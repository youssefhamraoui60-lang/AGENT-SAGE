"""Replay only user turns. Corpus assistant replies are never treated as truth.

The dialogue file supplies safety/intention labels, not field-level gold answers.
Report route coverage/continuity separately from the manually annotated fixtures.
"""
import argparse,collections,hashlib,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services.supplier_chat_flow import extract
from app.services import chat_partners,supplier_sql,supplier_dialogue
from app.services.chat_turns import norm

def evaluate(source,output,limit=0):
    def forbidden(*a,**kw):raise AssertionError('SQL disabled in offline dialogue replay')
    supplier_sql.run=forbidden;supplier_sql.load_defaults=forbidden;supplier_sql.load_reference_labels=forbidden
    counts=collections.Counter();unhandled=collections.Counter();samples=[];started=time.monotonic();max_turn_ms=0
    with source.open(encoding='utf-8-sig') as stream:
        for line in stream:
            if not line.strip():continue
            if limit and counts['conversations']>=limit:break
            row=json.loads(line)
            state={'articles':[],'partners':[]};history=[];failed=False;draft_id=None;identity_changed=False
            for turn in row['conversation']:
                if turn['role']!='user':continue
                text=turn['content'];counts['user_turns']+=1
                try:
                    turn_started=time.monotonic()
                    directed=supplier_dialogue.handle(text,state,history)
                    parsed=None if directed else extract(text,state,history)
                    if directed:
                        state=directed['state'];counts['dialogue_controller_turns']+=1;counts['handled_turns']+=1
                    elif parsed:
                        delta,grounding=parsed;old=state;state=chat_partners.merge(state,delta,grounding)
                        supplier_dialogue.remember_changes(old,state,text)
                        counts['handled_turns']+=1
                    else:
                        counts['unhandled_turns']+=1;unhandled[text]+=1;failed=True
                except Exception as exc:
                    counts['exceptions']+=1;failed=True
                    if len(samples)<30:samples.append({'id':row['id'],'input':text,'error':type(exc).__name__})
                max_turn_ms=max(max_turn_ms,(time.monotonic()-turn_started)*1000)
                if state['partners']:
                    if draft_id and state['partners'][0]['id']!=draft_id:identity_changed=True
                    draft_id=state['partners'][0]['id']
                history.append({'role':'user','content':text})
                assert not state['articles'] and not any(p.get('approved') or (p.get('operation') or {}).get('status') not in (None,'invalidated') for p in state['partners'])
            counts['conversations']+=1
            counts['single_supplier_final']+=len(state['partners'])==1
            counts['all_turns_handled_single_supplier']+=not failed and len(state['partners'])==1
            counts['draft_identity_changed']+=identity_changed
            raw_users=norm('\n'.join(t['content'] for t in history))
            for p in state['partners']:
                for key in ('nom','ice','identifiant_fiscal','rc','telephone','ville','adresse','intitule_court'):
                    if p.get(key) and norm(str(p[key])) not in raw_users:counts['ungrounded_literal_fields']+=1
    with source.open('rb') as binary:source_hash=hashlib.file_digest(binary,'sha256').hexdigest()
    root=Path(__file__).resolve().parents[1]/'backend/app'
    parser_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['services/supplier_dialogue.py','services/supplier_language.py','services/supplier_noisy_language.py','services/supplier_chat_flow.py','services/chat_model.py','schemas/conversation_entities.py']}
    report={'source_sha256':source_hash,'parser_files':parser_hashes,'sage_inserts':0,'assistant_corpus_replies_ignored':True,'field_level_gold_available':False,'counts':dict(counts),'max_turn_ms':round(max_turn_ms,2),'seconds':round(time.monotonic()-started,2),'unhandled_samples':unhandled.most_common(60),'exceptions':samples}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('unhandled_samples','exceptions')},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--limit',type=int,default=0);args=parser.parse_args();evaluate(args.source,args.output,args.limit)
