"""Offline extraction benchmark. Never connects to Sage or executes SQL."""
import argparse,collections,hashlib,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services.supplier_chat_flow import extract
from app.services import chat_partners
from app.services.chat_turns import norm
from app.services.supplier_dates import normalize_date

KEYS={'if':'identifiant_fiscal','IF':'identifiant_fiscal','ICE':'ice','RC':'rc','paiement':'conditions_paiement'}
def evaluate(source,limit,output,legacy=False):
    from app.services import supplier_sql,supplier_language
    def forbidden(*args,**kwargs):raise AssertionError('SQL forbidden during offline benchmark')
    supplier_sql.run=forbidden;supplier_sql.load_defaults=forbidden;supplier_sql.load_reference_labels=forbidden
    if legacy:supplier_language.extract_request=lambda message:None
    snapshot=Path(__file__).with_name('corpus-reference-labels.json')
    references=json.loads(snapshot.read_text(encoding='utf-8'))['rows'] if snapshot.exists() else []
    raw=source.read_bytes()
    rows=[json.loads(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()] if source.suffix=='.jsonl' else json.loads(raw.decode('utf-8-sig'))['messages']
    if limit:rows=rows[:limit]
    counts=collections.Counter();groups=collections.defaultdict(collections.Counter);splits=collections.defaultdict(collections.Counter);failures=[];other_failures=[];started=time.monotonic()
    for index,row in enumerate(rows):
        expected={KEYS.get(k,k):normalize_date(v) if k=='date_regularite' else v for k,v in (row.get('donnees_attendues') or row['attendu']).items()}
        actual={};error=None
        try:
            parsed=extract(row['message'],{})
            if parsed:
                delta,grounding=parsed
                state=chat_partners.merge({'articles':[],'partners':[]},delta,grounding)
                if len(state['partners'])==1:actual={k:v for k,v in state['partners'][0].items() if k in expected or k in {'nom','ice','identifiant_fiscal','rc','ville','adresse','telephone','fax','conditions_paiement','devise','type_montant','date_regularite'}}
                assert not any(p.get('approved') for p in state['partners'])
        except Exception as exc:error=type(exc).__name__
        compared=dict(actual)
        if expected.get('conditions_paiement') and actual.get('conditions_paiement'):
            matches={r['code'] for r in references if r['kind']=='Paiement' and supplier_sql.reference_norm(r['label'])==supplier_sql.reference_norm(actual['conditions_paiement'])}
            if len(matches)==1 and expected['conditions_paiement'] in matches:compared['conditions_paiement']=matches.pop()
        wrong=[k for k,v in expected.items() if norm(str(compared.get(k,'')))!=norm(str(v))]
        extra=[k for k,v in actual.items() if k not in expected and v]
        ok=not wrong and not extra and not error
        address_preserved=(wrong==['adresse'] and not extra and not error and
            norm(str(actual.get('adresse',''))).startswith(norm(expected['adresse'])+',') and
            norm(str(actual['adresse'])) in norm(row['message']) and '\n' not in actual['adresse'])
        counts['messages']+=1;counts['exact']+=ok;counts['errors']+=bool(error)
        counts['complete_with_full_original_address']+=bool(address_preserved)
        counts['complete_or_address_preserved']+=bool(ok or address_preserved)
        groups[row['scenario']]['messages']+=1;groups[row['scenario']]['exact']+=ok
        split='development_first_2000' if index<2000 else 'validation_remaining'
        splits[split]['messages']+=1;splits[split]['exact']+=ok
        if not ok and len(failures)<60:failures.append({'id':row['id'],'message':row['message'],'expected':expected,'actual':actual,'wrong':wrong,'extra':extra,'error':error})
        if not ok and not address_preserved and len(other_failures)<30:other_failures.append({'id':row['id'],'message':row['message'],'expected':expected,'actual':actual,'wrong':wrong,'extra':extra,'error':error})
    root=Path(__file__).resolve().parents[1]/'backend/app'
    parser_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['services/supplier_language.py','services/supplier_noisy_language.py','services/supplier_chat_flow.py','services/chat_model.py','schemas/conversation_entities.py']}
    report={'source_sha256':hashlib.sha256(raw).hexdigest(),'parser_sha256':hashlib.sha256(json.dumps(parser_hashes,sort_keys=True).encode()).hexdigest(),'parser_files':parser_hashes,'synthetic_corpus':True,'legacy':legacy,'sage_writes':0,'model_training':False,'counts':dict(counts),'accuracy':counts['exact']/counts['messages'],'seconds':round(time.monotonic()-started,2),'splits':dict(splits),'scenarios':dict(groups),'failure_samples':failures}
    report['other_failure_samples']=other_failures
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('failure_samples','other_failure_samples','scenarios','parser_files')},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--limit',type=int,default=0);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--legacy',action='store_true');args=parser.parse_args()
    evaluate(args.source,args.limit,args.output,args.legacy)
