"""Run local regressions with external networking and ERP subprocesses denied."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import asyncio  # Windows defines a subprocess.Popen subclass during import.
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'backend'), str(ROOT/'backend/tests')]
os.environ.update(SAGE_SOAP_CREDENTIAL_FILE='', SAGE_SOAP_USERNAME='OFFLINE_FIXTURE',
                  SAGE_SOAP_PASSWORD='REDACTED_CONFIGURE_LOCALLY', APPROVAL_TOKEN='synthetic-offline-token',
                  SAGE_POWERSHELL_CHAT_ENABLED='false', SAGE_WRITES_ENABLED='false')
os.environ.pop('RUN_STEP2_INTEGRATION', None)
os.environ.pop('RUN_PKI_INTEGRATION', None)


def denied(*args, **kwargs):
    raise RuntimeError('OFFLINE_TEST_BOUNDARY: external networking/subprocess denied')


_socket_connect=socket.socket.connect
_socketpair=socket.socketpair
_local=threading.local()
def local_socketpair(*args,**kwargs):
    _local.socketpair=True
    try:return _socketpair(*args,**kwargs)
    finally:_local.socketpair=False
def connect(sock,address):
    if getattr(_local,'socketpair',False) and address[0] in ('127.0.0.1','::1'):
        return _socket_connect(sock,address)
    return denied()
socket.socketpair=local_socketpair
socket.socket.connect = connect
socket.socket.connect_ex = denied
socket.create_connection = denied
subprocess.Popen = denied

import pytest
import psycopg
psycopg.connect=denied

if __name__ == '__main__':
    os.chdir(ROOT/'backend')
    raise SystemExit(pytest.main(sys.argv[1:]))
