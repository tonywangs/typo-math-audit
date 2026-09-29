"""Paired descriptive analysis with a family-stratified question bootstrap."""
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from .audit import audit_run
from .common import read_json, read_jsonl, write_json
from .perturb import CONDITIONS
from .dataset import FAMILIES


def interval(values):
    finite = np.asarray(values)[np.isfinite(values)]
    return np.quantile(finite, [0.025, .975]).tolist() if len(finite) else [None, None]


def summarize(records, seed=62103, replicates=10000):
    grouped = defaultdict(dict)
    for row in records:
        if row['condition'] in grouped[row['question_id']]:
            raise ValueError('Duplicate condition')
        grouped[row['question_id']][row['condition']] = row
    complete = [v for _,v in sorted(grouped.items()) if set(v)==set(CONDITIONS)]
    if not complete:
        raise ValueError('No complete question clusters to analyze')
    matrix = np.array([[q[c]['correct'] for c in CONDITIONS] for q in complete], dtype=float)
    clean = matrix[:,0]
    rng = np.random.default_rng(seed)
    strata = [np.array([i for i,q in enumerate(complete) if q['clean']['family']==f]) for f in FAMILIES]
    indices = np.concatenate([rng.choice(s,size=(replicates,len(s)),replace=True) for s in strata if len(s)],axis=1)
    boot = matrix[indices].mean(axis=1)
    answer = dict(question_clusters=len(complete), observed_records=len(records),
                  excluded_incomplete_questions=len(grouped)-len(complete),
                  excluded_records=len(records)-len(complete)*len(CONDITIONS),
                  bootstrap=dict(seed=seed,replicates=replicates,unit='original question',
                                 stratified_by='family',confidence=.95,
                                 note='Marginal percentile intervals; not simultaneous; template uncertainty unmeasured'),
                  conditions={})
    for j,c in enumerate(CONDITIONS):
        rows=[q[c] for q in complete]
        values=matrix[:,j]
        broken=(clean==1)&(values==0)
        recovered=(clean==0)&(values==1)
        clean_boot=clean[indices].sum(axis=1)
        with np.errstate(divide='ignore',invalid='ignore'):
            conditional=broken[indices].sum(axis=1)/clean_boot
        n=len(rows)
        answer['conditions'][c]=dict(
            correct=int(values.sum()),denominator=n,accuracy=float(values.mean()),accuracy_ci95=interval(boot[:,j]),
            paired_delta=float((values-clean).mean()),paired_delta_ci95=interval(boot[:,j]-boot[:,0]),
            both_correct=int(((clean==1)&(values==1)).sum()),
            clean_correct_to_incorrect=int(broken.sum()),clean_incorrect_to_correct=int(recovered.sum()),
            both_incorrect=int(((clean==0)&(values==0)).sum()),
            clean_correct_denominator=int(clean.sum()),
            break_rate_given_clean_correct=float(broken.sum()/clean.sum()) if clean.sum() else None,
            break_rate_ci95=interval(conditional),
            bootstrap_zero_clean_correct_replicates=int((clean_boot==0).sum()),
            invalid=sum(r['status']=='invalid_format' for r in rows),
            truncated=sum(r['truncated'] for r in rows),unchanged=sum(r['unchanged'] for r in rows),
            possible_meaning_change=sum(r['possible_meaning_change'] for r in rows),
            mean_realized_eligible_word_rate=float(np.mean([r['realized_eligible_word_rate'] for r in rows])),
            mean_realized_all_word_rate=float(np.mean([r['realized_all_word_rate'] for r in rows])),
            mean_input_tokens=float(np.mean([r['input_tokens'] for r in rows])),
            mean_output_tokens=float(np.mean([r['output_tokens'] for r in rows])),
            total_generation_seconds=sum(r['elapsed_seconds'] for r in rows),
            by_family={f:dict(correct=sum(q[c]['correct'] for q in complete if q[c]['family']==f),
                              denominator=sum(q[c]['family']==f for q in complete)) for f in FAMILIES})
    return answer


