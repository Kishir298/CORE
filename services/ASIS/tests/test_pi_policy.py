"""Pi policy unit tests plus real loopback/process plumbing, without real weights."""
from __future__ import annotations
import contextlib
import importlib.util
import json
import multiprocessing
import sys
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

import pytest
from asis.pi import policy, runtime

DIGEST = 'a' * 64
MODEL = 'qwen2.5:0.5b-instruct-q4_K_M'
RECORD = {'digest':DIGEST,'tier':'small','peak_gib':1.5,'context':2048,'tools_verified':False}

@pytest.fixture
def pi(tmp_path, monkeypatch):
    manifest=tmp_path/'models.json';manifest.write_text(json.dumps({MODEL:RECORD}))
    monkeypatch.setenv('ASIS_DEPLOYMENT_PROFILE','pi')
    monkeypatch.setenv('ASIS_PI_MODEL_MANIFEST',str(manifest))
    monkeypatch.setenv('ASIS_PI_QUEUE_DIRECTORY',str(tmp_path/'queue'))
    monkeypatch.setattr(runtime,'snapshot',lambda:policy.Snapshot(6*policy.GIB,10,0.1,0,45))
    return manifest

@pytest.mark.parametrize('free,expected',[(2,'blocked'),(3,'allowed'),(6,'allowed')])
def test_memory_gates(free,expected):
    s=policy.Snapshot(free*policy.GIB,10,0,0,40)
    assert policy.decide(s,RECORD,1.5)['status']==expected

@pytest.mark.parametrize('values', [{'cpu_percent':71},{'load_per_core':2},{'memory_pressure':11},{'temperature_c':81}])
def test_pressure_queues(values):
    s=replace(policy.Snapshot(6*policy.GIB,10,0,0,40),**values)
    assert policy.decide(s,RECORD,1.5)['status']=='queued'


def test_residency_not_counted_twice():
    s=policy.Snapshot(2*policy.GIB,10,0,0,40)
    assert policy.decide(s,RECORD,1.5,resident=1.5*policy.GIB)['status']=='allowed'


@pytest.mark.skipif(sys.platform != "linux", reason="Linux telemetry adapter")
def test_linux_snapshot_uses_available_and_cgroup_ancestors(tmp_path,monkeypatch):
    proc=tmp_path/'proc';group=tmp_path/'group';thermal=tmp_path/'thermal'
    (proc/'self').mkdir(parents=True);(proc/'pressure').mkdir()
    (group/'child').mkdir(parents=True);thermal.mkdir()
    (proc/'meminfo').write_text('MemFree: 100 kB\nMemAvailable: 6000000 kB\n')
    (proc/'loadavg').write_text('0.0 0.0 0.0 1/20 1')
    (proc/'pressure/memory').write_text('some avg10=0.00 avg60=0.00 total=0')
    (proc/'self/cgroup').write_text('0::/child\n')
    (group/'memory.max').write_text(str(2*policy.GIB));(group/'memory.current').write_text(str(policy.GIB))
    (group/'child/memory.max').write_text('max')
    sequence=iter([(100,50),(200,120)])
    monkeypatch.setattr(policy,'_cpu',lambda p:next(sequence))
    monkeypatch.setattr(policy.time,'sleep',lambda n:None)
    s=policy.snapshot(proc,group,thermal)
    assert s.available==policy.GIB and s.cgroup_remaining==policy.GIB
    assert s.cpu_percent==pytest.approx(30)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux telemetry adapter")
def test_missing_telemetry_blocks(tmp_path):
    with pytest.raises(policy.PolicyError,match='telemetry'):
        policy.snapshot(tmp_path,sample_seconds=0)

@pytest.mark.parametrize('mutate',[{'digest':'latest'},{'peak_gib':float('nan')},{'tier':'7b'},{'context':8192},{'tier':'ceiling'},{'context':4096}])
def test_invalid_or_unbenchmarked_approval(pi,mutate):
    pi.write_text(json.dumps({MODEL:{**RECORD,**mutate}}))
    with pytest.raises(policy.PolicyError):policy.approval(MODEL)

@pytest.mark.parametrize('endpoint',['https://example.com','http://192.168.1.2:11434','http://localhost:11434/other'])
def test_remote_endpoints_not_substituted(endpoint):
    with pytest.raises(policy.PolicyError,match='loopback'):
        runtime.request(endpoint,'/api/tags')


