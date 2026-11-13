import json
import secrets

import pytest

from core.entrypoint import main
from core.web.accounts import Accounts
from tests.test_linux_desktop_contract import RemoteError
from tests.test_linux_desktop_contract import server as server

EMAIL='rishik.patil78@gmail.com'
TEMP='Password'+'@123'


def seed():
    salt=secrets.token_hex(16)
    return dict(email=EMAIL,name='Rishik Patil',salt=salt,digest=Accounts._hash(TEMP,salt))


def test_initial_owner_must_change_before_privileged_access(server):
    gateway,remote=server
    assert gateway.accounts.bootstrap_owner(seed())
    owner=remote.login(EMAIL.upper(),TEMP)
    assert owner['role']=='owner' and owner['password_change_required']
    for path in ['/api/settings','/api/profiles','/api/access','/api/services','/api/records']:
        with pytest.raises(RemoteError) as exc:remote.request('GET',path)
        assert exc.value.status==403
    old_cookie=gateway.token({'Cookie':'; '.join(f'{c.name}={c.value}' for c in remote.cookies)})
    for body in [dict(current_password='wrong',new_password='new-password-1234'),dict(current_password=TEMP,new_password=TEMP)]:
        with pytest.raises(RemoteError):remote.request('POST','/api/password',body)
    remote.request('POST','/api/password',dict(current_password=TEMP,new_password='new-password-1234'))
    assert gateway.accounts.session(old_cookie) is None
    assert not gateway.accounts.bootstrap_owner(seed())
    with pytest.raises(RemoteError):remote.login(EMAIL,TEMP)
    profile=remote.login(EMAIL,'new-password-1234')
    assert not profile.get('password_change_required')
    remote.request('POST','/api/reauth',{'password':'new-password-1234'})
    assert remote.request('GET','/api/access')['requests']==[]
    assert len(gateway.accounts.profiles())==1


def test_seed_cli_is_explicit_idempotent_and_persistent(tmp_path,capsys):
    path=tmp_path/'initial-owner.json';path.write_text(json.dumps(seed()))
    data=tmp_path/'data'
    assert main(['init-owner','--owner-seed',str(path),'--data',str(data)])==0
    assert main(['init-owner','--owner-seed',str(path),'--data',str(data)])==0
    a=Accounts(data)
    try:
        assert a.login(EMAIL,TEMP)[2]['password_change_required']
        assert TEMP.encode() not in a.path.read_bytes()
    finally:a.close()
    assert TEMP not in capsys.readouterr().out


def test_email_registration_and_existing_accounts_are_not_promoted(tmp_path):
    a=Accounts(tmp_path)
    try:
        a.create('existing','existing-password-123','Existing',first=True)
        member=a.register('person@example.com','member-password-123','Person')
        assert member['role']=='pending'
        assert not a.bootstrap_owner(seed())
        assert len(a.profiles())==2
    finally:a.close()


def test_invalid_seed_is_rejected_without_creating_account(tmp_path):
    a=Accounts(tmp_path)
    try:
        bad=seed();bad['digest']='plaintext'
        with pytest.raises(ValueError):a.bootstrap_owner(bad)
        assert a.empty()
    finally:a.close()
