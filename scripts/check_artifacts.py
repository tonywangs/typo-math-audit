#!/usr/bin/env python3
"""Check the publication tree and sealed experiment without inference dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from typo_math_audit.audit import audit_run,compare_runs
from typo_math_audit.common import file_hash,read_json,canonical,digest
from typo_math_audit.protocol import CORE


def files():
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    return sorted({n for n in names if n and n!='artifacts.json'})


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--seal',action='store_true',help='Explicitly create/update the release integrity manifest')
    args=p.parse_args()
    names=files()
    if len(names)+1>1000: raise ValueError('Too many publication files')
    entries={}
    for n in names:
        path=ROOT/n
        if path.is_symlink() or not path.is_file(): raise ValueError(f'Not a regular file: {n}')
        size=path.stat().st_size
        if size>10*1024**2: raise ValueError(f'File too large: {n}')
        if n.endswith('.log') and n!='results/tests.log': raise ValueError(f'Excluded log: {n}')
        if path.suffix in ('.safetensors','.bin','.whl'): raise ValueError(f'Unpublishable weight/binary: {n}')
        entries[n]={'bytes':size,'sha256':file_hash(path)}
    frozen=read_json(ROOT/'src/typo_math_audit/assets/protocol.json')
    spec=frozen['specification']
    if digest(canonical(spec))!=frozen['specification_sha256']: raise ValueError('Protocol hash mismatch')
    for n in CORE:
        if file_hash(ROOT/'src/typo_math_audit'/n)!=spec['source_sha256'][n]: raise ValueError(f'Frozen source changed: {n}')
    if file_hash(ROOT/'src/typo_math_audit/assets/model.json')!=spec['model_manifest_sha256']: raise ValueError('Model manifest changed')
    pilot=audit_run(ROOT/'results/pilot')
    final=audit_run(ROOT/'results/final')
    replay=audit_run(ROOT/'results/offline-replay')
    comparison=compare_runs(ROOT/'results/final',ROOT/'results/offline-replay')
    if comparison['matched_records']!=1470: raise ValueError('Offline replay is incomplete')
    recovery=compare_runs(ROOT/'results/pilot',ROOT/'results/recovery-check')
    if recovery['matched_records']!=7: raise ValueError('Recovery replay is incomplete')
    if frozen['pilot_evidence']!=pilot: raise ValueError('Pilot evidence changed')
    if final['protocol_sha256']!=frozen['specification_sha256']: raise ValueError('Final protocol mismatch')
    pilot_meta=read_json(ROOT/'results/pilot/run.json')
    final_meta=read_json(ROOT/'results/final/run.json')
    if not pilot_meta['pilot'] or final_meta['pilot']: raise ValueError('Pilot/final role mismatch')
    from datetime import datetime
    if datetime.fromisoformat(frozen['frozen_utc'])>=datetime.fromisoformat(final_meta['created_utc']):
        raise ValueError('Evaluation started before freeze')
    manifest={'schema':1,'files':entries,'total_file_bytes_excluding_manifest':sum(x['bytes'] for x in entries.values())}
    manifest_path=ROOT/'artifacts.json'
    if args.seal:
        manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    elif read_json(manifest_path)!=manifest:
        raise ValueError('Release file inventory or hashes differ from artifacts.json')
    total=manifest['total_file_bytes_excluding_manifest']+manifest_path.stat().st_size
    if total>32*1024**2: raise ValueError('Publication tree too large')
    print(json.dumps({'files':len(entries)+1,'bytes':total,'pilot':pilot,'final':final,'offline_replay':replay,'recovery':recovery},sort_keys=True))


if __name__=='__main__': main()
