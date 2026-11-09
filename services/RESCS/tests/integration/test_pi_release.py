import errno
import pytest
from fastapi.testclient import TestClient
from rescs.config import Settings
from rescs.main import create_app
from rescs.gateway_scope import signed_headers
from rescs.mounts import check_mount
from rescs.storage.local import LocalObjectStore

KEY='integration-key-0123456789abcdef'
A='core.profile.'+'a'*32
B='core.profile.'+'b'*32


def settings(tmp_path, **kwargs):
    return Settings(_env_file=None, api_key=KEY, database_url='sqlite:///'+str(tmp_path/'data.db'), storage_dir=str(tmp_path/'files'), require_signed_owner=True, **kwargs)


def call(client, method, path, owner=A, **kwargs):
    return client.request(method,path,headers={'X-API-Key':KEY,**signed_headers(KEY,owner,method,path.split('?')[0])},**kwargs)


def test_real_storage_ownership_trash_restart(tmp_path):
    s=settings(tmp_path)
    with TestClient(create_app(s)) as c:
        assert c.get('/api/v1/files',headers={'X-API-Key':KEY}).status_code==401
        f=call(c,'POST','/api/v1/files',data={'owner':A},files={'upload':('private.txt',b'private bytes')})
        assert f.status_code==201, f.text
        fid=f.json()['id']
        for path in ['/api/v1/files/'+fid,'/api/v1/files/'+fid+'/content']:
            assert call(c,'GET',path,owner=B).status_code==403
        assert call(c,'GET','/api/v1/files',owner=B).json()['items']==[]
        assert call(c,'DELETE','/api/v1/files/'+fid,owner=B).status_code==403
        assert call(c,'POST','/api/v1/admin/cleanup').status_code==403
        assert call(c,'DELETE','/api/v1/files/'+fid).status_code==204
        assert call(c,'GET','/api/v1/files/'+fid).status_code==404
        assert call(c,'POST','/api/v1/files/'+fid+'/restore').status_code==200
    with TestClient(create_app(s)) as c:
        assert call(c,'GET','/api/v1/files/'+fid+'/content').content==b'private bytes'
        assert call(c,'GET','/api/v1/files?owner='+B).status_code==401


def test_signature_expiry_and_method_binding(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as c:
        for headers in [signed_headers(KEY,A,'GET','/api/v1/files',1), signed_headers(KEY,A,'POST','/api/v1/files')]:
            assert c.get('/api/v1/files',headers={'X-API-Key':KEY,**headers}).status_code==401


def test_ssd_guard_before_database_creation(tmp_path, monkeypatch):
    root=tmp_path/'missing';s=settings(tmp_path,required_mount=str(root))
    with pytest.raises(OSError):check_mount(s)
    assert not (tmp_path/'data.db').exists()
    monkeypatch.setattr('os.path.ismount',lambda _:True)
    with pytest.raises(ValueError):check_mount(s)


def test_disk_full_no_success_or_temporary_blob(tmp_path,monkeypatch):
    store=LocalObjectStore(tmp_path)
    def full(*args):raise OSError(errno.ENOSPC,'disk full')
    monkeypatch.setattr('os.fsync',full)
    with pytest.raises(Exception):store.put('safe',b'content')
    assert list(tmp_path.iterdir())==[]
