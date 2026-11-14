"""Locate the existing Telfix draft; do not create a session or approve anything."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services import business_store as db
with db.connection() as conn:
    rows=conn.execute("""SELECT id,revision,updated_at,state FROM chat_conversations c
        WHERE EXISTS(SELECT 1 FROM jsonb_array_elements(COALESCE(c.state->'partners','[]'::jsonb)) p
        WHERE lower(p->>'nom') IN (%s,%s)) ORDER BY updated_at DESC LIMIT 5""",('télfix','telfix')).fetchall()
    for row in rows:
        print(json.dumps({'id':str(row['id']),'revision':row['revision'],
            'suppliers':[{'id':p['id'],'name':p.get('nom'),'reviewed':p.get('reviewed'),
                'status':p.get('operation',{}).get('status'),'fields':{k:v for k,v in p.items() if isinstance(v,(str,int))}}
                for p in row['state'].get('partners',[]) if p.get('nom','').casefold() in ('télfix','telfix')]},ensure_ascii=False))
