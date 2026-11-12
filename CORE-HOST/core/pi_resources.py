"""Conservative Pi inference policy. No downloads or external inference endpoints.

These are project admission estimates, not benchmark claims. Exact installed
model digests need a locally created benchmark receipt before ordinary jobs.
"""
import json
import os
import re
import threading
import time
from collections import deque
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

GIB=1024**3
TIERS={'0.5b':(2.5,1.0),'1.5b':(3.5,2.0),'3b':(5.0,3.5)}


def ollama(path,body=None):
    request=Request('http://127.0.0.1:11434'+path,data=None if body is None else json.dumps(body).encode(),
                    headers={'Content-Type':'application/json'},method='GET' if body is None else 'POST')
    with build_opener(ProxyHandler({})).open(request,timeout=4) as response:
        raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('Model metadata exceeded its size limit.')
        return json.loads(raw)


def memory():
    fields={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.split()[1].isdigit()}
    available=fields['MemAvailable'];total=fields['MemTotal']
    # v2 or v1 limit minus actual usage; swap is never added.
    pairs=[('/sys/fs/cgroup/memory.max','/sys/fs/cgroup/memory.current'),
           ('/sys/fs/cgroup/memory/memory.limit_in_bytes','/sys/fs/cgroup/memory/memory.usage_in_bytes')]
    if os.environ.get('CORE_AI_CGROUP'):
        group=Path(os.environ['CORE_AI_CGROUP']).resolve()
        root=Path('/sys/fs/cgroup')
        if not group.is_relative_to(root):raise ValueError('AI cgroup must be under /sys/fs/cgroup.')
        if not group.is_dir():raise ValueError('Ollama cgroup is unavailable; start the dedicated Ollama service first.')
        pairs=[(str(p/'memory.max'),str(p/'memory.current')) for p in (group,*group.parents) if p==root or p.is_relative_to(root)]
    for limit_path,used_path in pairs:
        try:
            text=Path(limit_path).read_text().strip()
            if text!='max':
                limit=int(text);used=int(Path(used_path).read_text())
                if limit>0:available=min(available,max(0,limit-used));total=min(total,limit)
        except (OSError,ValueError):pass
    return available,total


