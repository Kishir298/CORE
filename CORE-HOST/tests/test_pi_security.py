"""Pi privacy boundaries are checked against APIs, not only UI visibility."""
import json
import time
from unittest.mock import patch

import pytest

from core.web.gateway import Gateway
from core.web.services import Job, Services

PW='pi-security-passphrase-123'


@pytest.fixture
def portal(tmp_path):
    g=Gateway(directory=tmp_path)
    owner=g.accounts.create('owner',PW,'Owner',first=True)
    alice=g.accounts.create('alice',PW,'Alice')
    bob=g.accounts.create('bobby',PW,'Bob')
    yield g,owner,alice,bob
    g.close()


def auth(g,name):
    _,body,cookie=g.dispatch('POST','/api/login',{'username':name,'password':PW},{})
    return {'Cookie':cookie.split(';')[0],'X-Core-CSRF':body['csrf']}


def test_owner_reauth_is_session_bound_expires_and_never_bypasses_privacy(portal):
    g,owner,alice,bob=portal
    headers=auth(g,'owner');other=auth(g,'owner')
    with pytest.raises(PermissionError,match='Re-enter'):g.dispatch('GET','/api/settings',{},headers)
    g.dispatch('POST','/api/reauth',{'password':PW},headers)
    assert g.dispatch('GET','/api/settings',{},headers)[0]==200
    with pytest.raises(PermissionError,match='Re-enter'):g.dispatch('GET','/api/settings',{},other)
    with g.accounts.db:g.accounts.db.execute('UPDATE sessions SET admin_until=?',(time.time()-1,))
    with pytest.raises(PermissionError,match='Re-enter'):g.dispatch('GET','/api/settings',{},headers)
    g.dispatch('POST','/api/reauth',{'password':PW},headers)
    private=g.data/'profiles'/alice['id']/'chats';private.mkdir(parents=True)
    (private/'private.json').write_text(json.dumps({'id':'alice-chat','service':'asis','prompt':'secret','events':[]}))
    assert g.dispatch('GET','/api/chats?owner='+alice['id'],{},headers)[1]['chats']==[]
    assert len(g.dispatch('GET','/api/chats',{},auth(g,'alice'))[1]['chats'])==1
    with patch.object(g.storage,'file_meta',side_effect=PermissionError('Wrong owner')):
        with pytest.raises(PermissionError):g.dispatch('GET','/api/files/foreign',{},headers)


def test_reauth_role_csrf_and_rate_limit(portal):
    g,_,_,_=portal;member=auth(g,'alice');owner=auth(g,'owner')
    with pytest.raises(PermissionError):g.dispatch('POST','/api/reauth',{'password':PW},member)
    with pytest.raises(PermissionError):g.dispatch('POST','/api/reauth',{'password':PW},{'Cookie':owner['Cookie']})
    for _ in range(5):
        with pytest.raises(PermissionError):g.dispatch('POST','/api/reauth',{'password':'wrong'},owner)
    with pytest.raises(PermissionError,match='Too many'):g.dispatch('POST','/api/reauth',{'password':PW},owner)
    assert 'wrong' not in json.dumps(g.accounts.events())


def test_member_and_unlocked_admin_cannot_grant_themselves_access(portal):
    g,owner,alice,bob=portal;alice_h=auth(g,'alice');owner_h=auth(g,'owner')
    folder=g.dispatch('POST','/api/folders',{'name':'Family Shared'},alice_h)[1]
    g.dispatch('POST','/api/reauth',{'password':PW},owner_h)
    for h in (owner_h,auth(g,'bobby')):
        with pytest.raises(PermissionError):g.dispatch('POST','/api/shares',{'folder':folder['id'],'username':'owner'},h)
        with pytest.raises(PermissionError):g.dispatch('GET','/api/files?folder='+folder['id'],{},h)
    g.dispatch('POST','/api/shares',{'folder':folder['id'],'username':'bobby'},alice_h)
    assert len(g.dispatch('GET','/api/folders',{},auth(g,'bobby'))[1]['shared_folders'])==1
    assert g.dispatch('GET','/api/folders',{},owner_h)[1]['shared_folders']==[]


def test_revocation_and_session_expiry(portal):
    g,_,alice,_=portal;h=auth(g,'alice')
    g.accounts.review(alice['id'],'revoke')
    with pytest.raises(PermissionError):g.dispatch('GET','/api/chats',{},h)
    h=auth(g,'owner')
    with g.accounts.db:g.accounts.db.execute('UPDATE sessions SET expires=?',(time.time()-1,))
    with pytest.raises(PermissionError):g.dispatch('GET','/api/records',{},h)


def test_pi_uses_safe_owner_chat_and_caps_concurrency(tmp_path,monkeypatch):
    monkeypatch.setenv('CORE_SAFE_CHAT','1');monkeypatch.setenv('CORE_MAX_AI_JOBS','1')
    monkeypatch.setenv('CORE_AI_CONTEXT_LIMIT','4096');monkeypatch.setenv('CORE_AI_THREADS','2')
    services=Services(tmp_path,{},'private',{'asis':'small-model','ascs':'small-coder'})
    argv,home,env=services.command('asis',{'id':'a'*32,'role':'owner'},'hello','plan')
    assert 'core.web.chat_worker' in argv and env['CORE_AI_CONTEXT_LIMIT']=='4096'
    assert '--message-stdin' in argv and not any('hello' in x for x in argv)
    assert '--coding' in services.command('ascs',{'id':'a'*32,'role':'owner'},'hello','plan')[0]
    with pytest.raises(ValueError,match='generation only'):services.command('ascs',{'id':'a'*32,'role':'owner'},'hello','build')
    for service in ('tiviss',):
        with pytest.raises(PermissionError):services.command(service,{'id':'a'*32,'role':'owner'},'read other chats','plan')
    services.jobs['busy']=Job('busy','a'*32,'asis',status='running')
    with pytest.raises(ValueError,match='profile'):services.start('asis',{'id':'a'*32,'role':'member'},'hi')
    services.close()


def test_readiness_and_quota_admin(portal):
    g,_,alice,_=portal;h=auth(g,'owner')
    with patch.object(g.storage,'request',side_effect=ConnectionError()):assert g.dispatch('GET','/api/ready',{}, {})[0]==503
    g.dispatch('POST','/api/reauth',{'password':PW},h)
    g.dispatch('POST','/api/quotas',{'username':'alice','bytes':1024**3},h)
    assert g.library.quota(alice['id'])==1024**3
    with pytest.raises(ValueError):g.dispatch('POST','/api/quotas',{'username':'alice','bytes':1},h)
