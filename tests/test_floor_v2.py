"""Expected cases authored from the protocol, before implementing its parser."""
import json
from pathlib import Path
import pytest
from typo_math_audit import floor_v2 as v2

# These expected answers do not use the production parser to generate expectations.
@pytest.mark.parametrize('text,parsed,kind', [
    ('13',13,'integer'), ('  +13\n',13,'integer'), ('-13',-13,'integer'),
    ('Answer: 13',13,'label'), ('answer: +13.',13,'label'),
    ('The answer is 13.',13,'sentence'), ('4 + 9 = 13',13,'equation'),
    ('4+9=12.',12,'equation'), ('4 + 9 = -5',-5,'equation'),
    ('Answer: 00013',13,'label'),
    ('13 or 14',None,'unsupported'), ('Answer: 13\nAnswer: 14',None,'unsupported'),
    ('Answer: 13\nActually 14',None,'unsupported'), ('13.0',None,'unsupported'),
    ('1,300',None,'unsupported'), ('１３',None,'unsupported'),
    ('**13**',None,'unsupported'), ('```13```',None,'unsupported'),
    ('\\boxed{13}',None,'unsupported'), ('The sum is 13.',None,'unsupported'),
    ('4 + 9 = 13 = 14',None,'unsupported'), ('9 + 4 = 13',None,'unsupported'),
    ('4 - 9 = 13',None,'unsupported'), ('4 + 9 =',None,'unsupported'),
    ('Answer: 13. Next question?',None,'unsupported'), ('',None,'unsupported'),
    ('9999999999',None,'unsupported'), ('13\x00',None,'unsupported'),
    ('Answer: 1e3',None,'unsupported'), ('13%',None,'unsupported'),
])
def test_scoring_adversaries(text,parsed,kind):
    result=v2.score_response(text,'4 + 9',13,'integer',False)
    assert result['candidate_answer']==parsed
    assert result['extraction_kind']==kind
    assert result['correct']==(parsed==13)
    truncated=v2.score_response(text,'4 + 9',13,'integer',True)
    assert not truncated['correct'] and not truncated['extracted']
    assert truncated['parsed_answer'] is None


def test_strict_separate_from_accuracy():
    assert v2.score_response('4+9=13','4 + 9',13,'equation')['strict_correct']
    r=v2.score_response('The answer is 13.','4 + 9',13,'label')
    assert r['correct'] and not r['strict_compliant']
    r=v2.score_response('Answer: 12','4 + 9',13,'label')
    assert r['extracted'] and r['strict_compliant'] and not r['correct']


def test_split_and_perturbation_invariants():
    from typo_math_audit.dataset import generate
    from typo_math_audit.perturb import apply_edits
    def keys(rows):
        return {(r['family'],tuple(sorted(r['operands']))) for r in rows}
    old=keys(generate('dev')+generate('eval'))
    dev=v2.questions('dev'); final=v2.questions('eval')
    assert len(dev)==42 and len(final)==210
    assert not old&keys(dev) and not old&keys(final) and not keys(dev)&keys(final)
    for form in v2.FORMATS:
        cases=v2.make_cases('eval',form)
        assert len(cases)==1470
        clean={r['question_id']:r['prompt'] for r in cases if r['condition']=='clean'}
        for r in cases:
            assert r['expression'] in r['prompt']
            assert r['prompt']==apply_edits(clean[r['question_id']],r['edits'])
            assert r['eligible_words']==5
            assert r['changed_words'] in (0,1,2)
            assert r['prompt'].splitlines()[-1]==v2.SUFFIXES[form]


def fake_rows(correct=11,extracted=34):
    return [dict(format=f,correct=i<correct,extracted=i<extracted,
                 strict_compliant=False,strict_correct=False,truncated=False,
                 diagnostic='unambiguous' if i<extracted else 'unsupported_format')
            for i in range(42) for f in v2.FORMATS]


def test_gate_boundaries_and_no_incomplete_pass():
    assert v2.summarize(fake_rows())['selected']=='integer'
    assert v2.summarize(fake_rows(correct=10))['selected'] is None
    assert v2.summarize(fake_rows(extracted=33))['selected'] is None
    assert v2.summarize(fake_rows()[:-1])['selected'] is None


def test_replay_stratification():
    cases=v2.make_cases('dev')
    selected=v2.replay_subset(cases,'dev')
    from collections import Counter
    assert len(selected)==42
    assert set(Counter((r['family'],r['format']) for r in selected).values())=={4,5}
    assert len({r['question_id'] for r in selected})==42
    selected=v2.replay_subset(v2.make_cases('eval','integer'),'eval')
    assert len(selected)==42
    assert set(Counter((r['family'],r['condition']) for r in selected).values())=={2}


