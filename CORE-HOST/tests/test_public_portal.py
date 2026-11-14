import io
import json
import os
import sys
from unittest.mock import patch

import pytest

from core.web.services import Job, Services
from core.web.storage import RescsStorage
from tests.test_linux_desktop_contract import Remote, RemoteError, owner
from tests.test_linux_desktop_contract import server as server


def test_registration_requires_approval_and_members_have_only_messaging_storage(server):
    gateway, admin=server;owner(gateway,admin)
    visitor=Remote(admin.url)
    request=visitor.request('POST','/api/register',{'username':'visitor','password':'visitor-password-123','name':'Visitor'})
    assert request['status']=='pending' and visitor.csrf==''
    with pytest.raises(RemoteError,match='pending approval'):visitor.login('visitor','visitor-password-123')
    pending=admin.request('GET','/api/access')['requests'];assert len(pending)==1
    admin.request('POST','/api/access',{'user_id':pending[0]['id'],'action':'approve'})
    profile=visitor.login('visitor','visitor-password-123');assert profile['role']=='member'
    services={s['id']:s for s in visitor.request('GET','/api/services')['services']}
    assert services['asis']['allowed'] is True
    assert services['ascs']['allowed'] is False
    for endpoint in ['/api/settings','/api/profiles','/api/access','/api/audit']:
        with pytest.raises(RemoteError) as error:visitor.request('GET',endpoint)
        assert error.value.status==403
    with pytest.raises(RemoteError) as error:visitor.request('POST','/api/jobs',{'service':'ascs','prompt':'do work'})
    assert error.value.status==403
    visitor.request('POST','/api/records',{'key':'own','value':{'ok':True}})
    assert len(visitor.request('GET','/api/records')['items'])==1
    with pytest.raises(RemoteError):visitor.request('GET','/api/records?service=tiviss')
    admin.request('POST','/api/access',{'user_id':profile['id'],'action':'revoke'})
    with pytest.raises(RemoteError):visitor.request('GET','/api/me')
    visitor.close()


def test_public_member_worker_has_no_agent_tools_or_cross_profile_environment(tmp_path):
    services=Services(tmp_path,{},'backend-secret',{'asis':'installed:test'})
    services.profile_models={'a'*32:{'asis':'personal:test'}}
    argv,cwd,env=services.command('asis',{'id':'a'*32,'role':'member'},'--prompt; arbitrary text','plan')
    assert argv[3]=='core.web.chat_worker'
    assert 'personal:test' in argv and '--message=--prompt; arbitrary text' in argv
    assert str(cwd)==str(tmp_path/'profiles'/('a'*32))
    assert 'RESCS_API_KEY' not in env and not any(k.startswith('ASIS_') for k in env)
    other=services.command('asis',{'id':'b'*32,'role':'member'},'hi','plan')[0]
    assert 'installed:test' in other and str(cwd) not in other


def test_server_chat_files_and_logs_are_per_account(tmp_path):
    services=Services(tmp_path,{},'secret')
    first=Job('1'*32,'a'*32,'asis',prompt='alice secret')
    second=Job('2'*32,'b'*32,'asis',prompt='bob secret')
    for job in (first,second):services._run(job,[sys.executable,'-c','print("private output")'],tmp_path,dict(os.environ))
    a=tmp_path/'profiles'/('a'*32)/'chats'/('1'*32+'.json')
    b=tmp_path/'profiles'/('b'*32)/'chats'/('2'*32+'.json')
    assert 'alice secret' in a.read_text() and 'bob secret' not in a.read_text()
    assert 'bob secret' in b.read_text() and 'alice secret' not in b.read_text()
    assert 'alice secret' not in (a.parents[1]/'logs/tasks.log').read_text()


def test_tool_free_model_memory_is_separate_between_accounts(tmp_path,monkeypatch):
    from core.web import chat_worker
    bodies=[]
    class Stream:
        def __init__(self,model,messages): bodies.append({'model':model,'messages':json.loads(json.dumps(messages))})
        def __enter__(self):return iter([{'message':{'content':'reply'},'done':True}])
        def __exit__(self,*args):pass
    monkeypatch.setattr(chat_worker,'ChatStream',Stream)
    for profile,message in [('alice','alice private'),('bob','bob private'),('alice','alice next')]:
        monkeypatch.setattr(sys,'argv',['worker','--profile-dir',str(tmp_path/profile),'--model','installed:test','--message',message])
        assert chat_worker.main()==0
    assert bodies[1]['messages']==[{'role':'user','content':'bob private'}]
    assert bodies[2]['messages'][0]['content']=='alice private'
    assert all('tools' not in body for body in bodies)


def test_rescs_file_owner_checked_before_downloading_content():
    storage=RescsStorage('http://127.0.0.1:8081','a'*32)
    with patch.object(storage,'request',return_value={'owner':'core.profile.'+'b'*32}) as request, patch.object(storage.opener,'open') as opened:
        with pytest.raises(PermissionError):storage.download('a'*32,'foreign-file')
        assert request.call_args.args==('GET','/api/v1/files/foreign-file')
        opened.assert_not_called()


def test_file_collection_fails_closed_if_backend_ignores_owner():
    storage=RescsStorage('http://127.0.0.1:8081','a'*32)
    with patch.object(storage,'request',return_value={'items':[{'owner':'other'}]}):
        with pytest.raises(PermissionError):storage.files('a'*32)


def test_rescs_upload_contract_and_content_hash():
    import hashlib
    storage=RescsStorage('http://127.0.0.1:8081','a'*32);data=b'cloud bytes'
    meta={'id':'file-1','owner':'core.profile.'+'a'*32,'sha256':hashlib.sha256(data).hexdigest()}
    with patch.object(storage,'files',return_value={'items':[],'total':0}), patch.object(storage.opener,'open',return_value=io.BytesIO(json.dumps(meta).encode())) as opened:
        assert storage.upload('a'*32,'../../notes.txt',data,'1'*32)==meta
        request=opened.call_args.args[0]
        assert request.method=='POST' and request.full_url.endswith('/api/v1/files')
        assert b'name="upload"; filename="notes.txt"' in request.data
        assert b'name="owner"' in request.data and data in request.data
