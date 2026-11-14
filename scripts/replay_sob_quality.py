"""Read-only preparations, never order creation, for the quality audit."""
import asyncio,json,sys,concurrent.futures
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'runtime/sob-quality-audit-20261112'
sys.path.insert(0,str(ROOT/'telegram-test'))
import prepare,learning_memory
def load(n):return json.loads((OUT/n).read_text(encoding='utf-8'))
def main():
    before=learning_memory.rules()
    (OUT/'learning-before-audit.json').write_text(json.dumps(before,default=str,ensure_ascii=False,indent=2),encoding='utf-8')
    verified={}
    for label,code in [('Acier HA diamètre 6 mm','RABT6'),('Acier HA diamètre 12 mm','RAB12'),('BRIQUE 07','BQ7')]:
        rows=prepare.lookup('article',code)
        if any(r['ITMREF_0'].strip()==code for r in rows):
            verified[label]=learning_memory.save('article_alias',label,{'code':code},actor='Codex audit SOB',source='Demande utilisateur audit 12/11/2026 ; vérification Sage TEST en lecture seule ; libellés explicites des documents 5171/5325.',approved=True)
    verified['source_guard']=learning_memory.save('interpretation','audit_source_article_5204',{'rule':'Un diamètre RAB explicite dans le message doit être conservé. Unité KG seule ne permet pas de sélectionner un article sans correspondance lexicale. Bloquer toute substitution ou omission.', 'source_message':5204,'observed_test':'2026ARC15142','expected_article':'RAB10'},actor='Codex audit SOB',source='Demande utilisateur de vérifier et corriger ; message 5204 : 1000 kg rab 10 sonasid. Mauvais article FL_ET constaté en TEST.',approved=True)
    (OUT/'learning-audit-saved.json').write_text(json.dumps(verified,ensure_ascii=False,indent=2),encoding='utf-8')
    analysis=load('analysis-reviewed.json'); preps=load('agent-sob_preparations.json'); visual=load('visual-transcriptions.json')
    wanted=[c for c in analysis['cases'] if (not c['test_numbers'] and (c['files'] or c['source_client'])) or 5204 in c['ids']]
    results=[]
    def one(c):
        try:
            histories=[p for p in preps if p['owner'].startswith('telegram:-1004375687420:') and any(p['owner'].endswith(':'+str(i)) for i in c['ids'])]
            history=json.loads(histories[-1]['history']) if histories else [{'role':'user','content':c['full_text']}]
            # Reprocess clear source text only; no quantities/prices imported from OB.
            if c['files']:
                history=[{'role':'user','content':c['full_text']}]
            detail=asyncio.run(prepare.prepare(history,details=True,reference_date=date.fromisoformat(c['date'][:10])))
            return {'case':c['case'],'ids':c['ids'],'ok':True,'details':detail,'mode':'Préparation seule ; aucun appel de création'}
        except Exception as e:return {'case':c['case'],'ids':c['ids'],'ok':False,'error':type(e).__name__+': '+str(e)[:300]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for r in pool.map(one,wanted):
            results.append(r)
            (OUT/'readonly-replays.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            print(json.dumps({'ids':r['ids'],'ok':r['ok'],'done':len(results),'total':len(wanted)}),flush=True)
    persist_examples(analysis,results)

def persist_examples(analysis,results):
    from psycopg.types.json import Jsonb
    bycase={r['case']:r for r in results}
    with learning_memory.db.connection() as conn:
        for c in analysis['cases']:
            expected={'article':'RAB10','quantity':1000,'unit':'KG','price':'absent du message'} if 5204 in c['ids'] else None
            conn.execute('''INSERT INTO sob_learning_examples(source_key,input_data,expected,observed,status)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(source_key) DO NOTHING''',
                ('quality-20261112-'+','.join(map(str,c['ids'])),Jsonb({'messages':c['ids'],'text':c['source_text']}),Jsonb(expected) if expected else None,
                 Jsonb({'test':c['test_numbers'],'ob_candidate':c['selected_ob'],'matching':c['match_level'],'issues':c['issues'],'readonly_replay':bycase.get(c['case'])}),
                 'source_error_confirmed' if expected else 'audit_needs_review'))
    (OUT/'learning-examples-audit.json').write_text(json.dumps({'stored_cases':len(analysis['cases']),'ob_is_expected_truth':False}),encoding='utf-8')
if __name__=='__main__':main()