class FakeEngine:
    def __init__(self,model_dir): pass
    def run(self,case,stop):
        from typo_math_audit.dataset import SYSTEM
        from typo_math_audit.common import digest,canonical
        text=str(case['answer'])
        rendered=f'<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{case["prompt"]}<|im_end|>\n<|im_start|>assistant\n'
        return dict(rendered_prompt=rendered,rendered_prompt_sha256=digest(rendered),
                    input_token_ids=[1],input_token_sha256=digest(canonical([1])),input_tokens=1,
                    output_token_ids=[3,2],output_tokens=2,raw_completion=text+'<|im_end|>',
                    completion=text,ended_with_eos=True,truncated=False,elapsed_seconds=.1,
                    **v2.score_response(text,case['expression'],case['answer'],case['format']))


@pytest.fixture
def runner_env(tmp_path,monkeypatch):
    from typo_math_audit.common import write_json,canonical,digest
    spec={'source_sha256':v2.source_hashes()}
    lock=dict(frozen_utc='2026-01-01T00:00:00+00:00',specification=spec,
              specification_sha256=digest(canonical(spec)))
    monkeypatch.setattr(v2,'frozen',lambda *a:lock)
    monkeypatch.setattr(v2,'verify_model',lambda p:None)
    return tmp_path


def invoke(path,limit=None,engine=FakeEngine,**kw):
    return v2.run(path,'unused',limit=limit,engine_factory=engine,**kw)


def test_checkpoint_recovery_corruption(runner_env):
    from typo_math_audit.common import read_jsonl,jsonl_bytes
    p=runner_env
    assert invoke(p,1)==2
    prefix=(p/'outputs.jsonl').read_bytes()
    with (p/'outputs.jsonl').open('ab') as f:f.write(b'{broken')
    assert invoke(p,1)==2
    assert (p/'outputs.jsonl').read_bytes().startswith(prefix)
    assert len(list(p.glob('recovery-*.json')))==1
    assert invoke(p)==0
    assert v2.audit(p)['records']==126
    rows=read_jsonl(p/'outputs.jsonl');rows[0]['correct']=not rows[0]['correct']
    (p/'outputs.jsonl').write_bytes(jsonl_bytes(rows))
    with pytest.raises(ValueError,match='integrity'):invoke(p)


def test_cancellation_budget_and_restore(runner_env):
    import os,signal
    from typo_math_audit.common import read_json,read_jsonl,write_json
    class Cancel(FakeEngine):
        def run(self,case,stop):
            os.kill(os.getpid(),signal.SIGTERM)
            assert stop()
            raise InterruptedError()
    p=runner_env
    old=signal.getsignal(signal.SIGTERM)
    assert invoke(p,engine=Cancel)==2
    assert signal.getsignal(signal.SIGTERM)==old
    assert read_json(p/'status.json')['state']=='cancelled'
    assert read_jsonl(p/'outputs.jsonl')==[]
    assert invoke(p,1)==2
    cfg=read_json(p/'run.json');cfg['created_utc']='2000-01-01T00:00:00+00:00'
    write_json(p/'run.json',cfg)
    assert invoke(p)==2
    assert read_json(p/'status.json')['state']=='budget_exhausted'
    assert len(read_jsonl(p/'outputs.jsonl'))==1


def test_replay_and_gate_enforcement(runner_env):
    p=runner_env
    assert invoke(p/'main')==0
    assert invoke(p/'replay',replay=True)==0
    assert v2.compare(p/'main',p/'replay')['matched_records']==42
    assert invoke(p/'incomplete',1)==2
    with pytest.raises(ValueError,match='Incomplete'):invoke(p/'eval',phase='eval',pilot=p/'incomplete')
    # Complete but deliberately wrong answers fail even if format extraction is perfect.
    class Wrong(FakeEngine):
        def run(self,case,stop):
            altered=dict(case,answer=999)
            result=super().run(altered,stop)
            result.update(v2.score_response('999',case['expression'],case['answer'],case['format']))
            return result
    assert invoke(p/'wrong',engine=Wrong)==0
    with pytest.raises(ValueError,match='gate did not pass'):invoke(p/'eval',phase='eval',pilot=p/'wrong')


def test_integrity_audit_and_lock(runner_env):
    from typo_math_audit.common import read_jsonl,jsonl_bytes,seal
    p=runner_env
    with v2.writer_lock(p):
        with pytest.raises(ValueError,match='Another writer'):invoke(p,1)
    assert invoke(p)==0
    original=(p/'outputs.jsonl').read_bytes()
    rows=read_jsonl(p/'outputs.jsonl')
    for field,value in [('parsed_answer',999),('truncated',True),('rendered_prompt','altered'),('ended_with_eos',False)]:
        bad=dict(rows[0]);bad.pop('record_sha256');bad[field]=value
        (p/'outputs.jsonl').write_bytes(jsonl_bytes([seal(bad)]+rows[1:]))
        with pytest.raises(ValueError):v2.audit(p)
    (p/'outputs.jsonl').write_bytes(original+b'{oops')
    with pytest.raises(ValueError,match='tail'):v2.audit(p)