def report(root, allow_partial=False):
    root=Path(root)
    integrity=audit_run(root,allow_partial)
    config=read_json(root/'run.json')
    settings=config['specification']['analysis']
    summary=summarize(read_jsonl(root/'outputs.jsonl'),settings['bootstrap_seed'],settings['bootstrap_replicates'])
    summary['integrity']=integrity
    sessions=[read_json(p) for p in sorted(root.glob('session-*.json'))]
    summary['runtime']=dict(recorded_session_wall_seconds=sum(s['wall_seconds'] for s in sessions),
                            peak_process_rss_kib=max((s['peak_process_rss_kib'] for s in sessions),default=None),
                            recorded_sessions=len(sessions),
                            note='Sum of recorded invocation wall times, including loading and verification. A SIGKILL can leave unrecorded invocation time.')
    summary['artifact_sizes_before_report']={p.name:p.stat().st_size for p in root.iterdir() if p.is_file() and p.suffix in ('.json','.jsonl')}
    write_json(root/'summary.json',summary)
    label='Development pilot' if config['pilot'] else 'Frozen evaluation'
    lines=[f'# {label}: arithmetic typo audit','',
           f"{summary['question_clusters']} complete original questions; {integrity['records']}/{integrity['expected_records']} actual completions. "
           f"Excluded incomplete questions: {summary['excluded_incomplete_questions']}.",'',
           'Accuracy uses strict whole-integer responses. Invalid format and truncated responses count as incorrect. '
           'Delta is corrupted minus clean accuracy; positive values are improvements.','',
           '| Condition | Correct / N | Accuracy | Delta (percentage points), 95% CI | Clean correct → incorrect / clean correct | Incorrect → correct | Invalid | Truncated |',
           '|---|---:|---:|---:|---:|---:|---:|---:|']
    for c,m in summary['conditions'].items():
        lo,hi=m['paired_delta_ci95']
        lines.append(f"| {c} | {m['correct']}/{m['denominator']} | {100*m['accuracy']:.2f}% | "
                     f"{100*m['paired_delta']:+.2f} [{100*lo:+.2f}, {100*hi:+.2f}] | "
                     f"{m['clean_correct_to_incorrect']}/{m['clean_correct_denominator']} | "
                     f"{m['clean_incorrect_to_correct']} | {m['invalid']} | {m['truncated']} |")
    lines += ['', 'Intervals use 10,000 bootstrap samples of original questions, stratified by task family. '
              'All seven variants stay together. These are marginal intervals without multiplicity correction, '
              'not evidence about other templates, models, or human typing distributions. '
              'Accuracy and conditional transition intervals are in summary.json.', '',
              '## Task families','', '| Condition | Addition | Subtraction | Multiplication |', '|---|---:|---:|---:|']
    for c,m in summary['conditions'].items():
        cells=[f"{m['by_family'][f]['correct']}/{m['by_family'][f]['denominator']}" for f in FAMILIES]
        lines.append(f"| {c} | "+' | '.join(cells)+' |')
    lines += ['', '## Realized perturbations','',
              '| Condition | Eligible-word rate | All-word rate | Unchanged / N | Possible meaning change / N | Mean input tokens |',
              '|---|---:|---:|---:|---:|---:|']
    for c,m in summary['conditions'].items():
        lines.append(f"| {c} | {100*m['mean_realized_eligible_word_rate']:.1f}% | "
                     f"{100*m['mean_realized_all_word_rate']:.2f}% | {m['unchanged']}/{m['denominator']} | "
                     f"{m['possible_meaning_change']}/{m['denominator']} | {m['mean_input_tokens']:.2f} |")
    rt=summary['runtime']
    lines += ['', 'All edited variants are conservatively flagged for possible meaning changes; '
              'this is an unreviewed risk flag, not a measured semantic failure. Numbers, operators and the '
              'answer instruction are untouched. Offsets refer to the original user prompt.', '',
              '## Runtime and artifacts','',
              f"Recorded invocation time: {rt['recorded_session_wall_seconds']:.3f} seconds across {rt['recorded_sessions']} sessions. "
              f"Peak process RSS: {rt['peak_process_rss_kib']} KiB (Linux high-water mark). "
              'Per-case times, token IDs, exact rendered prompts, completions, hashes and scoring evidence '
              'are in outputs.jsonl. Environment and loading time are in session-*.json. '
              'File sizes are listed in summary.json; model weights are stored separately.', '',
              '## Limits','',
              'One 135M-parameter model, one prompt template, English, operands 0–20, and three single-operation '
              'families. Development and evaluation arithmetic instances are disjoint, but share templates '
              'and operand ranges; training-data contamination cannot be ruled out. Five optional scaffold '
              'words are eligible for one or two edits, so this is a mild, protected-input intervention. '
              'It does not measure story comprehension, difficult mathematics, larger-model behavior, '
              'adversarial attacks, or realistic human-error distributions. Strict scoring mixes arithmetic '
              'success with instruction-format compliance. The 24-token cap may censor correct answers in longer '
              'explanations; no post-hoc answer extraction or generation retuning is used. Clean-first order '
              'and shared templates limit timing and uncertainty interpretations. Poor accuracy, zero changes, '
              'and improvements are all retained. Deterministic replay is tested on the recorded environment; '
              'different hardware or numerical libraries may differ.', '']
    path=root/'report.md'
    path.write_text('\n'.join(lines))
    return str(path)
