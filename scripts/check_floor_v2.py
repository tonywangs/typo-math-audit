#!/usr/bin/env python3
"""Independent gate/count recomputation, historical diagnosis, and release audit.

--write creates scientific summaries from immutable raw records. Default verifies.
No production extraction or summary function is used to compute expected counts.
"""
import argparse
from collections import Counter
from datetime import datetime
import json
import re
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from typo_math_audit.common import file_hash,read_json,read_jsonl,write_json
from typo_math_audit.floor_v2 import audit,compare,frozen,FORMATS


def integer(text):
    body=text[1:] if text[:1] in ('+','-') else text
    if 1<=len(body)<=9 and body.isascii() and body.isdecimal(): return int(text)
    return None


def independent_parse(text,expression):
    text=text.strip()
    value=integer(text)
    if value is not None:return value,'integer'
    lowered=text.lower()
    for prefix,kind in [('answer:','label'),('the answer is','sentence')]:
        if lowered.startswith(prefix):
            suffix=text[len(prefix):]
            if kind=='sentence' and (not suffix or suffix[0] not in ' \t\n\r\f\v'):continue
            suffix=suffix.lstrip(' \t\n\r\f\v')
            if suffix.endswith('.'):suffix=suffix[:-1]
            value=integer(suffix)
            if value is not None:return value,kind
    left,sep,right=text.partition('=')
    if sep and '=' not in right:
        a,op,b=expression.split()
        x,found,y=left.partition(op)
        if found and x.strip(' \t\n\r\f\v')==a and y.strip(' \t\n\r\f\v')==b:
            right=right.lstrip(' \t\n\r\f\v')
            if right.endswith('.'):right=right[:-1]
            value=integer(right)
            if value is not None:return value,'equation'
    return None,'unsupported'


def compute(rows):
    result={}
    for form in FORMATS:
        group=[r for r in rows if r['format']==form]
        counts=Counter()
        for r in group:
            a,b=r['operands']
            independent_gold={'addition':a+b,'subtraction':a-b,'multiplication':a*b}[r['family']]
            if independent_gold!=r['answer']:raise ValueError('Arithmetic answer disagreement')
            parsed,kind=independent_parse(r['completion'],r['expression'])
            extracted=parsed is not None and not r['truncated']
            correct=extracted and parsed==r['answer']
            strict=extracted and kind==form
            expected=dict(candidate_answer=parsed,parsed_answer=parsed if extracted else None,
                          extraction_kind=kind,extracted=extracted,correct=correct,
                          strict_compliant=strict,strict_correct=strict and correct)
            for key,value in expected.items():
                if r[key]!=value:raise ValueError(f'Independent parser disagreement {r["case_id"]}: {key}')
            counts['correct']+=correct;counts['extracted']+=extracted
            counts['strict_compliant']+=strict;counts['strict_correct']+=strict and correct
            counts['truncated']+=r['truncated']
            counts['extracted_wrong']+=extracted and not correct
            counts['unsupported_nontruncated']+=not extracted and not r['truncated']
        result[form]=dict(n=len(group),**{k:counts[k] for k in
            ('correct','extracted','strict_compliant','strict_correct','truncated','extracted_wrong','unsupported_nontruncated')})
    complete=len(rows)==126 and all(c['n']==42 for c in result.values())
    passed=[f for f in FORMATS if complete and result[f]['correct']/42>=.25 and result[f]['extracted']/42>=.8]
    selected=sorted(passed,key=lambda f:(-result[f]['correct'],-result[f]['extracted'],FORMATS.index(f)))[0] if passed else None
    return dict(complete=complete,configurations=result,selected=selected,
                decision='pass' if selected else 'fail' if complete else 'incomplete')


def history():
    result={}
    for name in ('pilot','final'):
        root=ROOT/'results'/name
        questions={r['question_id']:r for r in read_jsonl(root/'questions.jsonl')}
        rows=read_jsonl(root/'outputs.jsonl')
        counts=Counter(); examples=[]
        for r in rows:
            q=questions[r['question_id']]
            parsed,kind=independent_parse(r['completion'],q['expression'])
            counts['original_'+r['status']]+=1
            if r['truncated']:category='truncated_not_assessed'
            elif parsed is None:category='unsupported_not_assessed'
            elif parsed==r['answer']:category='whole_response_grammar_correct'
            else:category='whole_response_grammar_wrong'
            counts[category]+=1
            if len(examples)<12 and (parsed is not None or r['truncated']):
                examples.append(dict(case_id=r['case_id'],completion=r['completion'],truncated=r['truncated'],
                                     original_status=r['status'],original_correct=r['correct'],
                                     diagnostic_category=category,extraction_kind=kind))
        result[name]=dict(records=len(rows),original_correct=sum(r['correct'] for r in rows),
                          outputs_sha256=file_hash(root/'outputs.jsonl'),counts=dict(sorted(counts.items())),examples=examples)
    return dict(note='Post-hoc descriptive diagnosis only. Original scores remain authoritative for v1. '
                'Unsupported text is not automatically incorrect arithmetic; no broad prose extraction or typo effect is inferred.',runs=result)


