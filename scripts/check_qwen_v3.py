#!/usr/bin/env python3
"""Independently recompute v3 scoring, paired counts, intervals, and release pins."""
import argparse
import json
from pathlib import Path
import re
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from typo_math_audit import qwen_v3 as v
from typo_math_audit.common import digest, file_hash, read_json


def independent_parse(text,expression,truncated):
    if truncated: return None
    text=text.strip(); number=r'([+-]?[0-9]{1,9})'
    if re.fullmatch(number,text,flags=re.ASCII): return int(text)
    for prefix in ('Answer:', 'The answer is'):
        spacing = r'\s*' if prefix == 'Answer:' else r'\s+'
        match=re.fullmatch(re.escape(prefix)+spacing+number+r'\.?',text,flags=re.I|re.ASCII)
        if match: return int(match[1])
    a,op,b=expression.split()
    match=re.fullmatch(re.escape(a)+r'\s*'+re.escape(op)+r'\s*'+re.escape(b)+r'\s*=\s*'+number+r'\.?',text,re.ASCII)
    return int(match[1]) if match else None


def check(root,model_dir=None,require_replay=False):
    lock=v.frozen(); spec=lock['specification']
    assert file_hash(ROOT/'docs/qwen-v3/protocol.md')==spec['protocol_document_sha256']
    assert file_hash(ROOT/'tests/test_qwen_v3.py')==spec['tests_sha256']
    pilot=v.audit(root/'pilot'); rows=v.audit(root/'eval')
    assert v.gate(pilot)['passed']
    assert read_json(root/'pilot/run.json')['phase']=='pilot'
    assert read_json(root/'eval/run.json')['phase']=='eval'
    evidence=v.pilot_evidence(root/'pilot',pilot)
    assert read_json(root/'eval/run.json')['pilot_evidence']==evidence
    for row in pilot+rows:
        answer=independent_parse(row['completion'],row['expression'],row['truncated'])
        assert row['parsed_answer']==answer
        assert row['correct']==(answer is not None and answer==row['answer'])
        assert row['extracted']==(answer is not None)
    summary=read_json(root/'eval/summary.json')
    conditions=['clean','transpose-20','transpose-40','delete-20','delete-40','keyboard-20','keyboard-40']
    qids=sorted({r['question_id'] for r in rows})
    lookup={(r['question_id'],r['condition']):r for r in rows}
    assert len(qids)==210 and len(lookup)==1470
    matrix=np.array([[int(lookup[q,c]['correct']) for c in conditions] for q in qids])
    rng=np.random.default_rng(62103)
    indices=[]
    for family in ('addition','subtraction','multiplication'):
        positions=[i for i,q in enumerate(qids) if lookup[q,'clean']['family']==family]
        assert len(positions)==70
        indices.append(rng.choice(np.array(positions),size=(10000,70),replace=True))
    draws=np.concatenate(indices,axis=1)
    clean=matrix[:,0]
    for j,c in enumerate(conditions):
        m=summary['conditions'][c]; values=matrix[:,j]
        assert m['correct']==int(values.sum()) and m['denominator']==210
        assert m['both_correct']==int(((clean==1)&(values==1)).sum())
        broken=((clean==1)&(values==0)); recovered=((clean==0)&(values==1))
        assert m['clean_correct_to_incorrect']==int(broken.sum())
        assert m['clean_incorrect_to_correct']==int(recovered.sum())
        assert m['both_incorrect']==int(((clean==0)&(values==0)).sum())
        delta=values-clean
        assert abs(m['paired_delta']-float(delta.mean()))<1e-12
        np.testing.assert_allclose(m['paired_delta_ci95'],np.quantile(delta[draws].mean(axis=1),[.025,.975]),atol=1e-12)
        np.testing.assert_allclose(m['accuracy_ci95'],np.quantile(values[draws].mean(axis=1),[.025,.975]),atol=1e-12)
        for key in ('extracted','strict_compliant','strict_correct','truncated'):
            assert m[key]==sum(r[key] for r in rows if r['condition']==c)
        for family in ('addition','subtraction','multiplication'):
            assert m['by_family'][family]==dict(correct=sum(r['correct'] for r in rows if r['condition']==c and r['family']==family),denominator=70)
    for kind,low in [('transpose',1),('delete',3),('keyboard',5)]:
        delta=matrix[:,low+1]-matrix[:,low]
        m=summary['high_minus_low'][kind]
        assert abs(m['paired_delta']-float(delta.mean()))<1e-12
        np.testing.assert_allclose(m['paired_delta_ci95'],np.quantile(delta[draws].mean(axis=1),[.025,.975]),atol=1e-12)
    replay=None
    if require_replay or (root/'replay/run.json').exists():
        assert read_json(root/'replay/run.json')['phase']=='replay'
        assert read_json(root/'replay/run.json')['pilot_evidence']==evidence
        replay=v.compare(root/'eval',root/'replay')
        assert replay['matched_records']==42
    if model_dir:
        v.verify_model(model_dir)
        from transformers import AutoTokenizer
        tok=AutoTokenizer.from_pretrained(model_dir,local_files_only=True,trust_remote_code=False)
        for r in pilot+rows:
            assert tok(r['rendered_prompt'],add_special_tokens=False)['input_ids']==r['input_token_ids']
            assert tok.decode(r['output_token_ids'],skip_special_tokens=True,clean_up_tokenization_spaces=False)==r['completion']
            assert tok.decode(r['output_token_ids'],skip_special_tokens=False,clean_up_tokenization_spaces=False)==r['raw_completion']
    return dict(pilot=v.gate(pilot),evaluation_records=len(rows),independent_statistics=True,
                replay=replay,tokenization_checked=bool(model_dir))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT/'results/qwen-v3')
    p.add_argument('--model-dir',type=Path)
    p.add_argument('--require-replay',action='store_true')
    a=p.parse_args(); print(json.dumps(check(a.root,a.model_dir,a.require_replay),sort_keys=True))
