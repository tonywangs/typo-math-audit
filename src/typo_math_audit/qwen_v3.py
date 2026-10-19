"""Separately frozen Qwen model replacement; preserves both historical studies."""
from __future__ import annotations
import argparse
from datetime import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import signal
import sys
import time
import urllib.request

from .common import (ASSETS, canonical, check_seal, digest, file_hash, jsonl_bytes,
                     read_json, read_jsonl, seal, utcnow, write_json)
from .dataset import SYSTEM, FAMILIES
from .floor_v2 import make_cases, score_response
from .perturb import CONDITIONS, KINDS
from .runner import writer_lock

LOCK = ASSETS / 'qwen-v3-protocol.json'
MODEL = ASSETS / 'qwen-v3-model.json'
SOURCE = Path(__file__).parent


def cases(phase):
    if phase == 'pilot': return make_cases('dev', 'integer')
    rows = make_cases('eval', 'integer')
    if phase == 'replay':
        return [c for c in rows if int(c['question_id'].rsplit('-', 1)[1]) < 2]
    if phase != 'eval': raise ValueError('Unknown phase')
    return rows


def sources():
    return {p.name: file_hash(p) for p in sorted(SOURCE.glob('*.py'))}


def freeze(root):
    if LOCK.exists(): raise ValueError('Already frozen')
    deps = read_json(ASSETS / 'dependencies.json')
    spec = dict(model=read_json(MODEL), source_sha256=sources(),
                python=platform.python_version(),
                dependencies={p: importlib.metadata.version(p) for p in deps},
                cases_sha256={p: digest(jsonl_bytes(cases(p))) for p in ('pilot','eval','replay')},
                protocol_document_sha256=file_hash(Path(root)/'docs/qwen-v3/protocol.md'),
                tests_sha256=file_hash(Path(root)/'tests/test_qwen_v3.py'),
                max_new_tokens=64, pilot_budget_seconds=1800, eval_budget_seconds=10800,
                gate=dict(n=42, correct=34, extracted=38), bootstrap_seed=62103,
                bootstrap_replicates=10000)
    write_json(LOCK, dict(frozen_utc=utcnow(), specification=spec,
                         specification_sha256=digest(canonical(spec))))


def frozen(environment=False):
    lock = read_json(LOCK); spec = lock['specification']
    if digest(canonical(spec)) != lock['specification_sha256']: raise ValueError('Protocol hash mismatch')
    if spec['source_sha256'] != sources(): raise ValueError('Frozen source drift')
    if spec['model'] != read_json(MODEL): raise ValueError('Model manifest drift')
    for phase in ('pilot','eval','replay'):
        if spec['cases_sha256'][phase] != digest(jsonl_bytes(cases(phase))): raise ValueError('Input drift')
    # Source checkouts also enforce the human-readable protocol and test pins.
    # Installed wheels lack these files; the release verifier checks the checkout.
    root=SOURCE.parent.parent
    if (root/'docs/qwen-v3/protocol.md').exists():
        if file_hash(root/'docs/qwen-v3/protocol.md') != spec['protocol_document_sha256']:
            raise ValueError('Protocol document drift')
        if file_hash(root/'tests/test_qwen_v3.py') != spec['tests_sha256']:
            raise ValueError('Scoring tests drift')
    if environment:
        if platform.python_version() != spec['python']: raise ValueError('Python version drift')
        for p, version in spec['dependencies'].items():
            if importlib.metadata.version(p) != version: raise ValueError(f'Dependency drift: {p}')
    return lock


def verify_model(root):
    for name, entry in read_json(MODEL)['files'].items():
        path = Path(root)/name
        if not path.is_file() or path.stat().st_size != entry['bytes'] or file_hash(path) != entry['sha256']:
            raise ValueError(f'Model file mismatch: {name}')


def acquire(root):
    """Public unauthenticated HTTPS only; never read tokens or credential stores."""
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    manifest = read_json(MODEL)
    for name, entry in manifest['files'].items():
        dest = root/name
        if dest.exists() and file_hash(dest) == entry['sha256']: continue
        url = f"https://huggingface.co/{manifest['repo_id']}/resolve/{manifest['revision']}/{name}"
        temp = dest.with_suffix(dest.suffix+'.partial')
        with urllib.request.urlopen(url, timeout=120) as response, temp.open('wb') as stream:
            while chunk := response.read(1048576): stream.write(chunk)
        if temp.stat().st_size != entry['bytes'] or file_hash(temp) != entry['sha256']:
            raise ValueError(f'Download mismatch: {name}')
        temp.replace(dest)
    verify_model(root)


