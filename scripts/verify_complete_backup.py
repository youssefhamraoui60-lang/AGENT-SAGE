"""Verify extracted private archive against its embedded content manifest."""
import argparse,hashlib,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    root=a.directory.resolve()
    rows=json.loads((root/'backup/MANIFEST-SHA256.json').read_text(encoding='utf-8'))
    for row in rows:
        f=(root/row['path']).resolve()
        if not f.is_relative_to(root):raise ValueError('Unsafe manifest path')
        if f.stat().st_size!=row['bytes']:raise ValueError('Size mismatch: '+row['path'])
        h=hashlib.sha256()
        with f.open('rb') as src:
            for b in iter(lambda:src.read(4*1024*1024),b''):h.update(b)
        if h.hexdigest()!=row['sha256']:raise ValueError('SHA256 mismatch: '+row['path'])
    print(json.dumps({'verified_files':len(rows),'status':'PASS'}))

if __name__=='__main__':main()
