"""Read-only incident replay: real Ollama, isolated PG, simulated ERP tools."""
import argparse
import asyncio
import json
import time
from pathlib import Path
import evaluate_human_conversations as evaluation

TEXT="je veuxc réer la articles et le founiseur mon forniseur c'est AHMNDE Forme juridique SARL AU Capital 100 000 DH Année de création 2018 RC 129251 (Rabat) ICE 002033808000048 prer créer le articles Africa EV Mobility Expo etreffirzncer avce le forniseur que tu a crééer le uniter de articles est UN LE TVA 10 le articles dois non gérer on stok et dans le site de fréer géniro 202"
MULTILINE="je veuxc réer la articles et le founiseur  mon forniseur c'est AHMNDE Forme juridique\nSARL AU\nCapital\n100 000 DH\nAnnée de création\n2018 (8 ans)\nRC\n129251 (Rabat)\nICE\n002033808000048 prer créer le articles Africa EV Mobility Expo etreffirzncer avce le forniseur que tu a crééer   le uniter de articles est UN LE TVA 10 le articles dois non gérer on stok et dans le site de fréer géniro 202"


async def main(label):
    root=Path(__file__).resolve().parents[1]
    measured={'label':label,'writes':0,'model_requests':[],'sql_mode':'simulated','soap_requests':0}
    original=evaluation.chat_model.request_stream
    async def request(client,payload):
        record={'input_characters':sum(len(m['content']) for m in payload['messages']),
                'schema_characters':len(json.dumps(payload['format'])),'options':payload['options']}
        measured['model_requests'].append(record);start=time.perf_counter()
        try:
            body,timings=await original(client,payload)
            record.update(timings=timings,done=body.get('done'),done_reason=body.get('done_reason'),output_characters=len(body.get('message',{}).get('content','')))
            return body,timings
        except Exception as exc:
            record['error_type']=type(exc).__name__;raise
        finally:record['elapsed_ms']=round((time.perf_counter()-start)*1000,3)
    evaluation.chat_model.request_stream=request
    evaluation.scenarios=lambda:[{'id':'ahmnde-'+label,'persona':'demande utilisateur exacte','cardinality':1,'path':'multi-operations',
        'turns':[evaluation.step(TEXT,article_count=1,partner_count=1,articles={'designation':'Africa EV Mobility Expo','unite':'UN','taux_tva':'10','gestion_stock':'1','site':'202','fournisseur_nom':'AHMNDE'})]}]
    measured['configured_ai_timeout_seconds']=evaluation.settings.business_ai_timeout
    start=time.perf_counter()
    try:measured['exit_code']=await evaluation.run(argparse.Namespace(only='',limit=1))
    finally:
        measured['total_ms']=round((time.perf_counter()-start)*1000,3)
        target=root/'tests/ai-evaluation/reports'/('timeout-multi-'+label+'.json')
        target.write_text(json.dumps(measured,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(measured,ensure_ascii=True),flush=True)
    return measured['exit_code']


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args().label)))
