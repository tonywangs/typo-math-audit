"""Separately frozen, bounded baseline recovery pilot. Historical sources untouched."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import random
import re
import resource
import signal
import sys
import time

from .common import (ASSETS, canonical, check_seal, digest, file_hash, jsonl_bytes,
                     read_json, read_jsonl, seal, utcnow, write_json)
from .dataset import FAMILIES, SYMBOLS, generate, oracle
from .perturb import cases as perturb_cases, perturb
from .protocol import load_frozen
from .runner import environment, writer_lock
from .model import verify_model

FORMATS = ('integer','label','equation')
PREFIX = 'Please carefully calculate the following simple arithmetic problem below.\n{expression}\n'
SUFFIXES = dict(integer='Reply with only the integer answer. No explanation.',
                label='Reply in this format: Answer: <integer>. No explanation.',
                equation='Write only the completed equation, like 21 + 1 = 22. No explanation.')
LOCK = ASSETS / 'floor-v2-protocol.json'
NUMBER = r'[+-]?[0-9]{1,9}'


def score_response(text, expression, answer, form, truncated=False):
    """No gold-dependent extraction: gold is used only after a whole-text parse."""
    text=text.strip()
    kind='unsupported'; parsed=None
    patterns=[('integer',f'({NUMBER})'),
              ('label',rf'Answer:\s*({NUMBER})\.?'),
              ('sentence',rf'The answer is\s+({NUMBER})\.?')]
    a,op,b=expression.split()
    patterns.append(('equation',rf'{re.escape(a)}\s*{re.escape(op)}\s*{re.escape(b)}\s*=\s*({NUMBER})\.?'))
    for name,pattern in patterns:
        match=re.fullmatch(pattern,text,re.IGNORECASE|re.ASCII)
        if match:
            parsed=int(match[1]); kind=name
            break
    extracted=parsed is not None and not truncated
    strict=extracted and kind==form
    ambiguous=len(re.findall(r'(?<![\w.])[+-]?[0-9]+(?![\w.])',text,re.ASCII))>1
    diagnostic=('truncated' if truncated else 'unambiguous' if extracted else
                'potentially_ambiguous' if ambiguous else 'unsupported_format')
    return dict(candidate_answer=parsed,parsed_answer=parsed if extracted else None,
                extraction_kind=kind,extracted=extracted,strict_compliant=strict,
                correct=extracted and parsed==answer,strict_correct=strict and parsed==answer,
                diagnostic=diagnostic)


def questions(split):
    if split not in ('dev','eval'): raise ValueError('Unknown split')
    historical=generate('dev')+generate('eval')
    used={(q['family'],tuple(sorted(q['operands']))) for q in historical}
    result=[]
    for fi,family in enumerate(FAMILIES):
        pairs=[(a,b) for a in range(21) for b in range(a,21) if (family,(a,b)) not in used]
        random.Random(20260930+fi).shuffle(pairs)
        selected=pairs[:14] if split=='dev' else pairs[14:84]
        for i,(a,b) in enumerate(selected):
            if family=='subtraction': a,b=b,a
            answer={'addition':a+b,'subtraction':a-b,'multiplication':a*b}[family]
            if answer!=oracle(family,a,b): raise ValueError('Oracle disagreement')
            result.append(dict(question_id=f'v2-{split}-{family}-{i:03d}',family=family,
                               operands=[a,b],expression=f'{a} {SYMBOLS[family]} {b}',
                               answer=answer,oracle_answer=oracle(family,a,b),split=split))
    return result


def make_cases(split, selected=None):
    result=[]
    if split=='eval' and selected not in FORMATS: raise ValueError('Evaluation requires a selected format')
    for q in questions(split):
        for form in (FORMATS if selected is None else (selected,)):
            prompt=PREFIX.format(**q)+SUFFIXES[form]
            item=dict(q,prompt=prompt,prompt_sha256=digest(prompt))
            variants=[perturb(item)] if split=='dev' else list(perturb_cases([item]))
            for c in variants:
                result.append(dict(c,case_id=c['case_id']+':'+form,format=form,
                                   expression=q['expression'],operands=q['operands'],split=split))
    return result


def replay_subset(cases,split):
    if split=='dev':
        return [c for c in cases if c['format']==FORMATS[int(c['question_id'].rsplit('-',1)[1])%3]]
    return [c for c in cases if int(c['question_id'].rsplit('-',1)[1])<2]


def summarize(rows):
    summary={}
    for form in FORMATS:
        group=[r for r in rows if r['format']==form]
        summary[form]=dict(n=len(group),**{k:sum(bool(r[k]) for r in group) for k in
            ('correct','extracted','strict_compliant','strict_correct','truncated')},
            diagnostics=dict(sorted(Counter(r['diagnostic'] for r in group).items())))
    complete=len(rows)==126 and all(g['n']==42 for g in summary.values())
    passing=[f for f in FORMATS if complete and summary[f]['correct']>=11 and summary[f]['extracted']>=34]
    selected=max(passing,key=lambda f:(summary[f]['correct'],summary[f]['extracted'],-FORMATS.index(f))) if passing else None
    return dict(complete=complete,configurations=summary,selected=selected,
                decision='pass' if selected else 'fail' if complete else 'incomplete')


def source_hashes():
    return {'floor_v2.py':file_hash(Path(__file__)),
            'historical_protocol':file_hash(ASSETS/'protocol.json')}


def preregister(root):
    if LOCK.exists(): raise ValueError('Already preregistered; cannot overwrite')
    historical=load_frozen()
    root=Path(root)
    spec=dict(schema=2,historical_specification_sha256=historical['specification_sha256'],
              model=read_json(ASSETS/'model.json'),settings=dict(historical['specification']['settings'],max_new_tokens=64),
              python=historical['specification']['python'],dependencies=historical['specification']['dependencies'],
              source_sha256=source_hashes(),protocol_document_sha256=file_hash(root/'docs/floor-v2/protocol.md'),
              scoring_tests_sha256=file_hash(root/'tests/test_floor_v2.py'),
              templates={f:PREFIX+SUFFIXES[f] for f in FORMATS},
              dataset_sha256={s:digest(jsonl_bytes(questions(s))) for s in ('dev','eval')},
              pilot_cases_sha256=digest(jsonl_bytes(make_cases('dev'))),
              pilot_budget_seconds=1800,evaluation_budget_seconds=10800,
              replay_rule='dev: all 14 per family, format=index modulo 3; eval: first 2 per family x 7 conditions',
              selection='42 per format; >=11 correct and >=34 extracted; rank correct, extraction, format order')
    write_json(LOCK,dict(frozen_utc=utcnow(),specification=spec,specification_sha256=digest(canonical(spec))))
    return read_json(LOCK)


def frozen(check_environment=True):
    lock=read_json(LOCK); spec=lock['specification']
    if digest(canonical(spec))!=lock['specification_sha256']: raise ValueError('Protocol hash mismatch')
    if spec['source_sha256']!=source_hashes(): raise ValueError('Frozen sources changed')
    if read_json(ASSETS/'model.json')!=spec['model']: raise ValueError('Model manifest changed')
    if check_environment:
        load_frozen()  # Independently enforces original code and all exact dependency versions.
    if spec['dataset_sha256']!={s:digest(jsonl_bytes(questions(s))) for s in ('dev','eval')}:
        raise ValueError('Dataset drift')
    if spec['pilot_cases_sha256']!=digest(jsonl_bytes(make_cases('dev'))): raise ValueError('Pilot drift')
    return lock


class Engine:
    def __init__(self,model_dir):
        from .inference import Engine as HistoricalEngine
        self.engine=HistoricalEngine(model_dir)
        self.engine.generation.max_new_tokens=64

    def run(self,case,stop):
        result=self.engine.run(case,stop)
        # Historical engine's scores are not used for this separately frozen study.
        for key in ('parsed_answer','status','correct'): result.pop(key)
        result['truncated']=result['output_tokens']>=64 and not result['ended_with_eos']
        return dict(result,**score_response(result['completion'],case['expression'],case['answer'],
                                           case['format'],result['truncated']))


def validate(row,case,protocol_hash):
    check_seal(row)
    if row['protocol_sha256']!=protocol_hash: raise ValueError('Protocol mismatch')
    if any(row.get(k)!=v for k,v in case.items()): raise ValueError('Case mismatch')
    expected=score_response(row['completion'],case['expression'],case['answer'],case['format'],row['truncated'])
    if any(row[k]!=v for k,v in expected.items()): raise ValueError('Score mismatch')
    if row['rendered_prompt_sha256']!=digest(row['rendered_prompt']): raise ValueError('Prompt hash mismatch')
    if row['input_token_sha256']!=digest(canonical(row['input_token_ids'])): raise ValueError('Input hash mismatch')
    for name in ('input','output'):
        ids=row[name+'_token_ids']
        if row[name+'_tokens']!=len(ids) or any(type(t)!=int or t<0 for t in ids): raise ValueError('Token mismatch')
    if not 0<row['output_tokens']<=64: raise ValueError('Output length mismatch')
    if row['ended_with_eos']!=(row['output_token_ids'][-1]==2): raise ValueError('EOS mismatch')
    if row['truncated']!=(row['output_tokens']==64 and not row['ended_with_eos']): raise ValueError('Truncation mismatch')
    if not row['ended_with_eos'] and not row['truncated']: raise ValueError('Unfinished generation')
    if not 0<=row['elapsed_seconds']<10800: raise ValueError('Timing mismatch')
    from .dataset import SYSTEM
    rendered=f'<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{case["prompt"]}<|im_end|>\n<|im_start|>assistant\n'
    if row['rendered_prompt']!=rendered: raise ValueError('Unexpected chat template')


def recover(path,expected,protocol_hash):
    if not path.exists(): return []
    data=path.read_bytes()
    if data and not data.endswith(b'\n'):
        boundary=data.rfind(b'\n')+1
        write_json(path.parent/f'recovery-{time.time_ns()}.json',
                   dict(utc=utcnow(),discarded_tail_hex=data[boundary:].hex(),sha256=digest(data[boundary:])))
        with path.open('r+b') as f:
            f.truncate(boundary); f.flush(); os.fsync(f.fileno())
        data=data[:boundary]
    rows=[json.loads(line) for line in data.splitlines()]
    if len(rows)>len(expected): raise ValueError('Extra records')
    for r,c in zip(rows,expected): validate(r,c,protocol_hash)
    return rows


def run(root,model_dir,phase='pilot',pilot=None,replay=False,limit=None,engine_factory=Engine):
    lock=frozen(); start=time.perf_counter(); started=utcnow()
    if limit is not None and limit<1: raise ValueError('Positive limit required')
    split='dev' if phase=='pilot' else 'eval'
    selected=None; pilot_evidence=None
    if phase=='eval':
        if pilot is None: raise ValueError('Evaluation requires completed pilot evidence')
        audit(pilot)
        pilot_rows=read_jsonl(Path(pilot)/'outputs.jsonl'); gate=summarize(pilot_rows)
        selected=gate['selected']
        if selected is None: raise ValueError('Development gate did not pass')
        pilot_evidence=dict(outputs_sha256=file_hash(Path(pilot)/'outputs.jsonl'),gate=gate)
    expected=make_cases(split,selected)
    if replay: expected=replay_subset(expected,split)
    specification=dict(preregistration_sha256=lock['specification_sha256'],phase=phase,split=split,
                       selected=selected,pilot_evidence=pilot_evidence,replay=replay,
                       cases_sha256=digest(jsonl_bytes(expected)),
                       runtime_budget_seconds=1800 if split=='dev' or replay else 10800)
    protocol_hash=digest(canonical(specification)); root=Path(root)
    with writer_lock(root):
        verify_model(model_dir)
        path=root/'run.json'
        if path.exists():
            config=read_json(path)
            if config['specification']!=specification: raise ValueError('Run configuration changed')
            if config['protocol_sha256']!=protocol_hash or config['preregistration']!=lock:
                raise ValueError('Run metadata changed')
        else:
            config=dict(created_utc=started,specification=specification,protocol_sha256=protocol_hash,
                        preregistration=lock,environment=environment())
            write_json(path,config)
        for name,data in [('questions.jsonl',jsonl_bytes(questions(split))),('cases.jsonl',jsonl_bytes(expected))]:
            path=root/name
            if path.exists() and path.read_bytes()!=data: raise ValueError('Input artifact mismatch')
            path.write_bytes(data)
        rows=recover(root/'outputs.jsonl',expected,protocol_hash)
        if len(rows)==len(expected): return 0
        deadline=datetime.fromisoformat(config['created_utc']).timestamp()+specification['runtime_budget_seconds']
        cancelled=False
        def handler(signum,frame):
            nonlocal cancelled
            cancelled=True
        def stop(): return cancelled or time.time()>=deadline
        handlers={s:signal.signal(s,handler) for s in (signal.SIGINT,signal.SIGTERM)}
        before=len(rows); state='error'; error=None
        try:
            if stop(): raise InterruptedError()
            engine=engine_factory(str(model_dir))
            with (root/'outputs.jsonl').open('ab') as stream:
                for case in expected[before:]:
                    if stop(): raise InterruptedError()
                    result=engine.run(case,stop)
                    if stop(): raise InterruptedError()
                    row=seal(dict(case,protocol_sha256=protocol_hash,**result))
                    validate(row,case,protocol_hash)
                    stream.write(jsonl_bytes([row])); stream.flush(); os.fsync(stream.fileno()); rows.append(row)
                    print(f'{len(rows)}/{len(expected)} durable completions',flush=True)
                    if limit is not None and len(rows)-before>=limit: break
            state='complete' if len(rows)==len(expected) else 'checkpoint'
            return 0 if state=='complete' else 2
        except InterruptedError:
            state='cancelled' if cancelled else 'budget_exhausted'
            return 2
        except Exception as exc:
            error=f'{type(exc).__name__}: {exc}'
            raise
        finally:
            for s,h in handlers.items(): signal.signal(s,h)
            session=dict(started_utc=started,finished_utc=utcnow(),state=state,error=error,
                         completed_before=before,completed_after=len(rows),expected=len(expected),
                         wall_seconds=time.perf_counter()-start,
                         peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                         protocol_sha256=protocol_hash,environment=environment())
            write_json(root/f'session-{time.time_ns()}.json',session)
            write_json(root/'status.json',dict(state=state,completed=len(rows),expected=len(expected)))


def audit(root,allow_partial=False):
    root=Path(root); lock=frozen(False); config=read_json(root/'run.json'); spec=config['specification']
    if config['preregistration']!=lock: raise ValueError('Preregistration mismatch')
    if spec['preregistration_sha256']!=lock['specification_sha256']: raise ValueError('Preregistration hash mismatch')
    if spec['phase'] not in ('pilot','eval') or spec['split']!=('dev' if spec['phase']=='pilot' else 'eval'):
        raise ValueError('Phase mismatch')
    if spec['runtime_budget_seconds']!=(1800 if spec['split']=='dev' or spec['replay'] else 10800):
        raise ValueError('Budget mismatch')
    if spec['split']=='dev' and (spec['selected'] is not None or spec['pilot_evidence'] is not None):
        raise ValueError('Unexpected pilot selection')
    if spec['split']=='eval':
        evidence=spec['pilot_evidence']
        if not evidence or evidence['gate']['selected']!=spec['selected'] or evidence['gate']['decision']!='pass':
            raise ValueError('Evaluation without passing gate')
    if datetime.fromisoformat(config['created_utc'])<datetime.fromisoformat(lock['frozen_utc']):
        raise ValueError('Inference before freeze')
    ph=digest(canonical(spec))
    if ph!=config['protocol_sha256']: raise ValueError('Run hash mismatch')
    expected=make_cases(spec['split'],spec['selected'])
    if spec['replay']: expected=replay_subset(expected,spec['split'])
    if (root/'cases.jsonl').read_bytes()!=jsonl_bytes(expected): raise ValueError('Cases differ')
    if spec['cases_sha256']!=digest(jsonl_bytes(expected)): raise ValueError('Cases hash mismatch')
    if (root/'questions.jsonl').read_bytes()!=jsonl_bytes(questions(spec['split'])): raise ValueError('Questions differ')
    data=(root/'outputs.jsonl').read_bytes()
    if data and not data.endswith(b'\n'): raise ValueError('Incomplete record tail')
    rows=[json.loads(line) for line in data.splitlines()]
    if len(rows)>len(expected) or (len(rows)!=len(expected) and not allow_partial): raise ValueError('Incomplete or extra records')
    for r,c in zip(rows,expected): validate(r,c,ph)
    return dict(records=len(rows),expected=len(expected),complete=len(rows)==len(expected),
                outputs_sha256=file_hash(root/'outputs.jsonl'),protocol_sha256=ph)


def compare(reference,replay):
    audit(reference); audit(replay)
    a={r['case_id']:r for r in read_jsonl(Path(reference)/'outputs.jsonl')}
    b=read_jsonl(Path(replay)/'outputs.jsonl')
    ignored={'elapsed_seconds','record_sha256','protocol_sha256'}
    for r in b:
        if {k:v for k,v in r.items() if k not in ignored}!={k:v for k,v in a[r['case_id']].items() if k not in ignored}:
            raise ValueError('Replay differs: '+r['case_id'])
    return dict(matched_records=len(b),excluded_fields=sorted(ignored),
                reason='Subset run protocol differs by its preregistered replay flag and case inventory')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('preregister'); p.add_argument('--root',default='.')
    p=sub.add_parser('run'); p.add_argument('--model-dir',required=True); p.add_argument('--out',required=True)
    p.add_argument('--phase',choices=['pilot','eval'],default='pilot'); p.add_argument('--pilot')
    p.add_argument('--replay',action='store_true'); p.add_argument('--limit',type=int)
    for name in ('audit','gate'):
        p=sub.add_parser(name); p.add_argument('--run',required=True)
    p=sub.add_parser('compare'); p.add_argument('reference'); p.add_argument('replay')
    args=parser.parse_args(argv)
    try:
        if args.command=='preregister': print(canonical(preregister(args.root)))
        elif args.command=='run': return run(args.out,args.model_dir,args.phase,args.pilot,args.replay,args.limit)
        elif args.command=='audit': print(canonical(audit(args.run)))
        elif args.command=='gate':
            audit(args.run)
            result=summarize(read_jsonl(Path(args.run)/'outputs.jsonl'))
            print(canonical(result))
        elif args.command=='compare': print(canonical(compare(args.reference,args.replay)))
        return 0
    except (ValueError,FileNotFoundError) as exc:
        print(f'error: {exc}',file=sys.stderr); return 1


if __name__=='__main__': raise SystemExit(main())
