import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest

HERE=Path(__file__).resolve().parents[1]

def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_ssd_missing_wrong_uuid_and_readonly_fail_closed(tmp_path):
    guard=load('guard')
    with patch.object(Path,'is_mount',return_value=False),pytest.raises(RuntimeError,match='microSD'):guard.verify_mount(tmp_path,'correct')
    def result(uuid='correct',opts='rw,noatime'):
        return type('R',(),{'stdout':json.dumps({'filesystems':[{'uuid':uuid,'fstype':'ext4','options':opts}]})})()
    with patch.object(Path,'is_mount',return_value=True),patch.object(guard.subprocess,'run',return_value=result()):
        assert guard.verify_mount(tmp_path,'correct')['uuid']=='correct'
    for entry in (result(uuid='wrong'),result(opts='ro,noatime')):
        with patch.object(Path,'is_mount',return_value=True),patch.object(guard.subprocess,'run',return_value=entry),pytest.raises(RuntimeError):guard.verify_mount(tmp_path,'correct')


def test_initial_keys_and_config_preserve_existing_data(tmp_path):
    module=load('configure');base=tmp_path/'etc';base.mkdir();data=tmp_path/'data';(data/'core').mkdir(parents=True)
    module.configure(base,data,'11111111-2222-3333-4444-555555555555')
    config=json.loads((data/'core/gateway.json').read_text())
    assert 'RESCS_API_KEY='+config['rescs_key'] in (base/'rescs.env').read_text()
    assert 'CORE_SAFE_CHAT=1' in (base/'core.env').read_text()
    assert (base/'core.env').stat().st_mode & 0o777==0o600
    previous=(base/'rescs.env').read_bytes()
    with pytest.raises(ValueError):module.configure(base,data,'11111111-2222-3333-4444-555555555555')
    assert (base/'rescs.env').read_bytes()==previous


def test_existing_gateway_does_not_leave_half_new_configuration(tmp_path):
    module=load('configure');base=tmp_path/'etc';base.mkdir();data=tmp_path/'data';(data/'core').mkdir(parents=True)
    (data/'core/gateway.json').write_text('{}')
    with pytest.raises(ValueError):module.configure(base,data,'11111111-2222-3333-4444-555555555555')
    assert list(base.iterdir())==[]
