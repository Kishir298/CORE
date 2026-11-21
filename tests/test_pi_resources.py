import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core import pi_resources as pr
from core.web.services import Services

MODEL='qwen2.5:1.5b';DIGEST='a'*64
linux_only=pytest.mark.skipif(sys.platform!='linux',reason='Pi resource checks require Linux /proc and fcntl')


def policy(tmp_path,available=6*pr.GIB,cpu=10,receipt=True):
    p=object.__new__(pr.PiPolicy);p.data=tmp_path
    p.metrics=lambda:{'available_bytes':available,'total_bytes':8*pr.GIB,'reserve_bytes':int(1.5*pr.GIB),
        'context':2048,'cpu_average_percent':cpu,'cpu_samples':10,'temperature_c':50,'memory_pressure_avg10':0,'load1':0}
    if receipt:(tmp_path/'pi-benchmarks.json').write_text(json.dumps({MODEL:{'approved':True,'digest':DIGEST,'context':2048,'machine_id':'machine','observed_peak_bytes':0}}))
    return p


def backend(path,body=None):
    if path=='/api/tags':return {'models':[{'name':MODEL,'digest':DIGEST}]}
    if path=='/api/show':return {'capabilities':['completion'],'details':{'parameter_size':'1.5B','quantization_level':'Q4_K_M'}}
    if path=='/api/ps':return {'models':[]}
    raise AssertionError(path)


@pytest.mark.parametrize('available,cpu,state',[(6,10,'allowed'),(2,10,'queued'),(6,90,'queued')])
def test_ram_and_sustained_cpu_gates(tmp_path,available,cpu,state):
    p=policy(tmp_path,available*pr.GIB,cpu)
    with patch.object(pr,'ollama',side_effect=backend),patch.object(pr,'machine_id',return_value='machine'):
        assert p.evaluate(MODEL)['state']==state


def test_digest_context_and_machine_bound_approval(tmp_path):
    p=policy(tmp_path,receipt=False)
    with patch.object(pr,'ollama',side_effect=backend),patch.object(pr,'machine_id',return_value='machine'):
        assert p.evaluate(MODEL)['state']=='blocked'
        assert p.evaluate(MODEL,benchmark=True)['state']=='allowed'
        assert p.evaluate('qwen2.5:7b',benchmark=True)['state']=='blocked'
        assert p.evaluate('qwen2.5:3b',benchmark=True)['state']=='blocked'  # Missing installed tag, not silently substituted.
    p=policy(tmp_path)
    with patch.object(pr,'ollama',side_effect=backend),patch.object(pr,'machine_id',return_value='different-pi'):
        assert p.evaluate(MODEL)['state']=='blocked'


def test_resident_model_is_not_counted_as_a_second_full_allocation(tmp_path):
    p=policy(tmp_path,int(2.7*pr.GIB))
    def resident(path,body=None):
        if path=='/api/ps':return {'models':[{'name':MODEL,'digest':DIGEST,'size':int(2*pr.GIB)}]}
        return backend(path,body)
    with patch.object(pr,'ollama',side_effect=resident),patch.object(pr,'machine_id',return_value='machine'):
        result=p.evaluate(MODEL);assert result['state']=='allowed' and result['estimated_additional_bytes']==256*1024**2


@linux_only
def test_memavailable_and_cgroup_limits_never_add_swap():
    contents={'/proc/meminfo':'MemTotal: 8388608 kB\nMemAvailable: 6291456 kB\nMemFree: 1 kB\nSwapFree: 99999999 kB\n',
              '/sys/fs/cgroup/memory.max':str(4*pr.GIB),'/sys/fs/cgroup/memory.current':str(3*pr.GIB)}
    def read(path,*args,**kwargs):
        if str(path) not in contents:raise FileNotFoundError(str(path))
        return contents[str(path)]
    with patch.object(Path,'read_text',read):assert pr.memory()==(pr.GIB,4*pr.GIB)


def test_shared_queue_serializes_models_and_queued_job_can_be_cancelled(tmp_path,monkeypatch):
    monkeypatch.setenv('CORE_SAFE_CHAT','1')
    switches=[]
    class FakePolicy:
        def __init__(self,data):pass
        def installed(self,*args):pass
        def switch(self,model):
            assert not any(j.status=='running' for j in services.jobs.values())
            switches.append(model)
        def evaluate(self,*args):return {'state':'allowed'}
        def close(self):pass
    monkeypatch.setattr(pr,'PiPolicy',FakePolicy)
    services=Services(tmp_path,{},'secret')
    monkeypatch.setattr(services,'command',lambda service,user,prompt,mode:([sys.executable,'-c','import time;print("response",flush=True);time.sleep(.3)','--model',MODEL],tmp_path,{}))
    one=services.start('asis',{'id':'a'*32,'role':'member'},'hello')
    two=services.start('ascs',{'id':'b'*32,'role':'owner'},'code')
    deadline=time.monotonic()+5
    while any(j.status in ('starting','queued','running') for j in services.jobs.values()) and time.monotonic()<deadline:time.sleep(.01)
    assert [services.jobs[x['id']].status for x in (one,two)]==['completed','completed']
    assert len(switches)==2
    services.pi_slot.acquire()
    queued=services.start('asis',{'id':'c'*32,'role':'member'},'cancel')
    services.stop(queued['id'],{'id':'c'*32})
    services.pi_slot.release()
    time.sleep(.1)
    assert services.jobs[queued['id']].status=='cancelled' and services.jobs[queued['id']].process is None
    services.close()


def test_unload_previous_model_before_switching(tmp_path):
    p=object.__new__(pr.PiPolicy)
    import threading
    p.closed=threading.Event();p.data=tmp_path;requests=[]
    (tmp_path/'pi-benchmarks.json').write_text(json.dumps({'previous':{'approved':True,'digest':'prev-digest','machine_id':'machine'}}))
    def api(path,body=None):
        requests.append((path,body))
        if path=='/api/ps':return {'models':[{'name':'previous','digest':'prev-digest'}]} if len(requests)==1 else {'models':[]}
        return {}
    with patch.object(pr,'ollama',side_effect=api),patch.object(pr,'machine_id',return_value='machine'):p.switch(MODEL)
    assert requests[1]==('/api/generate',{'model':'previous','keep_alive':0})


@linux_only
def test_shared_lock_rejects_untrusted_owner_and_missing_path(tmp_path):
    import threading
    file=tmp_path/'lock';file.write_text('')
    with pytest.raises(ValueError,match='root-owned'):pr.acquire_shared_lock(file,threading.Event(),time.monotonic()+1)
    with pytest.raises(FileNotFoundError):pr.acquire_shared_lock(tmp_path/'missing',threading.Event(),time.monotonic()+1)


@linux_only
def test_shared_lock_waits_and_releases_across_descriptors(tmp_path):
    import fcntl
    import stat
    import threading
    from types import SimpleNamespace
    path=tmp_path/'lock';path.write_text('');cancel=threading.Event()
    # Root ownership is an OS fixture here; real flock exclusion uses actual descriptors.
    with patch.object(pr.os,'fstat',return_value=SimpleNamespace(st_uid=0,st_mode=stat.S_IFREG|0o660)):
        first=pr.acquire_shared_lock(path,cancel,time.monotonic()+1)
        with pytest.raises(ValueError,match='expired'):pr.acquire_shared_lock(path,cancel,time.monotonic()+.01)
        pr.os.close(first)
        second=pr.acquire_shared_lock(path,cancel,time.monotonic()+1)
        fcntl.flock(second,fcntl.LOCK_UN);pr.os.close(second)
