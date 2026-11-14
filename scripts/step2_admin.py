"""Local maintenance: additive migration, validated reference import and local RAG indexing.
No company connections, no remote services. Run from backend with its existing venv.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services import business_store as store
from app.services.knowledge import index_document
from psycopg.types.json import Jsonb

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='action',required=True)
    sub.add_parser('migrate')
    ref=sub.add_parser('import-references')
    ref.add_argument('path',type=Path)
    ref.add_argument('--validated',action='store_true')
    docs=sub.add_parser('index-document')
    docs.add_argument('path',type=Path)
    docs.add_argument('--reviewed',action='store_true')
    args=parser.parse_args()
    if args.action=='migrate': print('Migration applied' if store.migrate() else 'Migration already applied; checksum verified')
    elif args.action=='index-document':
        print('Indexed local document',index_document(args.path,ROOT/'knowledge/documents',reviewed=args.reviewed))
    else:
        items=json.loads(args.path.read_text(encoding='utf-8-sig'))
        if not isinstance(items,list) or len(items)>20000: raise ValueError('Reference list expected, maximum 20000')
        with store.connection() as conn:
            for item in items:
                if set(item)-{'kind','code','label','aliases','metadata','provenance'}: raise ValueError('Unknown reference fields')
                if item['kind'] not in ('unit','category','supplier','article','site','family'): raise ValueError('Unknown reference kind')
                if not all(isinstance(item[name],str) and 0<len(item[name])<=500 for name in ('code','label','provenance')):
                    raise ValueError('Reference code, label and provenance required')
                aliases=item.get('aliases',[])
                if not isinstance(aliases,list) or not all(isinstance(x,str) and len(x)<=500 for x in aliases): raise ValueError('Invalid aliases')
                conn.execute('INSERT INTO reference_entries(kind,code,label,aliases,metadata,validated,provenance) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    (item['kind'],item['code'],item['label'],Jsonb(aliases),Jsonb(item.get('metadata',{})),args.validated,item['provenance']))
        print('Imported',len(items),'local references. No existing references overwritten.')

if __name__=='__main__': main()