class Engine:
    def __init__(self, model_dir):
        os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'
        os.environ['TOKENIZERS_PARALLELISM']='false'
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, GenerationConfig
        self.torch = torch
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        torch.manual_seed(1907); torch.use_deterministic_algorithms(True)
        torch.backends.mkldnn.enabled = False
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False)
        self.model = AutoModelForCausalLM.from_pretrained(model_dir, local_files_only=True,
            trust_remote_code=False, torch_dtype=torch.float32, attn_implementation='eager').to('cpu').eval()
        self.generation = GenerationConfig(max_new_tokens=64, do_sample=False, num_beams=1,
            use_cache=True, eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=self.tokenizer.eos_token_id, bos_token_id=self.tokenizer.bos_token_id)

    def run(self, case, stop):
        from transformers import StoppingCriteria, StoppingCriteriaList
        class Cancel(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs): return stop()
        start = time.perf_counter()
        rendered = self.tokenizer.apply_chat_template([
            dict(role='system', content=SYSTEM), dict(role='user', content=case['prompt'])],
            tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(rendered, add_special_tokens=False, return_tensors='pt')
        with self.torch.inference_mode():
            output = self.model.generate(**inputs, generation_config=self.generation,
                stopping_criteria=StoppingCriteriaList([Cancel()]))
        tokens = output[0, inputs['input_ids'].shape[1]:].tolist()
        if stop(): raise InterruptedError('Partial generation discarded')
        eos = tokens[-1] == self.tokenizer.eos_token_id
        truncated = len(tokens) == 64 and not eos
        text = self.tokenizer.decode(tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        ids = inputs['input_ids'][0].tolist()
        return dict(rendered_prompt=rendered, rendered_prompt_sha256=digest(rendered),
            input_token_ids=ids, input_token_sha256=digest(canonical(ids)), input_tokens=len(ids),
            output_token_ids=tokens, output_tokens=len(tokens),
            raw_completion=self.tokenizer.decode(tokens, skip_special_tokens=False, clean_up_tokenization_spaces=False),
            completion=text, ended_with_eos=eos, truncated=truncated,
            elapsed_seconds=time.perf_counter()-start,
            **score_response(text, case['expression'], case['answer'], 'integer', truncated))


def validate(row, case, protocol_hash):
    check_seal(row)
    if row['protocol_sha256'] != protocol_hash: raise ValueError('Protocol mismatch')
    if any(row.get(k) != v for k,v in case.items()): raise ValueError('Case mismatch')
    expected = score_response(row['completion'],case['expression'],case['answer'],'integer',row['truncated'])
    if any(row.get(k) != v for k,v in expected.items()): raise ValueError('Score mismatch')
    if row['rendered_prompt_sha256'] != digest(row['rendered_prompt']): raise ValueError('Prompt hash mismatch')
    expected_prompt = '<|im_start|>system\n'+SYSTEM+'<|im_end|>\n<|im_start|>user\n'+case['prompt']+'<|im_end|>\n<|im_start|>assistant\n'
    if row['rendered_prompt'] != expected_prompt: raise ValueError('Rendered prompt mismatch')
    if row['input_token_sha256'] != digest(canonical(row['input_token_ids'])): raise ValueError('Input hash mismatch')
    for name in ('input','output'):
        ids=row[name+'_token_ids']
        if row[name+'_tokens'] != len(ids) or any(type(t) != int or not 0<=t<151936 for t in ids):
            raise ValueError('Token mismatch')
    if not 0 < row['output_tokens'] <= 64: raise ValueError('Output length mismatch')
    if row['ended_with_eos'] != (row['output_token_ids'][-1] == 151645): raise ValueError('EOS mismatch')
    if row['truncated'] != (row['output_tokens']==64 and not row['ended_with_eos']): raise ValueError('Truncation mismatch')
    if not row['ended_with_eos'] and not row['truncated']: raise ValueError('Unfinished generation')
    if not 0 <= row['elapsed_seconds'] < 10800: raise ValueError('Timing mismatch')


def gate(rows):
    n=len(rows); correct=sum(r['correct'] for r in rows); extracted=sum(r['extracted'] for r in rows)
    return dict(n=n, correct=correct, extracted=extracted,
                passed=n==42 and correct>=34 and extracted>=38)


def audit(root, partial=False):
    root=Path(root); lock=frozen(); meta=read_json(root/'run.json'); phase=meta['phase']
    expected=cases(phase)
    if meta['protocol_sha256'] != lock['specification_sha256']: raise ValueError('Run protocol mismatch')
    if datetime.fromisoformat(meta['created_utc']) <= datetime.fromisoformat(lock['frozen_utc']):
        raise ValueError('Run predates freeze')
    budget=1800 if phase=='pilot' else 10800
    if meta['budget_seconds'] != budget: raise ValueError('Budget mismatch')
    if (root/'cases.jsonl').read_bytes() != jsonl_bytes(expected): raise ValueError('Cases mismatch')
    path=root/'outputs.jsonl'; raw=path.read_bytes() if path.exists() else b''
    if raw and not raw.endswith(b'\n'): raise ValueError('Torn output tail')
    rows=[json.loads(line) for line in raw.splitlines()]
    if len(rows)>len(expected) or (not partial and len(rows)!=len(expected)): raise ValueError('Incomplete/extra records')
    for row,case in zip(rows,expected): validate(row,case,lock['specification_sha256'])
    if phase != 'pilot':
        pilot=root.parent/'pilot'
        if read_json(pilot/'run.json')['phase'] != 'pilot': raise ValueError('Invalid pilot phase')
        pilot_rows=audit(pilot)
        evidence=pilot_evidence(pilot,pilot_rows)
        if not evidence['gate']['passed'] or meta['pilot_evidence'] != evidence:
            raise ValueError('Pilot provenance mismatch')
        if datetime.fromisoformat(evidence['completed_utc']) >= datetime.fromisoformat(meta['created_utc']):
            raise ValueError('Evaluation predates pilot completion')
    if not partial:
        status=read_json(root/'status.json')
        if not status['complete'] or status['records'] != len(rows): raise ValueError('Status mismatch')
        if datetime.fromisoformat(status['completed_utc']) < datetime.fromisoformat(meta['created_utc']):
            raise ValueError('Completion predates run')
    return rows


def pilot_evidence(root, rows):
    return dict(gate=gate(rows),outputs_sha256=file_hash(Path(root)/'outputs.jsonl'),
                completed_utc=read_json(Path(root)/'status.json')['completed_utc'])


def verify_tokens(rows, model_dir):
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(model_dir,local_files_only=True,trust_remote_code=False)
    for row in rows:
        if tokenizer(row['rendered_prompt'],add_special_tokens=False)['input_ids'] != row['input_token_ids']:
            raise ValueError('Input tokenization mismatch')
        for special,key in ((False,'raw_completion'),(True,'completion')):
            if tokenizer.decode(row['output_token_ids'],skip_special_tokens=special,
                clean_up_tokenization_spaces=False) != row[key]:
                raise ValueError('Output decoding mismatch')



def recover_tail(root):
    path=Path(root)/'outputs.jsonl'
    if not path.exists(): return
    raw=path.read_bytes()
    if raw and not raw.endswith(b'\n'):
        end=raw.rfind(b'\n')+1
        write_json(Path(root)/f'recovery-{time.time_ns()}.json',dict(
            discarded_bytes=len(raw)-end, discarded_sha256=digest(raw[end:]), utc=utcnow()))
        path.write_bytes(raw[:end])


def run(root, model_dir, phase, pilot=None, limit=None):
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    lock=frozen(environment=True); verify_model(model_dir)
    with writer_lock(root):
        evidence=None
        if phase!='pilot':
            if pilot is None or Path(pilot).resolve() != (root.parent/'pilot').resolve():
                raise ValueError('Evaluation/replay requires sibling pilot directory')
            pilot_rows=audit(pilot)
            if read_json(Path(pilot)/'run.json')['phase']!='pilot' or not gate(pilot_rows)['passed']:
                raise ValueError('Pilot gate failed')
            evidence=pilot_evidence(pilot,pilot_rows)
        expected=cases(phase); budget=1800 if phase=='pilot' else 10800
        if not (root/'run.json').exists():
            if (root/'outputs.jsonl').exists(): raise ValueError('Orphan outputs')
            write_json(root/'run.json',dict(phase=phase,created_utc=utcnow(),budget_seconds=budget,
                protocol_sha256=lock['specification_sha256'],pilot_evidence=evidence))
            (root/'cases.jsonl').write_bytes(jsonl_bytes(expected))
        meta=read_json(root/'run.json')
        if meta['phase']!=phase or meta['pilot_evidence']!=evidence: raise ValueError('Resume evidence mismatch')
        recover_tail(root); rows=audit(root,partial=True)
        verify_tokens(rows,model_dir)
        if len(rows)==len(expected):
            audit(root)
            return dict(complete=True, records=len(rows))
        deadline=datetime.fromisoformat(meta['created_utc']).timestamp()+budget
        cancelled=False
        def cancel(*_):
            nonlocal cancelled
            cancelled=True
        def stop(): return cancelled or time.time()>=deadline
        old={s:signal.signal(s,cancel) for s in (signal.SIGINT,signal.SIGTERM)}
        started=time.perf_counter(); count=0; loading=None
        try:
            if not stop():
                engine=Engine(model_dir); loading=time.perf_counter()-started
                with (root/'outputs.jsonl').open('ab') as stream:
                    for case in expected[len(rows):]:
                        if stop() or (limit is not None and count>=limit): break
                        try: result=engine.run(case,stop)
                        except InterruptedError: break
                        row=seal(dict(case,**result,protocol_sha256=lock['specification_sha256']))
                        validate(row,case,lock['specification_sha256'])
                        stream.write(jsonl_bytes([row])); stream.flush(); os.fsync(stream.fileno())
                        rows.append(row); count+=1
                        if count%50==0: print(f'{phase}: {len(rows)}/{len(expected)}',flush=True)
        finally:
            for s,h in old.items(): signal.signal(s,h)
            write_json(root/f'session-{time.time_ns()}.json',dict(utc=utcnow(),new_records=count,
                wall_seconds=time.perf_counter()-started,loading_seconds=loading,
                peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                python=platform.python_version(),platform=platform.platform(),
                cancelled=cancelled,budget_exhausted=time.time()>=deadline))
        result=dict(complete=len(rows)==len(expected),records=len(rows),expected=len(expected))
        if result['complete']: result['completed_utc']=utcnow()
        if phase=='pilot': result['gate']=gate(rows)
        write_json(root/'status.json',result)
        return result


def compare(left,right):
    a={r['case_id']:r for r in audit(left)}; b=audit(right)
    ignore={'elapsed_seconds','record_sha256'}
    for r in b:
        if {k:v for k,v in r.items() if k not in ignore} != {k:v for k,v in a[r['case_id']].items() if k not in ignore}:
            raise ValueError(f"Replay mismatch: {r['case_id']}")
    return dict(matched_records=len(b))


def wilson(k,n):
    if not n: return [None,None]
    z=1.959963984540054; p=k/n; den=1+z*z/n
    mid=(p+z*z/(2*n))/den
    half=z*((p*(1-p)/n+z*z/(4*n*n))**.5)/den
    return [max(0.,mid-half),min(1.,mid+half)]


def statistics(rows):
    import numpy as np
    from .analysis import summarize
    prepared=[dict(r,status='valid' if r['extracted'] else 'invalid_format') for r in rows]
    result=summarize(prepared)
    for condition,metrics in result['conditions'].items():
        group=[r for r in rows if r['condition']==condition]
        for key in ('extracted','strict_compliant','strict_correct'):
            metrics[key]=sum(r[key] for r in group)
        metrics['accuracy_wilson_ci95']=wilson(metrics['correct'],metrics['denominator'])
        metrics['break_rate_wilson_ci95']=wilson(metrics['clean_correct_to_incorrect'],metrics['clean_correct_denominator'])
    clusters={r['question_id']:{} for r in rows}
    for r in rows: clusters[r['question_id']][r['condition']]=r
    groups=[clusters[k] for k in sorted(clusters)]
    rng=np.random.default_rng(62103)
    strata=[np.array([i for i,q in enumerate(groups) if q['clean']['family']==f]) for f in FAMILIES]
    indices=np.concatenate([rng.choice(s,size=(10000,len(s)),replace=True) for s in strata],axis=1)
    result['high_minus_low']={}
    for kind in KINDS:
        delta=np.array([int(q[kind+'-40']['correct'])-int(q[kind+'-20']['correct']) for q in groups])
        result['high_minus_low'][kind]=dict(paired_delta=float(delta.mean()),
            paired_delta_ci95=np.quantile(delta[indices].mean(axis=1),[.025,.975]).tolist())
    return result


def report(root):
    root=Path(root); rows=audit(root)
    if read_json(root/'run.json')['phase']!='eval': raise ValueError('Report requires evaluation')
    result=statistics(rows)
    sessions=[read_json(p) for p in root.glob('session-*.json')]
    result['runtime']=dict(wall_seconds=sum(s['wall_seconds'] for s in sessions),
        peak_process_rss_kib=max(s['peak_process_rss_kib'] for s in sessions))
    write_json(root/'summary.json',result)
    lines=['# Qwen v3: controlled typo evaluation','',
        '210 paired arithmetic questions; 1,470 actual completions. Accuracy includes invalid and truncated answers as incorrect. '
        'Delta means typo minus clean. Whole-response v2 extraction is used; strict integer correctness is shown separately.','',
        '| Condition | Correct / 210 | Strict correct | Extracted | Truncated | Delta pp [95% CI] | Clean correct → incorrect | Incorrect → correct |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for c,m in result['conditions'].items():
        lo,hi=m['paired_delta_ci95']
        lines.append(f"| {c} | {m['correct']} | {m['strict_correct']} | {m['extracted']} | {m['truncated']} | {100*m['paired_delta']:+.2f} [{100*lo:+.2f}, {100*hi:+.2f}] | {m['clean_correct_to_incorrect']} | {m['clean_incorrect_to_correct']} |")
    lines+=['','## Higher versus lower edit frequency','',
        '| Typo type | 40% minus 20% accuracy, pp [95% CI] |','|---|---:|']
    for k,m in result['high_minus_low'].items():
        lo,hi=m['paired_delta_ci95']
        lines.append(f"| {k} | {100*m['paired_delta']:+.2f} [{100*lo:+.2f}, {100*hi:+.2f}] |")
    lines+=['','## Interpretation limits','',
        'Intervals are 10,000 family-stratified bootstrap samples of paired questions, seed 62103; '
        'marginal, not simultaneous. A floor/ceiling can produce a degenerate bootstrap interval. '
        'summary.json additionally gives Wilson intervals for accuracy and clean-correct break rates, '
        'family counts, realized edit rates and token lengths. These are descriptive binomial approximations, '
        'not uncertainty over templates or models. Zero observed change does not establish equivalence.', '',
        'Only five optional words can be edited; numeric expressions and instructions are protected. '
        'The 20%/40% rates mean one/two edited eligible words, not 20%/40% of all text. '
        'One small model, one English template, and operands 0–20 do not support claims about general '
        'mathematical reasoning, realistic human mistakes, adversarial attacks, or other models. '
        'All edits carry a possible-meaning-change flag; no human semantic review was performed.','',
        f"Recorded run time: {result['runtime']['wall_seconds']:.3f} seconds; peak RSS: {result['runtime']['peak_process_rss_kib']} KiB.", '',
        'Exact inputs, edits, rendered prompts, raw responses, token IDs, and scores are in cases.jsonl and outputs.jsonl. '
        'The separate protocol and model manifests pin reproduction.']
    (root/'report.md').write_text('\n'.join(lines)+'\n')
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('freeze'); s.add_argument('--root',type=Path,default=Path('.'))
    s=sub.add_parser('acquire'); s.add_argument('--model-dir',type=Path,required=True)
    s=sub.add_parser('run'); s.add_argument('--out',type=Path,required=True); s.add_argument('--model-dir',type=Path,required=True)
    s.add_argument('--phase',choices=['pilot','eval','replay'],required=True); s.add_argument('--pilot',type=Path)
    s.add_argument('--limit',type=int)
    for name in ('audit','report'):
        s=sub.add_parser(name); s.add_argument('root',type=Path)
    s=sub.add_parser('compare'); s.add_argument('left',type=Path); s.add_argument('right',type=Path)
    args=p.parse_args(argv)
    if args.command=='freeze': result=freeze(args.root)
    elif args.command=='acquire': result=acquire(args.model_dir)
    elif args.command=='run':
        if args.limit is not None and args.limit<1: p.error('--limit must be positive')
        result=run(args.out,args.model_dir,args.phase,args.pilot,args.limit)
        print(json.dumps(result,sort_keys=True)); return 0 if result['complete'] else 2
    elif args.command=='audit': result=dict(records=len(audit(args.root)))
    elif args.command=='compare': result=compare(args.left,args.right)
    else: result=report(args.root)
    print(json.dumps(result,sort_keys=True)); return 0


if __name__=='__main__': sys.exit(main())