def verify_tokens(model_dir,root):
    from typo_math_audit.model import verify_model
    verify_model(model_dir)
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(model_dir,local_files_only=True,trust_remote_code=False)
    for r in read_jsonl(root/'outputs.jsonl'):
        ids=tokenizer(r['rendered_prompt'],add_special_tokens=False)['input_ids']
        if ids!=r['input_token_ids']:raise ValueError('Retokenized prompt differs')
        for key,skip in [('completion',True),('raw_completion',False)]:
            decoded=tokenizer.decode(r['output_token_ids'],skip_special_tokens=skip,clean_up_tokenization_spaces=False)
            if decoded!=r[key]:raise ValueError('Decoded output differs')


def main():
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true')
    p.add_argument('--model-dir');p.add_argument('--require-replay',action='store_true')
    args=p.parse_args()
    root=ROOT/'results/floor-v2';lock=frozen(False)
    baseline=read_json(root/'historical-artifacts.json')
    for name,entry in baseline['files'].items():
        if name not in ('README.md','pyproject.toml') and file_hash(ROOT/name)!=entry['sha256']:
            raise ValueError('Historical artifact changed: '+name)
    if file_hash(ROOT/'docs/floor-v2/protocol.md')!=lock['specification']['protocol_document_sha256']:
        raise ValueError('Protocol document changed')
    if file_hash(ROOT/'tests/test_floor_v2.py')!=lock['specification']['scoring_tests_sha256']:
        raise ValueError('Preregistered tests changed')
    if file_hash(root/'reserved-evaluation-questions.jsonl')!=lock['specification']['dataset_sha256']['eval']:
        raise ValueError('Reserved evaluation inputs changed')
    evidence=audit(root/'pilot')
    rows=read_jsonl(root/'pilot/outputs.jsonl');summary=compute(rows)
    # Cross-check production gate only after completing independent computation.
    from typo_math_audit.floor_v2 import summarize
    production=summarize(rows)
    if read_json(root/'gate.json')!=production:raise ValueError('Saved gate decision differs')
    if production['selected'] is None and (root/'final').exists():
        raise ValueError('Evaluation exists despite failed gate')
    for form in FORMATS:
        diagnostics=Counter()
        for r in (row for row in rows if row['format']==form):
            value,_=independent_parse(r['completion'],r['expression'])
            numbers=re.findall(r'(?<![\w.])[+-]?[0-9]+(?![\w.])',r['completion'].strip(),re.ASCII)
            category=('truncated' if r['truncated'] else 'unambiguous' if value is not None else
                      'potentially_ambiguous' if len(numbers)>1 else 'unsupported_format')
            if category!=r['diagnostic']:raise ValueError('Diagnostic flag differs')
            diagnostics[category]+=1
        if dict(diagnostics)!=production['configurations'][form]['diagnostics']:
            raise ValueError('Diagnostic counts differ')
    for k in ('complete','selected','decision'):
        if production[k]!=summary[k]:raise ValueError('Independent gate disagreement')
    for f in FORMATS:
        for k in ('n','correct','extracted','strict_compliant','strict_correct','truncated'):
            if production['configurations'][f][k]!=summary['configurations'][f][k]:raise ValueError('Count disagreement')
    sessions=[read_json(p) for p in sorted((root/'pilot').glob('session-*.json'))]
    summary['measurement']=dict(wall_seconds=sum(s['wall_seconds'] for s in sessions),
        peak_process_rss_kib=max(s['peak_process_rss_kib'] for s in sessions),
        generated_tokens=sum(r['output_tokens'] for r in rows),
        summed_generation_seconds=sum(r['elapsed_seconds'] for r in rows),sessions=len(sessions))
    summary['evidence']=evidence
    for name,value in [('summary.json',summary),('historical-diagnosis.json',history())]:
        path=root/name
        if args.write:write_json(path,value)
        elif read_json(path)!=value:raise ValueError('Independent recomputation differs: '+name)
    if args.require_replay or (root/'offline-replay/outputs.jsonl').exists():
        result=compare(root/'pilot',root/'offline-replay')
        if result['matched_records']!=42:raise ValueError('Replay subset incomplete')
        path=root/'replay-verification.json'
        result.update(reference_sha256=file_hash(root/'pilot/outputs.jsonl'),
                      replay_sha256=file_hash(root/'offline-replay/outputs.jsonl'))
        if args.write:write_json(path,result)
        elif read_json(path)!=result:raise ValueError('Replay evidence differs')
    if args.model_dir:
        for name in ('pilot','offline-replay'):
            if (root/name/'outputs.jsonl').exists():verify_tokens(args.model_dir,root/name)
    print(json.dumps(summary,sort_keys=True))


if __name__=='__main__':main()