def test_coding_modes_blocked_even_when_enum(pi,memory_manager):
    from asis.cli.main import build_assistant
    from asis.ai import AIManager
    from asis.ai.providers import MockAIProvider
    from asis.identity import build_identity
    from asis.app.modes import AssistantMode
    with pytest.raises(policy.PolicyError,match='sandbox'):
        build_assistant(build_identity(),AIManager(MockAIProvider()),memory_manager,mode=AssistantMode.CODING)

@pytest.fixture
def server():
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def reply(self,value):
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps(value).encode())
        def do_GET(self):
            calls.append((self.path,None))
            self.reply({'models':[{'name':MODEL,'digest':DIGEST}]} if self.path=='/api/tags' else {'models':[]})
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.path,body))
            if self.path=='/api/show':
                return self.reply({'details':{'parameter_size':'494M','quantization_level':'Q4_K_M'},'capabilities':['completion']})
            if self.path=='/api/generate':return self.reply({'done':True})
            if body.get('stream'):
                self.send_response(200);self.end_headers()
                self.wfile.write((json.dumps({'message':{'content':'hello'},'done':True})+'\n').encode())
            else:self.reply({'message':{'content':'hello'},'done':True})
    instance=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=instance.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{instance.server_port}',calls
    instance.shutdown();instance.server_close();thread.join()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux queue adapter")
def test_real_http_provider_contract_and_pin(pi,server):
    from asis.ai.providers.ollama import OllamaProvider
    from asis.ai.models import AIMessage,MessageRole
    host,calls=server
    p=OllamaProvider(model=MODEL,host=host,num_predict=999,keep_alive='1h',retries=3)
    messages=[AIMessage(role=MessageRole.USER,content='hello')]
    assert p.chat(messages).content=='hello'
    assert ''.join(p.stream_chat(messages))=='hello'
    assert p.retries==3
    requests=[body for path,body in calls if path=='/api/chat']
    assert all(body['options']=={'num_ctx':2048,'num_thread':2,'num_predict':256} for body in requests)
    assert all(body['keep_alive']==0 and 'tools' not in body for body in requests)
    assert json.loads((runtime.queue_directory()/'status.json').read_text())['status']=='idle'
    pi.write_text(json.dumps({MODEL:{**RECORD,'digest':'b'*64}}))
    before=len(requests)
    with pytest.raises(policy.PolicyError,match='digest'):
        p.chat(messages)
    assert len([1 for path,body in calls if path=='/api/chat'])==before


def test_incomplete_stream_is_failure_without_retry(pi,monkeypatch):
    from asis.ai.providers.ollama import OllamaProvider
    from asis.ai.models import AIMessage,MessageRole
    from asis.errors import InferenceError
    @contextlib.contextmanager
    def fake_lease(*a):yield 2048,{'capabilities':['completion']},RECORD
    monkeypatch.setattr(runtime,'lease',fake_lease)
    from asis.ai.providers import ollama
    response=Mock();response.iter_lines.return_value=[json.dumps({'message':{'content':'partial'},'done':False})]
    post=Mock(return_value=response);monkeypatch.setattr(ollama,'_post',post)
    with pytest.raises(InferenceError,match='without completion'):
        list(OllamaProvider(model=MODEL).stream_chat([AIMessage(role=MessageRole.USER,content='hi')]))
    assert post.call_count==1 and response.close.called


def _hold_lock(directory,ready):
    import fcntl
    with open(Path(directory)/'inference.lock','a') as f:
        fcntl.flock(f,fcntl.LOCK_EX);ready.set();time.sleep(0.5)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux process locking")
def test_queue_serializes_processes_and_releases_on_cancel(pi,server):
    directory=runtime.queue_directory();directory.mkdir()
    ctx=multiprocessing.get_context("spawn")
    ready=ctx.Event()
    child=ctx.Process(target=_hold_lock,args=(directory,ready));child.start()
    assert ready.wait(3)
    start=time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        with runtime.lease(MODEL,server[0]):raise KeyboardInterrupt
    child.join(3)
    assert time.monotonic()-start>=0.5
    with runtime.lease(MODEL,server[0]):pass


