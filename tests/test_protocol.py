import copy
import pytest
from typo_math_audit import protocol
from typo_math_audit.common import canonical,digest,write_json


def test_frozen_protocol_refuses_drift(tmp_path,monkeypatch):
    spec=protocol.specification()
    write_json(tmp_path/'protocol.json',dict(specification=spec,specification_sha256=digest(canonical(spec))))
    monkeypatch.setattr(protocol,'ASSETS',tmp_path)
    monkeypatch.setattr(protocol,'specification',lambda:spec)
    assert protocol.load_frozen()['specification']==spec
    changed=copy.deepcopy(spec);changed['settings']['max_new_tokens']+=1
    monkeypatch.setattr(protocol,'specification',lambda:changed)
    with pytest.raises(ValueError,match='differs'): protocol.load_frozen()
    monkeypatch.setattr(protocol,'specification',lambda:spec)
    write_json(tmp_path/'protocol.json',dict(specification=spec,specification_sha256='0'*64))
    with pytest.raises(ValueError,match='hash mismatch'): protocol.load_frozen()


def test_freeze_cannot_overwrite(tmp_path,monkeypatch):
    from typo_math_audit import cli
    (tmp_path/'protocol.json').write_text('{}')
    monkeypatch.setattr(cli,'ASSETS',tmp_path)
    assert cli.main(['freeze','--pilot','unused'])==1
    assert (tmp_path/'protocol.json').read_text()=='{}'