def cpu_ticks():
    fields=[int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    return sum(fields),fields[3]+fields[4]


class PiPolicy:
    def __init__(self,data):
        self.data=Path(data);self.samples=deque(maxlen=10);self.lock=threading.Lock();self.closed=threading.Event()
        self.thread=threading.Thread(target=self._sample,daemon=True);self.thread.start()

    def _sample(self):
        previous=None
        while not self.closed.is_set():
            try:
                current=cpu_ticks()
                if previous and current[0]>previous[0]:
                    usage=100*(1-(current[1]-previous[1])/(current[0]-previous[0]))
                    with self.lock:self.samples.append(usage)
                previous=current
            except (OSError,ValueError):pass
            self.closed.wait(1)

    def metrics(self):
        available,total=memory()
        with self.lock:samples=list(self.samples)
        temperature=None;pressure=None
        try:temperature=int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000
        except (OSError,ValueError):pass
        try:
            line=Path('/proc/pressure/memory').read_text().splitlines()[0]
            pressure=float(dict(x.split('=') for x in line.split()[1:])['avg10'])
        except (OSError,ValueError,KeyError,IndexError):pass
        return {'available_bytes':available,'total_bytes':total,'reserve_bytes':int(1.5*GIB),
                'context':int(os.environ.get('CORE_AI_CONTEXT_LIMIT','2048')),
                'cpu_average_percent':sum(samples)/len(samples) if samples else None,'cpu_samples':len(samples),
                'temperature_c':temperature,'memory_pressure_avg10':pressure,'load1':os.getloadavg()[0]}

    def installed(self,model,service):
        # Only explicitly named small instruct Q4 variants; mutable tags are digest-checked.
        family='qwen2.5-coder' if service=='ascs' else 'qwen2.5'
        match=re.fullmatch(re.escape(family)+r':(0\.5b|1\.5b|3b)(?:-instruct-q4_[kK]_[mM]|-instruct-q4_0)?',model or '')
        if not match:raise ValueError('Pi policy permits explicit Qwen2.5/Qwen2.5-Coder 0.5B, 1.5B or 3B instruct Q4 tags only; 4B/7B+ are not admitted.')
        models=ollama('/api/tags').get('models',[])
        row=next((x for x in models if x.get('name')==model or x.get('model')==model),None)
        if not row or not re.fullmatch(r'(?:sha256:)?[a-f0-9]{64}',row.get('digest','')):raise ValueError('Install the exact model explicitly; a full installed digest is required.')
        show=ollama('/api/show',{'model':model});details=show.get('details',{})
        if details.get('quantization_level','').upper() not in ('Q4_0','Q4_K_M'):raise ValueError('Only verified Q4_0 or Q4_K_M quantization is admitted.')
        parameter=details.get('parameter_size','')
        if not re.fullmatch(r'[0-9.]+[BM]',parameter):raise ValueError('Model parameter size metadata is missing.')
        billions=float(parameter[:-1])/(1000 if parameter.endswith('M') else 1)
        if billions>{'0.5b':0.7,'1.5b':1.8,'3b':3.5}[match[1]]:raise ValueError('Installed model exceeds the Pi parameter ceiling.')
        if 'completion' not in show.get('capabilities',[]):raise ValueError('The installed model does not advertise text completion support.')
        return match[1],row,show

    def evaluate(self,model,service='asis',*,benchmark=False):
        try:result=self.metrics()
        except (OSError,ValueError,KeyError) as exc:return {'model':model,'service':service,'state':'blocked','reason':str(exc)}
        result.update(model=model,service=service,state='blocked',reason='')
        try:
            if result['context'] not in (2048,4096):raise ValueError('Pi context must be 2048 or an independently benchmarked 4096.')
            tier,row,_=self.installed(model,service);result['digest']=row['digest']
            report_path=self.data/'pi-benchmarks.json'
            reports=json.loads(report_path.read_text()) if report_path.exists() else {}
            receipt=reports.get(model,{})
            current=(receipt.get('digest')==row['digest'] and receipt.get('context')==result['context'] and receipt.get('approved') is True
                     and receipt.get('machine_id')==machine_id())
            if not benchmark and not current:raise ValueError('Benchmark and explicitly approve this exact model digest/context on this Pi before use.')
            loaded=ollama('/api/ps').get('models',[])
            resident=sum(int(x.get('size',0)) for x in loaded if x.get('digest')==row['digest'])
            gate,estimate=TIERS[tier]
            estimate=max(int(estimate*GIB),int(receipt.get('observed_peak_bytes',0)*1.25) if current else 0)
            additional=max(256*1024**2,estimate-resident)
            result.update(resident_bytes=resident,estimated_additional_bytes=additional,tier=tier)
            if result['available_bytes']+resident<int(gate*GIB) or result['available_bytes']-result['reserve_bytes']<additional:
                result.update(state='queued',reason='Insufficient effective RAM/headroom. Explicitly select an approved smaller model; swap does not qualify.');return result
            if result['cpu_samples']<10 or result['cpu_average_percent']>70:
                result.update(state='queued',reason='Collecting ten CPU samples or sustained CPU utilization exceeds 70%.');return result
            if (result['temperature_c'] is not None and result['temperature_c']>=80) or (result['memory_pressure_avg10'] or 0)>10 or result['load1']>2*(os.cpu_count() or 1):
                result.update(state='queued',reason='Thermal, memory or runnable-work pressure is too high.');return result
            result.update(state='allowed',reason='Admitted for tool-free inference; full coding execution remains disabled.')
        except (OSError,ValueError,KeyError,TypeError) as exc:result['reason']=str(exc)
        return result

    def switch(self,model):
        # Called only while the shared AI slot is held, before admission is rechecked.
        others=[x for x in ollama('/api/ps').get('models',[]) if x.get('name',x.get('model'))!=model]
        if others:
            receipts_path=self.data/'pi-benchmarks.json'
            receipts=json.loads(receipts_path.read_text()) if receipts_path.exists() else {}
            allowed={r.get('digest') for r in receipts.values() if r.get('approved') is True and r.get('machine_id')==machine_id()}
            if any(row.get('digest') not in allowed for row in others):
                raise ValueError('An unrelated or unapproved model is resident. Unload it explicitly before using the CORE queue.')
        for row in others:ollama('/api/generate',{'model':row.get('name',row.get('model')),'keep_alive':0})
        if others:
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                if not any(x.get('name',x.get('model'))!=model for x in ollama('/api/ps').get('models',[])):return
                if self.closed.wait(.2):raise ValueError('Host is shutting down.')
            raise ValueError('Previous model did not unload; the new job was not started.')

    def close(self):
        self.closed.set();self.thread.join(timeout=2)


def machine_id():
    import hashlib
    return hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest()


def benchmark(data,model,service,approve=False):
    """Explicit local smoke/measurement. Stop CORE first to avoid a second queue."""
    import socket

    from core.inference import ChatStream
    with socket.socket() as probe:
        probe.settimeout(.5)
        if probe.connect_ex(('127.0.0.1',8780))==0:
            raise ValueError('Stop risarms-core before this exclusive benchmark; RESCS and the proxy may stay online.')
    os.environ.setdefault('CORE_AI_CONTEXT_LIMIT','2048');os.environ.setdefault('CORE_AI_THREADS','2')
    policy=PiPolicy(data)
    try:
        policy.installed(model,service);policy.switch(model)
        # CPU admission uses a genuine ten-second interval, not one instantaneous sample.
        while len(policy.samples)<10:
            if policy.closed.wait(.2):raise ValueError('Benchmark cancelled.')
        admission=policy.evaluate(model,service,benchmark=True)
        if admission['state']!='allowed':raise ValueError(admission['reason'])
        available_before,_=memory();minimum=available_before;stop=threading.Event()
        def sample_memory():
            nonlocal minimum
            while not stop.wait(.1):
                try:minimum=min(minimum,memory()[0])
                except (OSError,KeyError):pass
        observer=threading.Thread(target=sample_memory,daemon=True);observer.start()
        started=time.monotonic();first=None;output=[];last={}
        prompt='Write a Python add(a, b) function and explain it.' if service=='ascs' else 'Explain what a local home server does in two sentences.'
        try:
            with ChatStream(model,[{'role':'user','content':prompt}]) as stream:
                for event in stream:
                    text=event.get('message',{}).get('content','')
                    if text:
                        if first is None:first=time.monotonic()-started
                        output.append(text)
                    last=event
                    if time.monotonic()-started>120:raise ValueError('Benchmark exceeded its two-minute runtime limit.')
        finally:stop.set();observer.join(timeout=2)
        if not output:raise ValueError('Model did not produce a text response; approval refused.')
        # A probe does not establish tool competence or quality on larger coding tasks.
        report={'model':model,'service':service,'digest':admission['digest'],'context':admission['context'],
                'machine_id':machine_id(),'observed_peak_bytes':max(0,available_before-minimum)+admission.get('resident_bytes',0),
                'first_text_seconds':first,'elapsed_seconds':time.monotonic()-started,
                'tokens_per_second':(last.get('eval_count',0)/(last.get('eval_duration',1)/1e9)) if last.get('eval_duration',0)>0 else None,
                'response':''.join(output),'approved':bool(approve),'at':time.time(),
                'quality':'Smoke response only. Operator must separately evaluate representative tasks and web latency.'}
        path=Path(data)/'pi-benchmarks.json';previous=json.loads(path.read_text()) if path.exists() else {}
        if approve:
            previous[model]=report
            import tempfile
            fd,name=tempfile.mkstemp(prefix='benchmark-',dir=data,suffix='.json')
            with os.fdopen(fd,'w') as f:json.dump(previous,f,indent=2)
            Path(name).replace(path)
        return report
    finally:
        policy.close()
        try:ollama('/api/generate',{'model':model,'keep_alive':0})
        except (OSError,ValueError):pass


def acquire_shared_lock(path,cancel,deadline):
    """Coordinate with updated standalone ASCS through a trusted Linux flock."""
    import fcntl
    import stat
    descriptor=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
    try:
        info=os.fstat(descriptor)
        if info.st_uid!=0 or not stat.S_ISREG(info.st_mode) or info.st_mode&0o002:
            raise ValueError('Inference lock must be a root-owned regular file without world-write access.')
        while not cancel.is_set():
            try:fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB);return descriptor
            except BlockingIOError:
                if time.monotonic()>deadline:raise ValueError('Shared ASIS/ASCS inference lock wait expired.')
                cancel.wait(.2)
        raise ValueError('Queued inference was cancelled.')
    except BaseException:os.close(descriptor);raise
