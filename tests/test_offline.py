import platform
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.skipif(platform.system()!='Linux' or platform.machine()!='x86_64',reason='Linux x86_64 seccomp helper')
def test_network_guard_survives_exec():
    helper=Path(__file__).resolve().parents[1]/'scripts/offline_exec.py'
    code='''
import socket
for family in (socket.AF_INET,socket.AF_INET6):
    try:
        socket.socket(family,socket.SOCK_STREAM)
    except PermissionError:
        pass
    else:
        raise AssertionError('Internet socket allowed')
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.close()
print('inherited guard verified')
'''
    result=subprocess.run([sys.executable,str(helper),sys.executable,'-c',code],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert 'inherited guard verified' in result.stdout
