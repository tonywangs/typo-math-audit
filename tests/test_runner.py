import json
import os
import signal
from pathlib import Path
import pytest
from typo_math_audit import runner
from typo_math_audit.common import canonical,digest,read_json,read_jsonl,seal,write_json
from typo_math_audit.scoring import score
from typo_math_audit.audit import audit_run,compare_runs


class FakeEngine:
    def __init__(self,model_dir): pass
    def run(self,case,stop):
        text=str(case['answer'])
        return dict(rendered_prompt=case['prompt'],rendered_prompt_sha256=digest(case['prompt']),
                    input_token_ids=[1,2],input_token_sha256=digest(canonical([1,2])),input_tokens=2,
                    output_token_ids=[3,0],output_tokens=2,raw_completion=text+'<eos>',completion=text,
                    ended_with_eos=True,truncated=False,elapsed_seconds=.1,**score(text,case['answer']))


@pytest.fixture(autouse=True)
def bypass_model(monkeypatch):
    monkeypatch.setattr(runner,'verify_model',lambda _:None)


def invoke(path,limit=None,engine=FakeEngine):
    return runner.run(path,'unused',split='dev',pilot=True,limit=limit,engine_factory=engine)


def test_checkpoint_resume_and_exact_replay(tmp_path):
    root=tmp_path/'run'
    assert invoke(root,3)==2
    prefix=(root/'outputs.jsonl').read_bytes()
    assert invoke(root)==0
    assert (root/'outputs.jsonl').read_bytes().startswith(prefix)
    assert audit_run(root)['records']==210
    assert invoke(root)==0
    other=tmp_path/'other'
    assert invoke(other)==0
    assert compare_runs(root,other)['matched_records']==210


def test_torn_tail_recovery_and_complete_record_corruption(tmp_path):
    assert invoke(tmp_path,1)==2
    with (tmp_path/'outputs.jsonl').open('ab') as f: f.write(b'{"unfinished":')
    assert invoke(tmp_path,1)==2
    assert len(read_jsonl(tmp_path/'outputs.jsonl'))==2
    assert len(list(tmp_path.glob('recovery-*.json')))==1
    with (tmp_path/'outputs.jsonl').open('ab') as f: f.write(b'{invalid}\n')
    with pytest.raises(json.JSONDecodeError): invoke(tmp_path)


def test_signal_cancels_without_scoring_partial_generation(tmp_path):
    class CancelEngine(FakeEngine):
        def run(self,case,stop):
            os.kill(os.getpid(),signal.SIGTERM)
            assert stop()
            raise InterruptedError()
    before=signal.getsignal(signal.SIGTERM)
    assert invoke(tmp_path,engine=CancelEngine)==2
    assert read_json(tmp_path/'status.json')['state']=='cancelled'
    assert read_jsonl(tmp_path/'outputs.jsonl')==[]
    assert signal.getsignal(signal.SIGTERM)==before
    assert invoke(tmp_path,1)==2
    assert len(read_jsonl(tmp_path/'outputs.jsonl'))==1


def test_budget_exhaustion_is_persisted(tmp_path):
    assert invoke(tmp_path,1)==2
    cfg=read_json(tmp_path/'run.json');cfg['created_utc']='2000-01-01T00:00:00+00:00'
    write_json(tmp_path/'run.json',cfg)
    assert invoke(tmp_path)==2
    assert read_json(tmp_path/'status.json')['state']=='budget_exhausted'
    assert len(read_jsonl(tmp_path/'outputs.jsonl'))==1


def test_wrong_config_or_corrupted_inputs_refused(tmp_path):
    invoke(tmp_path,1)
    original=(tmp_path/'cases.jsonl').read_bytes()
    (tmp_path/'cases.jsonl').write_bytes(original+b'\n')
    with pytest.raises(ValueError,match='Input artifact'): invoke(tmp_path)
    (tmp_path/'cases.jsonl').write_bytes(original)
    rows=read_jsonl(tmp_path/'outputs.jsonl');rows[0]['correct']=not rows[0]['correct']
    from typo_math_audit.common import jsonl_bytes
    (tmp_path/'outputs.jsonl').write_bytes(jsonl_bytes(rows))
    with pytest.raises(ValueError,match='integrity'): invoke(tmp_path)


def test_one_writer(tmp_path):
    with runner.writer_lock(tmp_path):
        with pytest.raises(ValueError,match='Another writer'):
            with runner.writer_lock(tmp_path): pass


def test_pilot_rejects_evaluation(tmp_path):
    with pytest.raises(ValueError,match='development'):
        runner.run(tmp_path,'unused',split='eval',pilot=True)


def test_missing_results_not_reported_complete(tmp_path):
    invoke(tmp_path,8)
    with pytest.raises(ValueError,match='Incomplete'): audit_run(tmp_path)
    assert audit_run(tmp_path,True)['records']==8
    rows=read_jsonl(tmp_path/'outputs.jsonl')
    from typo_math_audit.analysis import summarize
    summary=summarize(rows,replicates=20)
    assert summary['question_clusters']==1
    assert summary['excluded_records']==1
    assert summary['excluded_incomplete_questions']==1
