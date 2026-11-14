"""Actual TEST SELECT verification, isolated local chat memory, zero Sage writes."""
import asyncio
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from app.core.config import settings
from app.services import business_store as db,sage_crud as crud,article_agent,conversation_chat as chat

# Process-local test guards. No .env or security policy changes.
settings.business_schema='evaluation_test_'+uuid4().hex[:12]
settings.sage_writes_enabled=False
settings.sage_powershell_chat_enabled=False
original=chat.tools.run
batches=[]


def read_only_tools(calls):
    start=time.perf_counter();results=original(calls)
    batches.append({'wall_ms':round((time.perf_counter()-start)*1000,3),'calls':calls,'results':results})
    return results


async def main():
    # Import just the incident constants without the isolated evaluator's global
    # network hooks. This script only invokes the application's fixed SELECT tools.
    import ast
    tree=ast.parse((ROOT/'scripts/diagnose_multi_operations.py').read_text(encoding='utf-8'))
    text=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MULTILINE' for t in n.targets))
    db.migrate();crud.migrate();article_agent.migrate();chat.migrate()
    owner=uuid4();session=chat.create(owner);chat.tools.run=read_only_tools
    start=time.perf_counter();result=await chat.send(owner,session['id'],text,session['revision'])
    state=result['state'];p=state['partners'][0];a=state['articles'][0]
    assert p['ice']=='002033808000048' and p['forme_juridique']=='SARL AU' and p['capital']=='100 000 DH'
    assert p['annee_creation']=='2018' and p['rc']=='129251' and p['ville_rc']=='Rabat'
    assert a['designation']=='Africa EV Mobility Expo' and a['site']=='202' and a['unite']=='UN'
    assert a['gestion_stock']=='1' and a['taux_tva']=='10' and a['fournisseur_nom']=='AHMNDE'
    assert not a['categorie'] and not a['code_tva'] and not a['code_fournisseur']
    assert state['operation_plan']['sage_writes']==0
    assert all(r.get('ok') for b in batches for r in b['results'].values()),'Some real SELECT checks unavailable'
    report={'at':datetime.now(timezone.utc).isoformat(),'mode':'REAL_SQL_TEST_SELECT_ONLY_WITH_ISOLATED_LOCAL_PG',
        'schema':settings.business_schema,'conversation_id':str(session['id']),'sage_writes':0,'soap_requests':0,
        'total_service_ms':round((time.perf_counter()-start)*1000,3),'performance':result['performance'],
        'batches':batches,'state':state,'reply':result['messages'][-1]['content'],'assertions_passed':True}
    target=ROOT/'tests/ai-evaluation/reports/timeout-multi-live-readonly.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'report':str(target),'passed':True,'performance':result['performance'],'sql_batches':len(batches),
        'sql_calls':sum(len(b['calls']) for b in batches),'supplier_resolution':p['resolution']['status'],'writes':0},ensure_ascii=True))


if __name__=='__main__':asyncio.run(main())
