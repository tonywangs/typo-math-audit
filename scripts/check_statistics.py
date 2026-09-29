#!/usr/bin/env python3
"""Recompute scientific summaries without changing the stored experiment."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from typo_math_audit.common import read_json,read_jsonl
from typo_math_audit.analysis import summarize
from typo_math_audit.audit import audit_run
from typo_math_audit.protocol import load_frozen


def main():
    frozen=load_frozen()
    settings=frozen['specification']['analysis']
    for name in ('pilot','final','offline-replay'):
        root=ROOT/'results'/name
        integrity=audit_run(root)
        stored=read_json(root/'summary.json')
        actual=summarize(read_jsonl(root/'outputs.jsonl'),settings['bootstrap_seed'],settings['bootstrap_replicates'])
        for key,value in actual.items():
            if stored[key]!=value: raise ValueError(f'{name}: summary differs in {key}')
        if stored['integrity']!=integrity: raise ValueError(f'{name}: integrity summary differs')
        print(f'{name}: all scientific statistics and bootstrap intervals reproduced')


if __name__=='__main__': main()
