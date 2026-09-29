#!/usr/bin/env python3
"""Real-model SIGTERM and torn-tail recovery check using preregistered replay cases.

Run once with --execute. Subsequent invocations verify the preserved evidence.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from typo_math_audit.common import read_json,read_jsonl,write_json,file_hash
from typo_math_audit.floor_v2 import audit


def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true')
    p.add_argument('--python',default='/tmp/typo-math-offline-venv/bin/python')
    p.add_argument('--model-dir',default='/tmp/typo-math-model');args=p.parse_args()
    out=ROOT/'results/floor-v2/recovery'
    evidence=out/'verification.json'
    if args.execute:
        if out.exists():raise ValueError('Refusing to overwrite recovery evidence')
        command=[sys.executable,str(ROOT/'scripts/offline_exec.py'),args.python,'-I','-m',
                 'typo_math_audit.floor_v2','run','--model-dir',args.model_dir,'--out',str(out),'--replay']
        process=subprocess.Popen(command,cwd='/tmp',stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                output=out/'outputs.jsonl'
                if process.poll() is not None:raise RuntimeError(process.communicate())
                if output.exists() and len(output.read_bytes().splitlines())>=1:
                    # The first durable line precedes the next generation. Interrupt mid-generation.
                    time.sleep(.2)
                    process.send_signal(signal.SIGTERM)
                    break
                time.sleep(.1)
            else:raise TimeoutError('No durable first result in three minutes')
            stdout,stderr=process.communicate(timeout=30)
            if process.returncode!=2:raise ValueError(f'Cancellation exit {process.returncode}: {stderr}')
        finally:
            if process.poll() is None:
                process.kill();process.wait()
        cancelled=read_json(out/'status.json')
        if cancelled['state']!='cancelled':raise ValueError('Signal did not cancel')
        prefix=(out/'outputs.jsonl').read_bytes();before=len(prefix.splitlines())
        audit(out,True)
        tail=b'{"deliberately_torn_recovery_test":'
        with (out/'outputs.jsonl').open('ab') as stream:
            stream.write(tail);stream.flush();os.fsync(stream.fileno())
        resumed=subprocess.run(command+['--limit','1'],cwd='/tmp',capture_output=True,text=True,timeout=180)
        if resumed.returncode!=2:raise ValueError(f'Resume exit {resumed.returncode}: {resumed.stderr}')
        after=read_jsonl(out/'outputs.jsonl')
        if len(after)!=before+1 or not (out/'outputs.jsonl').read_bytes().startswith(prefix):
            raise ValueError('Resume changed the durable prefix')
        discarded=[read_json(path) for path in out.glob('recovery-*.json')]
        if len(discarded)!=1 or bytes.fromhex(discarded[0]['discarded_tail_hex'])!=tail:
            raise ValueError('Torn tail not preserved')
        write_json(evidence,dict(cancelled_status=cancelled,cancel_exit=process.returncode,
                   resume_exit=resumed.returncode,records_before=before,records_after=len(after),
                   outputs_sha256=file_hash(out/'outputs.jsonl'),discarded_tail_hex=tail.hex(),
                   offline_guard_verified='Offline guard verified' in stdout and 'Offline guard verified' in resumed.stdout))
    saved=read_json(evidence)
    if not saved['offline_guard_verified']:raise ValueError('Missing offline guard evidence')
    checked=audit(out,True)
    if checked['records']!=saved['records_after'] or checked['outputs_sha256']!=saved['outputs_sha256']:
        raise ValueError('Recovery evidence changed')
    # Match every retained scientific field against the independently run pilot.
    reference={r['case_id']:r for r in read_jsonl(ROOT/'results/floor-v2/pilot/outputs.jsonl')}
    ignored={'elapsed_seconds','record_sha256','protocol_sha256'}
    for row in read_jsonl(out/'outputs.jsonl'):
        if {k:v for k,v in row.items() if k not in ignored}!={k:v for k,v in reference[row['case_id']].items() if k not in ignored}:
            raise ValueError('Recovery output differs from pilot')
    print(json.dumps(dict(verified=True,**saved),sort_keys=True))


if __name__=='__main__':main()
