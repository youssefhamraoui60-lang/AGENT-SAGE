"""Validate all corpus parameters offline using one read-only model/reference snapshot."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services import supplier_sql as sql,chat_partners
from app.services.supplier_chat_flow import extract
source=Path(r'C:\Users\youssef\Desktop\10000_messages_fournisseurs_fr.jsonl')
raw=source.read_bytes();rows=[json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
defaults=sql.load_defaults();defaults['__reference_labels']=sql.load_reference_labels()
def forbidden(*a,**k):raise AssertionError('No SQL execution in parameter benchmark')
sql.run=forbidden;sql.load_defaults=forbidden;sql.load_reference_labels=forbidden
constraints=json.loads(Path(__file__).with_name('corpus-field-constraints.json').read_text(encoding='utf-8-sig'))
failures=[];passed=0;sage_compatible=0;size_corrections=[];needs_correction=0
for row in rows:
    try:
        delta,grounding=extract(row['message'],{})
        p=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)['partners'][0]
        values=sql.parameters(p,defaults)
        for field,key in [('ice','ICE'),('if','IF'),('rc','RC')]:
            if field in row['champs_absents']:assert values[key]==''
        assert not p.get('approved')
        passed+=1
        too_long=sorted({c['field'] for c in constraints if c['limit']>=0 and len(str(values[c['field']]).encode('utf-16-le'))//2>c['limit']})
        if too_long:
            needs_correction+=1
            if len(size_corrections)<20:size_corrections.append({'id':row['id'],'fields':too_long})
        else:sage_compatible+=1
    except Exception as exc:
        if len(failures)<30:failures.append({'id':row['id'],'error':str(exc)})
report={'source_sha256':hashlib.sha256(raw).hexdigest(),'rows':len(rows),'parameters_valid':passed,'sage_character_limits_compatible':sage_compatible,'need_explicit_size_correction':needs_correction,'size_correction_samples':size_corrections,'sage_inserts':0,'live_reads':'model OB.F103, TEST reference labels, and actual TEST column limits','failures':failures}
Path(__file__).with_name('corpus-10000-parameters.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
