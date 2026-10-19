import copy
import json
from pathlib import Path
import pytest
from typo_math_audit import qwen_v3 as v
from typo_math_audit.common import canonical, digest, jsonl_bytes, seal
from typo_math_audit.dataset import generate, SYSTEM
from typo_math_audit.perturb import CONDITIONS, KINDS


def row(case, text='7', tokens=None, truncated=False):
    if tokens is None: tokens=[22,151645]
    rendered='<|im_start|>system\n'+SYSTEM+'<|im_end|>\n<|im_start|>user\n'+case['prompt']+'<|im_end|>\n<|im_start|>assistant\n'
    return seal(dict(case, protocol_sha256='test', completion=text, raw_completion=text+'<|im_end|>',
        rendered_prompt=rendered, rendered_prompt_sha256=digest(rendered),
        input_token_ids=[1,2], input_tokens=2,input_token_sha256=digest(canonical([1,2])),
        output_token_ids=tokens,output_tokens=len(tokens),ended_with_eos=tokens[-1]==151645,
        truncated=truncated,elapsed_seconds=.5,
        **v.score_response(text,case['expression'],case['answer'],'integer',truncated)))


def test_inputs_disjoint_and_protected():
    pilot=v.cases('pilot'); evaluation=v.cases('eval'); replay=v.cases('replay')
    assert len(pilot)==42 and len(evaluation)==1470 and len(replay)==42
    identity=lambda r:(r['family'],tuple(sorted(r['operands'])))
    old={identity(r) for r in generate('dev')+generate('eval')}
    assert not ({identity(r) for r in pilot}&{identity(r) for r in evaluation})
    assert not (old&{identity(r) for r in pilot+evaluation})
    for i in range(0,len(evaluation),7):
        group=evaluation[i:i+7]
        assert [c['condition'] for c in group]==list(CONDITIONS)
        for c in group:
            assert c['expression'] in c['prompt']
            assert c['prompt'].endswith('Reply with only the integer answer. No explanation.')
            assert c['eligible_words']==5
            assert c['changed_words']==(0 if c['condition']=='clean' else 1 if c['condition'].endswith('20') else 2)
        for j in (1,3,5):
            assert all(e in group[j+1]['edits'] for e in group[j]['edits'])


def test_gate_boundary():
    rows=[dict(correct=i<34,extracted=i<38) for i in range(42)]
    assert v.gate(rows)['passed']
    assert not v.gate(rows[:-1])['passed']
    rows[33]['correct']=False
    assert not v.gate(rows)['passed']
    rows[33]['correct']=True; rows[37]['extracted']=False
    assert not v.gate(rows)['passed']


@pytest.mark.parametrize('text,extracted', [('7',True),('Answer: 7.',True),('The answer is 7',True),
    ('I think 7',False),('7 or 8',False),('7.0',False),('**7**',False),('７',False)])
def test_scorer(text,extracted):
    c=v.cases('pilot')[0]; r=row(c,text)
    assert r['extracted']==extracted
    v.validate(r,c,'test')


def test_corruption_is_rejected_even_if_resealed():
    c=v.cases('pilot')[0]; good=row(c)
    for field,value in [('correct',not good['correct']),('rendered_prompt','wrong'),
        ('output_token_ids',[22,2]),('input_token_sha256','wrong'),('protocol_sha256','wrong')]:
        bad=dict(good); bad[field]=value; bad.pop('record_sha256'); bad=seal(bad)
        with pytest.raises(ValueError): v.validate(bad,c,'test')


def test_truncation_never_scored():
    c=v.cases('pilot')[0]; r=row(c,str(c['answer']),[22]*64,True)
    v.validate(r,c,'test')
    assert not r['correct'] and not r['extracted']


def test_torn_tail_only_recovery(tmp_path):
    path=tmp_path/'outputs.jsonl'; path.write_bytes(b'{"complete":true}\n{"partial":')
    v.recover_tail(tmp_path)
    assert path.read_bytes()==b'{"complete":true}\n'
    assert len(list(tmp_path.glob('recovery-*.json')))==1
    path.write_bytes(b'broken\n')
    v.recover_tail(tmp_path)
    assert path.read_bytes()==b'broken\n'  # Complete corrupt rows are never silently dropped.


