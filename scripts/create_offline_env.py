#!/usr/bin/env python3
"""Create a separate venv and install this project's wheel entirely from local files.

Usage: python3 scripts/create_offline_env.py WHEELHOUSE NEW_VENV
Run through offline_exec.py to enforce no Internet sockets during installation.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import venv
import zipfile


def main():
    if len(sys.argv)!=3: raise SystemExit(__doc__)
    wheelhouse=Path(sys.argv[1]).resolve()
    target=Path(sys.argv[2]).resolve()
    if target.exists(): raise ValueError('Use a new virtual environment directory')
    wheels=list(wheelhouse.glob('typo_math_audit-*.whl'))
    pip_wheels=list(wheelhouse.glob('pip-*.whl'))
    if len(wheels)!=1 or len(pip_wheels)!=1: raise ValueError('Expected exactly one project wheel and one pip wheel')
    root=Path(__file__).resolve().parents[1]
    venv.EnvBuilder(with_pip=False).create(target)
    python=target/'bin/python'
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
    purelib=subprocess.check_output([str(python),'-I','-c','import sysconfig; print(sysconfig.get_path("purelib"))'],env=env,text=True).strip()
    with zipfile.ZipFile(pip_wheels[0]) as archive:
        archive.extractall(purelib)
    subprocess.run([str(python),'-I','-m','pip','install','--no-index','--no-cache-dir',
                    '--find-links',str(wheelhouse),'-r',str(root/'requirements.lock'),str(wheels[0])],
                   env=env,cwd=target,check=True)
    origin=subprocess.check_output([str(python),'-I','-c',
        'import typo_math_audit; print(typo_math_audit.__file__)'],env=env,cwd=target,text=True).strip()
    if not Path(origin).is_relative_to(target): raise ValueError('Package was not loaded from isolated environment')
    print(json.dumps({'venv':str(target),'installed_package':origin,'wheel':str(wheels[0])}))


if __name__=='__main__': main()
