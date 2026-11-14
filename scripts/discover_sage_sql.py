"""Bounded SQL Browser SSRP request and TCP check; no SQL login or modification."""
import socket,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
result={'checked_at':datetime.now(timezone.utc).isoformat(),'target':'192.168.9.200','browser_udp_port':1434}
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
    sock.settimeout(3);sock.sendto(b'\x04SAGEX3\x00',('192.168.9.200',1434))
    data,peer=sock.recvfrom(8192)
    assert peer[0]=='192.168.9.200' and data[0]==5
    tokens=data[3:].decode('ascii').strip(';').split(';');fields=dict(zip(tokens[::2],tokens[1::2]))
result['advertised']=fields
with socket.create_connection(('192.168.9.200',int(fields['tcp'])),timeout=3):result['tcp_connected']=True
(ROOT/'logs/sql-server-discovery.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