def test_wilson_edges():
    assert v.wilson(0,0)==[None,None]
    assert v.wilson(0,210)[0]==0
    assert .017<v.wilson(0,210)[1]<.019
    assert v.wilson(210,210)[1]==1
    assert .981<v.wilson(210,210)[0]<.983


def test_paired_statistics_known_transitions():
    records=[]
    # 2 per family: clean one correct; high rate reverses it, low destroys it.
    for f in ('addition','subtraction','multiplication'):
        for i in range(2):
            for condition in CONDITIONS:
                correct=(i==0 if condition=='clean' else i==1 if condition.endswith('40') else False)
                records.append(dict(question_id=f'{f}-{i}',family=f,condition=condition,correct=correct,
                    extracted=True,strict_correct=correct,strict_compliant=True,truncated=False,
                    unchanged=condition=='clean',possible_meaning_change=condition!='clean',
                    realized_eligible_word_rate=0.,realized_all_word_rate=0.,input_tokens=1,output_tokens=1,
                    elapsed_seconds=.1))
    summary=v.statistics(records)
    for kind in KINDS:
        low=summary['conditions'][kind+'-20']; high=summary['conditions'][kind+'-40']
        assert low['paired_delta']==-.5 and high['paired_delta']==0
        assert high['clean_correct_to_incorrect']==3 and high['clean_incorrect_to_correct']==3
        assert summary['high_minus_low'][kind]['paired_delta']==.5


def test_token_validation_rejects_inconsistent_text(monkeypatch):
    import transformers
    class Tokenizer:
        def __call__(self,*args,**kwargs): return dict(input_ids=[1,2])
        def decode(self,tokens,skip_special_tokens,**kwargs):
            return '7' if skip_special_tokens else '7<|im_end|>'
    monkeypatch.setattr(transformers.AutoTokenizer,'from_pretrained',lambda *a,**k:Tokenizer())
    c=v.cases('pilot')[0]; good=row(c)
    v.verify_tokens([good],'unused')
    for key,value in [('input_token_ids',[1,3]),('completion','8'),('raw_completion','8<|im_end|>')]:
        bad=dict(good); bad[key]=value
        with pytest.raises(ValueError): v.verify_tokens([bad],'unused')


def test_audit_requires_passing_prior_pilot(tmp_path,monkeypatch):
    from typo_math_audit.common import write_json
    monkeypatch.setattr(v,'frozen',lambda:dict(specification_sha256='test',frozen_utc='2026-01-01T00:00:00+00:00'))
    def prepare(folder,phase,start,end):
        folder.mkdir()
        items=v.cases(phase)
        (folder/'cases.jsonl').write_bytes(jsonl_bytes(items))
        (folder/'outputs.jsonl').write_bytes(jsonl_bytes([row(c,str(c['answer'])) for c in items]))
        write_json(folder/'run.json',dict(phase=phase,protocol_sha256='test',created_utc=start,
            budget_seconds=1800 if phase=='pilot' else 10800,pilot_evidence=None))
        write_json(folder/'status.json',dict(complete=True,records=len(items),completed_utc=end))
    pilot=tmp_path/'pilot'; evaluation=tmp_path/'eval'
    prepare(pilot,'pilot','2026-01-02T00:00:00+00:00','2026-01-02T00:01:00+00:00')
    prepare(evaluation,'eval','2026-01-02T00:02:00+00:00','2026-01-02T00:03:00+00:00')
    with pytest.raises(ValueError,match='provenance'): v.audit(evaluation)
    meta=json.loads((evaluation/'run.json').read_text())
    meta['pilot_evidence']=v.pilot_evidence(pilot,v.audit(pilot)); write_json(evaluation/'run.json',meta)
    assert len(v.audit(evaluation))==1470
    meta['created_utc']='2026-01-02T00:00:30+00:00'; write_json(evaluation/'run.json',meta)
    with pytest.raises(ValueError,match='predates pilot'): v.audit(evaluation)


def test_frozen_document_pin_checked(tmp_path,monkeypatch):
    from typo_math_audit.common import write_json
    monkeypatch.setattr(v,'LOCK',tmp_path/'lock.json')
    root=Path(__file__).resolve().parents[1]
    v.freeze(root)
    lock=v.frozen(); lock['specification']['protocol_document_sha256']='bad'
    lock['specification_sha256']=digest(canonical(lock['specification']))
    write_json(v.LOCK,lock)
    with pytest.raises(ValueError,match='document drift'): v.frozen()
