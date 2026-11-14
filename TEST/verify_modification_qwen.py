"""Real bounded Qwen fallback + real TEST previews; no confirmation, no execution."""
import sys,json,time
from uuid import uuid4
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.services import modification_dialogue as dialogue,modification_actions as actions
from app.core.config import settings

def main():
    settings.sage_modification_enabled=True;results=[]
    cases=[('fr','Modifie l’appellation du fournisseur F10014 pour FOURNISSEUR QA','FOURNISSEUR QA'),('darija','bdel smiya dyal frs F10014 l FOURNISSEUR QA DARIJA','FOURNISSEUR QA DARIJA')]
    for language,text,expected in cases:
        start=time.monotonic();values=dialogue.semantic_changes(text,'supplier',{})
        d={'id':str(uuid4()),'folder':'TEST','resource':'supplier','code':'F10014','changes':values};actions.prepare_draft(d);op=d.get('operation',{})
        passed=d.get('changes',{}).get('name')==expected and op.get('status')=='prepared' and op.get('preview',{}).get('transaction_state')=='VALIDATED_NO_WRITE'
        row={'language':language,'passed':passed,'real_qwen_forced':True,'seconds':round(time.monotonic()-start,2),'recognized_changes':d.get('changes'),'operation_status':op.get('status'),'reply':op.get('message'),'sage_writes':0}
        print(json.dumps(row,ensure_ascii=True),flush=True);results.append(row)
    (ROOT/'TEST/modification-qwen-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(r['passed'] for r in results)

if __name__=='__main__':main()
