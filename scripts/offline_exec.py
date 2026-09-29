#!/usr/bin/env python3
"""Linux x86_64: deny AF_INET/AF_INET6 socket creation using inherited seccomp.

Execute the installed CLI in a fresh process after installing a kernel filter.
This does not provide a general security sandbox; it is an offline-replay check.
"""
import ctypes
import errno
import os
import platform
import sys


def deny_internet_sockets():
    if platform.system()!='Linux' or platform.machine()!='x86_64':
        raise RuntimeError('Offline seccomp test supports Linux x86_64 only')
    class Filter(ctypes.Structure):
        _fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_=[('len',ctypes.c_ushort),('filter',ctypes.POINTER(Filter))]
    # seccomp_data: nr at 0, arch at 4, args[0] at 16.
    # Reject non-x86_64 architectures; reject x32 syscall numbers too.
    instructions=[
        (0x20,0,0,4),                 # LD architecture
        (0x15,1,0,0xc000003e),        # JEQ AUDIT_ARCH_X86_64
        (0x06,0,0,0x80000000),        # RET KILL_PROCESS
        (0x20,0,0,0),                 # LD syscall number
        (0x35,0,1,0x40000000),        # JGE x32 syscall bit
        (0x06,0,0,0x00050000|errno.EPERM),
        (0x15,0,4,41),                # JEQ socket, else ALLOW
        (0x20,0,0,16),                # LD socket domain
        (0x15,1,0,2),                 # JEQ AF_INET -> DENY
        (0x15,0,1,10),                # JEQ AF_INET6 -> DENY; else ALLOW
        (0x06,0,0,0x00050000|errno.EPERM),
        (0x06,0,0,0x7fff0000),        # ALLOW
    ]
    filters=(Filter*len(instructions))(*(Filter(*x) for x in instructions))
    program=Program(len(instructions),filters)
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(38,1,0,0,0)!=0: raise OSError(ctypes.get_errno(),'PR_SET_NO_NEW_PRIVS')
    if libc.prctl(22,2,ctypes.byref(program),0,0)!=0: raise OSError(ctypes.get_errno(),'PR_SET_SECCOMP')


def main():
    if len(sys.argv)<2: raise SystemExit('Usage: offline_exec.py INSTALLED_CLI [arguments...]')
    deny_internet_sockets()
    # Positive control: fail if either kind of Internet socket can be created.
    import socket
    for family in (socket.AF_INET,socket.AF_INET6):
        try:
            sock=socket.socket(family,socket.SOCK_STREAM)
        except PermissionError:
            continue
        else:
            sock.close()
            raise RuntimeError('Internet socket unexpectedly available')
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    print('Offline guard verified: AF_INET and AF_INET6 denied by kernel',flush=True)
    os.execv(sys.argv[1],sys.argv[1:])


if __name__=='__main__': main()
