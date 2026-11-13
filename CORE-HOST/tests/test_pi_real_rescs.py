"""Real RESCS/SQLite/filesystem integration; no mock storage backend."""
import base64
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

import pytest

from core.web.gateway import Gateway
from core.web.storage import RescsStorage

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'CORE-CLIENT'))
remote_module=pytest.importorskip('client.desktop.remote')
Remote,RemoteError=remote_module.Remote,remote_module.RemoteError

PW='real-pi-integration-passphrase'


@pytest.fixture
def real_backend(tmp_path):
    source=Path(__file__).resolve().parents[2]/'services/RESCS'
    python=source.parents[2]/'unified/RISARMS-Portal/services/RESCS/.venv/bin/python'
    # Opt in only when a real installed backend environment was supplied.
    python=Path(os.environ.get('CORE_TEST_RESCS_PYTHON',str(python)))
    if not python.is_file():pytest.skip('Set CORE_TEST_RESCS_PYTHON to the installed RESCS interpreter.')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    env={**os.environ,'PYTHONPATH':str(source/'src'),'RESCS_API_KEY':'pi-test-local-key-only','RESCS_ENV':'test','RESCS_REQUIRE_SIGNED_OWNER':'true',
         'RESCS_DATABASE_URL':'sqlite:///'+str(tmp_path/'real-rescs.sqlite3'),'RESCS_STORAGE_DIR':str(tmp_path/'objects')}
    process=subprocess.Popen([str(python),'-m','uvicorn','rescs.main:create_app','--factory','--host','127.0.0.1','--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url='http://127.0.0.1:'+str(port)
    try:
        for _ in range(100):
            if process.poll() is not None:raise AssertionError('Real RESCS process exited during startup.')
            try:
                with urlopen(url+'/health/ready',timeout=.2) as response:
                    if response.status==200:break
            except OSError:time.sleep(.1)
        else:raise AssertionError('RESCS did not become ready.')
        yield url,tmp_path/'objects'
    finally:process.terminate();process.wait(timeout=15)


def start_portal(data,url):
    gateway=Gateway(directory=data)
    gateway.storage=RescsStorage(url,'pi-test-local-key-only')
    http=ThreadingHTTPServer(('127.0.0.1',0),gateway.handler());gateway.port=http.server_address[1]
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    return gateway,http,thread,'http://127.0.0.1:'+str(gateway.port)


def stop_portal(g,h,t):h.shutdown();h.server_close();t.join(3);g.close()


def test_actual_storage_privacy_sharing_trash_quota_restart_and_preview(tmp_path,real_backend):
    url,objects=real_backend;data=tmp_path/'portal'
    g,h,t,origin=start_portal(data,url)
    owner=Remote(origin);alice=Remote(origin);bob=Remote(origin)
    try:
        for name,first in [('owner',True),('alice',False),('bobby',False)]:g.accounts.create(name,PW,name,first=first)
        owner.login('owner',PW);alice_profile=alice.login('alice',PW);bob.login('bobby',PW)
        owner.request('POST','/api/reauth',{'password':PW})
        folder=alice.request('POST','/api/folders',{'name':'Family Shared'})
        body={'name':'private.txt','base64':base64.b64encode(b'private-rescs-content').decode(),'upload_id':'1'*32,'folder':folder['id']}
        meta=alice.request('POST','/api/files',body)
        assert alice.request('POST','/api/files',body)['id']==meta['id']
        assert len(list(objects.iterdir()))==1
        with patch.object(g.storage,'download',wraps=g.storage.download) as download:
            assert alice.request('GET','/api/files')['items'][0]['filename']=='private.txt'
            download.assert_not_called()
        for remote in (owner,bob):
            assert remote.request('GET','/api/files?owner='+alice_profile['id'])['items']==[]
            for suffix in ('','/preview'):
                with pytest.raises(RemoteError) as exc:remote.request('GET','/api/files/'+meta['id']+suffix)
                assert exc.value.status==403
            with pytest.raises(RemoteError):remote.request('POST','/api/files/'+meta['id']+'/trash')
        alice.request('POST','/api/shares',{'folder':folder['id'],'username':'bobby'})
        assert bob.request('GET','/api/files?shared=1')['total']==1
        assert base64.b64decode(bob.request('GET','/api/files/'+meta['id']+'/preview')['base64'])==b'private-rescs-content'
        with pytest.raises(RemoteError):bob.request('POST','/api/files/'+meta['id']+'/move',{'folder':''})
        alice.request('POST','/api/shares',{'folder':folder['id'],'username':'bobby','action':'revoke'})
        assert bob.request('GET','/api/files?shared=1&search=private')['total']==0
        with pytest.raises(RemoteError):bob.request('GET','/api/files/'+meta['id'])
        alice.request('POST','/api/files/'+meta['id']+'/delete')
        assert alice.request('GET','/api/files')['total']==0 and alice.request('GET','/api/files?trash=1')['total']==1
        with pytest.raises(RemoteError):alice.request('GET','/api/files/'+meta['id'])
        alice.request('POST','/api/files/'+meta['id']+'/restore')
        assert base64.b64decode(alice.request('GET','/api/files/'+meta['id'])['base64'])==b'private-rescs-content'
        # Force a small remaining quota through the actual gateway, without allocating 250 MiB.
        with patch.object(g.library,'quota',return_value=len(b'private-rescs-content')):
            with pytest.raises(RemoteError) as exc:alice.request('POST','/api/files',{**body,'upload_id':'2'*32})
            assert exc.value.status==400
        alice.request('POST','/api/records',{'key':'persistent','value':{'data':'survives restart'}})
        for remote in (owner,alice,bob):remote.close()
    finally:stop_portal(g,h,t)
    g,h,t,origin=start_portal(data,url);alice=Remote(origin)
    try:
        alice.login('alice',PW)
        assert alice.request('GET','/api/files')['total']==1
        assert alice.request('GET','/api/records')['items'][0]['value']=={'data':'survives restart'}
        assert alice.request('GET','/api/folders')['folders'][0]['id']==folder['id']
        alice.request('POST','/api/files/'+meta['id']+'/trash');alice.request('POST','/api/files/'+meta['id']+'/purge')
        assert alice.request('GET','/api/files?trash=1')['total']==0
        assert not list(objects.iterdir())
    finally:alice.close();stop_portal(g,h,t)
