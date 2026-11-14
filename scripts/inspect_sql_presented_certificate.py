"""Observe a TLS 1.2 Certificate message in TDS PRELOGIN, then disconnect.

No LOGIN7, SQL credentials, SQL batches, completed TLS session or trust changes.
The SSL context keeps normal certificate verification. We parse the public,
pre-authentication certificate message without accepting it as trusted.
"""
import socket,ssl,struct,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
LIMIT=1_000_000
def read_exact(sock,length):
    if length<0 or length>LIMIT:raise ValueError('oversized_record')
    parts=bytearray()
    while len(parts)<length:
        data=sock.recv(length-len(parts))
        if not data:raise EOFError('peer_closed')
        parts.extend(data)
    return bytes(parts)

def send_tds(sock,payload):
    if len(payload)>65527:raise ValueError('oversized_outgoing_prelogin')
    sock.sendall(struct.pack('!BBHHBB',0x12,1,len(payload)+8,0,1,0)+payload)

def read_tds(sock):
    body=bytearray()
    for _ in range(128):
        header=read_exact(sock,8);kind,status,length,_,_,_=struct.unpack('!BBHHBB',header)
        if kind not in (0x04,0x12) or length<8:raise ValueError('unexpected_tds_packet')
        body.extend(read_exact(sock,length-8))
        if len(body)>LIMIT:raise ValueError('oversized_tds_message')
        if status&1:return bytes(body)
    raise ValueError('too_many_packets')

def prelogin():
    values=[(0,b'\x10\x00\x00\x00\x00\x00'),(1,b'\x01'),(3,b'\x00'*4),(4,b'\x00')]
    offset=len(values)*5+1;header=bytearray();body=bytearray()
    for token,value in values:
        header.extend(struct.pack('!BHH',token,offset,len(value)));body.extend(value);offset+=len(value)
    return bytes(header)+b'\xff'+bytes(body)

out={'checked_at':datetime.now(timezone.utc).isoformat(),'server':'192.168.9.200','port':1433,
     'server_name_requested':'sage','method':'PASSIVE_CERTIFICATE_MESSAGE_AFTER_OWN_PRELOGIN_CLIENTHELLO',
     'login_sent':False,'sql_statements_sent':0,'tls_session_completed':False,'certificate_accepted_as_trusted':False,'trust_store_modified':False}
try:
    context=ssl.create_default_context();context.maximum_version=ssl.TLSVersion.TLSv1_2
    incoming=ssl.MemoryBIO();outgoing=ssl.MemoryBIO()
    tls=context.wrap_bio(incoming,outgoing,server_side=False,server_hostname='sage')
    try:tls.do_handshake()
    except ssl.SSLWantReadError:pass
    hello=outgoing.read()
    with socket.create_connection(('192.168.9.200',1433),timeout=5) as sock:
        sock.settimeout(5);send_tds(sock,prelogin());reply=read_tds(sock)
        index=0;encryption=None
        while index<len(reply) and reply[index]!=255:
            token,offset,length=struct.unpack('!BHH',reply[index:index+5]);index+=5
            if token==1:encryption=reply[offset]
        out['server_prelogin_encryption']=encryption
        if encryption not in (1,3):raise ValueError('server_did_not_accept_full_encryption')
        send_tds(sock,hello);records=bytearray();handshake=bytearray();chain=[]
        for _ in range(32):
            records.extend(read_tds(sock))
            while len(records)>=5:
                kind=records[0];length=int.from_bytes(records[3:5],'big')
                if len(records)<5+length:break
                payload=bytes(records[5:5+length]);del records[:5+length]
                if kind==21:raise ValueError('server_tls_alert')
                if kind==22:handshake.extend(payload)
            while len(handshake)>=4:
                kind=handshake[0];length=int.from_bytes(handshake[1:4],'big')
                if length>LIMIT:raise ValueError('oversized_handshake')
                if len(handshake)<4+length:break
                payload=bytes(handshake[4:4+length]);del handshake[:4+length]
                if kind==11:
                    total=int.from_bytes(payload[:3],'big');cursor=3
                    if total!=len(payload)-3:raise ValueError('bad_certificate_list')
                    while cursor<len(payload):
                        size=int.from_bytes(payload[cursor:cursor+3],'big');cursor+=3
                        cert=payload[cursor:cursor+size];cursor+=size
                        if len(cert)!=size or not size:raise ValueError('bad_certificate')
                        chain.append(cert)
            if chain:break
        if not chain:raise ValueError('no_tls12_certificate_observed')
        # Disconnect before any Finished/client-key exchange or database login.
    certs=[]
    for index,der in enumerate(chain):
        pem_path=ROOT/'runtime'/f'sql-presented-certificate-{index}.pem'
        pem_path.write_text(ssl.DER_cert_to_PEM_cert(der),encoding='ascii')
        parsed=ssl._ssl._test_decode_cert(str(pem_path))
        certs.append({'index':index,'subject':parsed.get('subject'),'issuer':parsed.get('issuer'),
            'san':parsed.get('subjectAltName',[]),'not_before':parsed.get('notBefore'),'not_after':parsed.get('notAfter'),
            'serial_number':parsed.get('serialNumber'),'sha256':hashlib.sha256(der).hexdigest(),'pem_file':str(pem_path)})
    out['certificates']=certs;out['status']='PUBLIC_CERTIFICATE_OBSERVED_NOT_TRUSTED'
except Exception as exc:
    out['status']='INSPECTION_FAILED';out['error_type']=type(exc).__name__;out['error_code']=str(exc) if isinstance(exc,ValueError) else 'transport_or_protocol_failure'
(ROOT/'logs/sql-tls-presented-certificate.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(out,indent=2,ensure_ascii=False))
