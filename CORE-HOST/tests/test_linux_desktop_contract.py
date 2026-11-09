import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from core.web.gateway import Gateway
from core.web.storage import RecordConflict, RescsStorage, record_revision

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'CORE-CLIENT'))
try:
    from client.desktop.remote import Remote, RemoteError, sync_records
    from client.desktop.store import LocalStore
    HAS_DESKTOP = True
except ImportError:
    # Standalone host CI can validate its HTTP contract without installing the client.
    HAS_DESKTOP = False
    from http.cookiejar import CookieJar
    from urllib.request import build_opener, HTTPCookieProcessor, Request, ProxyHandler
    from urllib.error import HTTPError
    class RemoteError(ConnectionError):
        def __init__(self,message,status=0):super().__init__(message);self.status=status
    class Remote:
        def __init__(self,url):
            self.url=url;self.csrf="";self.cookies=CookieJar()
            self.opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(self.cookies))
        def request(self,method,path,body=None):
            request=Request(self.url+path,method=method,data=json.dumps(body or {}).encode() if method!="GET" else None,
                            headers={"Origin":self.url,"Content-Type":"application/json","X-Core-CSRF":self.csrf})
            try:
                with self.opener.open(request,timeout=5) as response:return json.loads(response.read())
            except HTTPError as error:raise RemoteError(json.loads(error.read())["error"],error.code) from error
        def login(self,username,password):
            result=self.request("POST","/api/login",{"username":username,"password":password});self.csrf=result["csrf"];return result["profile"]
        def close(self):
            if self.csrf:
                try:self.request("POST","/api/logout")
                except RemoteError:pass
            self.cookies.clear();self.csrf=""



class MemoryRescs(RescsStorage):
    def __init__(self):
        super().__init__('http://127.0.0.1:8081', 'a'*32)
        self.rows = {}

    def records(self, user_id, service='workspace', *, limit=100, offset=0):
        owner, namespace = self.scope(user_id,service)
        rows=[row for row in self.rows.values() if row['owner']==owner and row['namespace']==namespace]
        return {'items':rows[offset:offset+limit], 'total':len(rows),'limit':limit,'offset':offset}

    def save(self, user_id, key, value, service='workspace'):
        owner, namespace = self.scope(user_id,service)
        result={'owner':owner,'namespace':namespace,'key':key,'value':value}
        self.rows[(owner,namespace,key)] = result
        return result


@pytest.fixture
def server(tmp_path):
    gateway=Gateway(directory=tmp_path/'server');gateway.storage=MemoryRescs()
    http=ThreadingHTTPServer(('127.0.0.1',0),gateway.handler());http.daemon_threads=True
    gateway.port=http.server_address[1]
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    remote=Remote('http://127.0.0.1:'+str(gateway.port))
    yield gateway,remote
    remote.close();http.shutdown();http.server_close();thread.join(3);gateway.close()


def owner(gateway, remote):
    remote.request('POST','/api/setup',{'setup_key':gateway.setup_key,'username':'owner','password':'long-password-123','name':'Owner'})
    profile=remote.login('owner','long-password-123')
    remote.request('POST','/api/reauth',{'password':'long-password-123'})
    return profile


@pytest.mark.skipif(not HAS_DESKTOP,reason="Requires a sibling CORE-CLIENT for cross-repo native sync validation")
def test_real_native_login_csrf_sync_conflict_and_offline_recovery(server,tmp_path):
    gateway,remote=server;profile=owner(gateway,remote)
    store=LocalStore(tmp_path/'local');local=store.create('owner','local-passphrase-123')
    store.bind(local,remote.url,profile['id']);store.save(local,'workspace','note',{'text':'offline draft'})
    assert sync_records(store,local,remote) == {'saved':1,'conflicts':[]}
    assert store.records(local)[0]['pending']==0
    store.save(local,'workspace','note',{'text':'local edit'})
    remote.request('POST','/api/records',{'key':'note','value':{'text':'server edit'}})
    assert sync_records(store,local,remote) == {'saved':0,'conflicts':['workspace/note']}
    assert store.records(local)[0]['value']=={'text':'local edit'}
    assert gateway.storage.current_record(profile['id'],'note')['value']=={'text':'server edit'}
    assert b'long-password-123' not in (tmp_path/'local/desktop.sqlite3').read_bytes()
    remote.close()
    with pytest.raises(RemoteError):remote.request('GET','/api/me')
    assert store.records(local)[0]['pending']==1;store.close()


def test_owner_setup_and_server_authorization_work_without_browser(server):
    gateway,remote=server;owner(gateway,remote)
    remote.request('POST','/api/profiles',{'username':'member','password':'member-password-123','name':'Member'})
    remote.close();remote.login('member','member-password-123')
    with pytest.raises(RemoteError) as error:remote.request('GET','/api/settings')
    assert error.value.status==403
    assert 'conditional_records_v1' in remote.request('GET','/api/health')['capabilities']


def test_conditional_create_cannot_overwrite_existing_key():
    storage=MemoryRescs();storage.save('a'*32,'key',{'v':1})
    with pytest.raises(RecordConflict):storage.conditional_save('a'*32,'key',{'v':2},'workspace','')
    current=storage.current_record('a'*32,'key')
    assert storage.conditional_save('a'*32,'key',{'v':2},'workspace',record_revision(current['value']))['value']=={'v':2}


def test_revision_lookup_checks_records_after_first_page():
    storage=MemoryRescs()
    for i in range(105):storage.save('a'*32,str(i),{'v':i})
    assert storage.current_record('a'*32,'104')['value']=={'v':104}
    assert storage.current_record('b'*32,'104') is None


def test_gateway_only_cli_is_headless_and_does_not_start_native_runtime(tmp_path,monkeypatch):
    from core.entrypoint import main
    calls=[]
    monkeypatch.setattr('core.web.gateway.serve',lambda app,**kw:calls.append((app,kw)))
    assert main(['--gateway-only','--data',str(tmp_path/'web')])==0
    assert calls[0][0] is None
    assert calls[0][1]['open_browser'] is False


def test_conditional_revision_parser_refuses_invalid_token():
    with pytest.raises(ValueError):MemoryRescs().conditional_save('a'*32,'key',{},'workspace','not-a-hash')
