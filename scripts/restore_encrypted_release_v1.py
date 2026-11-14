"""Restore Backup V1 from its independently authenticated AES-GCM parts."""
import argparse,hashlib,json,os,re,sys,tempfile,zipfile
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes

MAGIC=b'ASBX1\0\0\0';HEADER=8+4+4+12+16

def decrypt_part(source,destination,key,expected_index,total):
    with source.open('rb') as f:
        header=f.read(HEADER)
        if len(header)!=HEADER or header[:8]!=MAGIC:raise ValueError('Invalid encrypted part header')
        index=int.from_bytes(header[8:12],'big');parts=int.from_bytes(header[12:16],'big')
        if index!=expected_index or parts!=total:raise ValueError('Part order or count mismatch')
        nonce=header[16:28];tag=header[28:44];cipher=Cipher(algorithms.AES(key),modes.GCM(nonce,tag)).decryptor()
        cipher.authenticate_additional_data(header[:16]);h=hashlib.sha256()
        with destination.open('wb') as out:
            for block in iter(lambda:f.read(4*1024*1024),b''):
                plain=cipher.update(block);out.write(plain);h.update(plain)
            final=cipher.finalize();out.write(final);h.update(final)
        return h.hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parts',type=Path,required=True,help='Directory holding all backup-v1-part-NNN.aes files')
    p.add_argument('--key-file',type=Path,required=True,help='Private 64-character hex key file')
    p.add_argument('--output',type=Path,required=True,help='New output path for restored ZIP')
    a=p.parse_args();text=a.key_file.read_text(encoding='ascii').strip()
    if not re.fullmatch(r'[0-9a-fA-F]{64}',text):raise ValueError('Invalid key file')
    key=bytes.fromhex(text);parts=sorted(a.parts.glob('backup-v1-part-*.aes'))
    if not parts or [f.name for f in parts]!=[f'backup-v1-part-{i:03}.aes' for i in range(1,len(parts)+1)]:raise ValueError('Parts are missing or out of sequence')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=a.output.name+'.',suffix='.partial',dir=a.output.parent);os.close(fd);temp=Path(tmp)
    records=[]
    try:
        with temp.open('wb') as out:
            for index,source in enumerate(parts,1):
                plain=source.with_suffix('.restore-tmp')
                try:
                    checksum=decrypt_part(source,plain,key,index,len(parts));records.append({'part':source.name,'sha256_plain':checksum})
                    with plain.open('rb') as data:
                        for block in iter(lambda:data.read(4*1024*1024),b''):out.write(block)
                finally:plain.unlink(missing_ok=True)
        with zipfile.ZipFile(temp) as archive:
            if archive.testzip() is not None:raise ValueError('Restored ZIP CRC error')
            report=json.loads(archive.read('backup/REPORT.json'))
            manifest=json.loads(archive.read('backup/MANIFEST-SHA256.json'))
            if report.get('status')!='PASS' or not manifest:raise ValueError('Backup report/manifest invalid')
            names=set(archive.namelist())
            if len(manifest)+2!=len(names):raise ValueError('Backup file manifest count does not match ZIP')
            rows={row['path']:row for row in manifest}
            if len(rows)!=len(manifest):raise ValueError('Duplicate manifest paths')
            for row in manifest:
                if row['path'] not in names:raise ValueError('Backup manifest path is missing')
        os.replace(temp,a.output)
        (a.output.with_suffix(a.output.suffix+'.restore-proof.json')).write_text(json.dumps({'status':'PASS','zip_crc':'PASS','bytes':a.output.stat().st_size,'parts':records},indent=2),encoding='utf-8')
        print(json.dumps({'status':'PASS','output':str(a.output),'bytes':a.output.stat().st_size,'parts':len(records)}))
    except Exception:
        temp.unlink(missing_ok=True);raise

if __name__=='__main__':main()
