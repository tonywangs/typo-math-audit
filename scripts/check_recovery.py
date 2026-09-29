#!/usr/bin/env python3
"""Exercise real installed-CLI cancellation, torn-tail recovery and exact replay.

Uses only seven development completions; never edits the frozen experiment.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time


def invoke(command, cwd, env):
    return subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,timeout=180)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cli',required=True)
    p.add_argument('--model-dir',required=True)
    p.add_argument('--reference',required=True,help='Completed development pilot directory')
    p.add_argument('--evidence-out',help='Optional new directory to preserve test evidence')
    args=p.parse_args()
    cli=str(Path(args.cli).resolve())
    model=str(Path(args.model_dir).resolve())
    reference=str(Path(args.reference).resolve())
    helper=Path(__file__).resolve().with_name('offline_exec.py')
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
    with tempfile.TemporaryDirectory(prefix='typo-recovery-') as temporary:
        cwd=Path(temporary)
        out=cwd/'run'
        command=['/usr/bin/python3',str(helper),cli,'run','--split','dev','--model-dir',model,'--out',str(out)]
        started=time.monotonic()
        # Send SIGTERM once a real model completion has been fsynced.
        with (cwd/'console.txt').open('w') as console:
            child=subprocess.Popen(command,cwd=cwd,env=env,stdout=console,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+150
                records=[]
                while time.monotonic()<deadline:
                    if child.poll() is not None: raise RuntimeError('CLI exited before cancellation test')
                    output=out/'outputs.jsonl'
                    if output.exists():
                        data=output.read_bytes()
                        if b'\n' in data:
                            records=[json.loads(x) for x in data.splitlines() if x.endswith(b'}')]
                            break
                    time.sleep(.05)
                if not records: raise RuntimeError('No durable completion before timeout')
                child.send_signal(signal.SIGTERM)
                code=child.wait(timeout=30)
            finally:
                if child.poll() is None:
                    child.kill();child.wait()
        if code!=2: raise RuntimeError(f'Cancelled CLI returned {code}')
        status=json.loads((out/'status.json').read_text())
        if status['state']!='cancelled': raise RuntimeError(f'Unexpected cancellation state: {status}')
        output=out/'outputs.jsonl'
        prefix=output.read_bytes()
        completed=len(prefix.splitlines())
        if not 1<=completed<7: raise RuntimeError(f'Unexpected completed count: {completed}')
        with output.open('ab') as f: f.write(b'{"simulated_power_loss":')
        resumed=invoke(command+['--limit',str(7-completed)],cwd,env)
        if resumed.returncode!=2: raise RuntimeError(f'Resume failed: {resumed.stdout} {resumed.stderr}')
        if not output.read_bytes().startswith(prefix): raise RuntimeError('Committed prefix changed')
        if len(output.read_bytes().splitlines())!=7: raise RuntimeError('Missing resumed completions')
        if len(list(out.glob('recovery-*.json')))!=1: raise RuntimeError('Missing torn-tail evidence')
        compared=invoke([cli,'compare',reference,str(out)],cwd,env)
        if compared.returncode!=0: raise RuntimeError(f'Replay mismatch: {compared.stderr}')
        evidence=dict(real_model=True,offline_guard='kernel seccomp AF_INET/AF_INET6 denial',
                      cancellation_signal='SIGTERM',cancel_exit_code=code,
                      durable_before_cancel=completed,resume_exit_code=resumed.returncode,
                      durable_after_resume=7,committed_prefix_unchanged=True,
                      simulated_partial_tail_recovered=True,
                      deterministic_comparison=json.loads(compared.stdout),
                      elapsed_seconds=time.monotonic()-started)
        (out/'verification.json').write_text(json.dumps(evidence,indent=2,sort_keys=True)+'\n')
        if args.evidence_out:
            destination=Path(args.evidence_out)
            if destination.exists(): raise ValueError('Evidence destination must be new')
            shutil.copytree(out,destination,ignore=shutil.ignore_patterns('*.lockfile'))
        print(json.dumps(evidence,sort_keys=True))


if __name__=='__main__': main()
