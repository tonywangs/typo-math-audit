import json
import pytest
from typo_math_audit import model
from typo_math_audit.common import digest


def test_model_hashes_not_just_existence(tmp_path,monkeypatch):
    assets=tmp_path/'assets';assets.mkdir()
    weights=tmp_path/'weights';weights.mkdir()
    data=b'known bytes'
    (weights/'model.safetensors').write_bytes(data)
    manifest=dict(files={'model.safetensors':dict(bytes=len(data),sha256=digest(data))})
    (assets/'model.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(model,'ASSETS',assets)
    assert model.verify_model(weights)==manifest
    (weights/'model.safetensors').write_bytes(b'wrong bytes')
    with pytest.raises(ValueError,match='corrupt'): model.verify_model(weights)
    (weights/'model.safetensors').unlink()
    with pytest.raises(ValueError,match='missing'): model.verify_model(weights)


def test_acquisition_verifies_before_rename(tmp_path,monkeypatch):
    import io
    assets=tmp_path/'assets';assets.mkdir()
    manifest=dict(repo_id='example/model',revision='a'*40,files={'config.json':dict(bytes=2,sha256=digest(b'{}'))})
    (assets/'model.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(model,'ASSETS',assets)
    monkeypatch.setattr(model.urllib.request,'urlopen',lambda *a,**kw:io.BytesIO(b'xx'))
    with pytest.raises(ValueError,match='hash mismatch'): model.acquire(tmp_path/'weights')
    assert not (tmp_path/'weights/config.json').exists()
    monkeypatch.setattr(model.urllib.request,'urlopen',lambda *a,**kw:io.BytesIO(b'{}'))
    model.acquire(tmp_path/'weights')
    assert (tmp_path/'weights/config.json').read_bytes()==b'{}'