def test_core_member_and_codegen_routes(pi,tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[2]/'core-source/CORE-HOST'
    if not root.exists():pytest.skip('matching CORE patch checkout required')
    spec=importlib.util.spec_from_file_location('pi_core_services',root/'core/web/services.py')
    core=importlib.util.module_from_spec(spec);sys.modules[spec.name]=core;spec.loader.exec_module(core)
    source=Path(__file__).resolve().parents[1]
    services=core.Services(tmp_path,{'asis':str(source)},'must-not-leak',{'asis':MODEL,'ascs':MODEL})
    user={'id':'a'*32,'role':'member'}
    argv,_,env=services.command('asis',user,'hello','build')
    assert 'asis.pi.worker' in argv and 'chat' in argv
    assert env['ASIS_CORE_ENABLED']=='false' and not any(k.startswith('RESCS_') for k in env)
    with pytest.raises(PermissionError):services.command('ascs',user,'hi','build')
    argv,_,_=services.command('ascs',{'id':'b'*32,'role':'owner'},'write code','auto')
    assert 'asis.pi.worker' in argv and 'code' in argv and 'agent.main' not in argv
    assert 'prompt' not in str(services.ai_status())


@pytest.mark.parametrize("values", [{"cpu_percent":float("nan")},{"temperature_c":None},{"available":-1}])
def test_invalid_telemetry_rejected(values):
    with pytest.raises(policy.PolicyError):
        policy.decide(replace(policy.Snapshot(6*policy.GIB,10,0,0,40),**values),RECORD,1.5)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux queue adapter")
def test_blocked_status_preserves_reason_and_resources(pi, server, monkeypatch):
    monkeypatch.setattr(runtime,"snapshot",lambda:policy.Snapshot(policy.GIB,10,0,0,40))
    with pytest.raises(policy.PolicyError,match="RAM"):
        with runtime.lease(MODEL,server[0]):pass
    report=json.loads((runtime.queue_directory()/"status.json").read_text())
    assert "RAM" in report["reason"] and report["resources"]["available"]==policy.GIB
    assert not any(path=="/api/chat" for path,_ in server[1])


def test_worker_failed_output_does_not_persist(pi, tmp_path, monkeypatch):
    from asis.pi import worker
    def broken(self,messages):
        yield "partial"
        raise RuntimeError("failed generation")
    monkeypatch.setattr(worker.OllamaProvider,"stream_chat",broken)
    home=tmp_path/"profile"
    assert worker.main(["--profile-dir",str(home),"--model",MODEL,"--message","hello"])==1
    assert not (home/"chat-context.json").exists()


def test_worker_history_isolated_and_no_memory(pi,tmp_path,monkeypatch):
    from asis.pi import worker
    prompts=[]
    def echo(self,messages):
        prompts.append([m.content for m in messages])
        yield "answer"
    monkeypatch.setattr(worker.OllamaProvider,"stream_chat",echo)
    for name,message in (("a","private A"),("b","private B")):
        assert worker.main(["--profile-dir",str(tmp_path/name),"--model",MODEL,"--message",message])==0
    assert "private A" not in prompts[1]
    prior=(tmp_path/"a/chat-context.json").read_text()
    assert worker.main(["--profile-dir",str(tmp_path/"a"),"--model",MODEL,"--message","ephemeral","--no-memory"])==0
    assert "private A" not in prompts[2] and (tmp_path/"a/chat-context.json").read_text()==prior


def test_pi_http_disables_proxies_and_redirects(pi,monkeypatch):
    from asis.ai.providers import ollama
    response=Mock(status_code=302)
    session=Mock(); session.post.return_value=response
    requests=Mock(); requests.Session.return_value=session
    with pytest.raises(ollama.InferenceError,match="HTTP"):
        ollama._post(requests,"http://127.0.0.1:11434/api/chat")
    assert session.trust_env is False
    assert session.post.call_args.kwargs["allow_redirects"] is False
    assert session.close.called and response.close.called


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_pi_adapter_refuses_unsupported_platforms(monkeypatch, platform):
    monkeypatch.setattr(policy.sys, "platform", platform)
    with pytest.raises(policy.PolicyError, match="requires Linux"):
        policy.snapshot(sample_seconds=0)


def test_pi_never_autostarts_unmanaged_daemon(pi):
    from asis.ai.ollama_lifecycle import ensure_ollama, OllamaLifecycleError
    launch=Mock()
    with pytest.raises(OllamaLifecycleError, match="automatic daemon launch"):
        ensure_ollama("http://127.0.0.1:11434", managed="on", available_fn=lambda:False, popen_factory=launch)
    launch.assert_not_called()
    assert ensure_ollama("http://127.0.0.1:11434", available_fn=lambda:True).owned is False
