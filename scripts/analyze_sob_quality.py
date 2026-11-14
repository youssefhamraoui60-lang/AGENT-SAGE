"""Source-first SOB audit: OB differences are not automatically agent errors."""
import collections,json,re,sys,functools,hashlib
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'runtime/sob-quality-audit-20261112'
sys.path.insert(0,str(ROOT/'telegram-test'))
from prepare import canonical_article,document_ices,document_issuer_names
from understanding import normalized,customer_phrases
from telegram_batch import contact_name
import learning_memory


def load(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def stamp(value):
    match=re.fullmatch(r'/Date\((\d+)\)/',str(value))
    return datetime.fromtimestamp(int(match[1])/1000,ZoneInfo('Europe/Paris')).isoformat() if match else str(value)

@functools.lru_cache(maxsize=50000)
def norm(value):return normalized(value)

def metrics(rows):
    quantities=collections.defaultdict(float);prices=collections.defaultdict(set);units=collections.defaultdict(set)
    for row in rows:
        code=row['ITMREF_0'].strip();quantities[code]+=float(row['QTY_0']);prices[code].add(float(row['NETPRIATI_0']));units[code].add(str(row.get('SAU_0','')).strip())
    return dict(quantities),{k:sorted(v) for k,v in prices.items()},{k:sorted(v) for k,v in units.items()}


def source_goods(text,articles):
    goods={};prices={}
    for line in text.splitlines():
        match=re.search(r'(?i)^\s*(\d+(?:[.,]\d+)?)\s*(kg|kgs|tonnes?|t|sacs?|sachet?s?)\s+(?:de\s+)?((?:rab|fer|cpj|ciment|cima|sima)\s*0?(?:35|45|55|6|8|10|12|14|16|20|25|32))\b(.*)',line)
        if not match:continue
        code=canonical_article(match[3]);article=articles.get(code)
        if not article:continue
        qty=float(match[1].replace(',','.'));unit=match[2].lower();sales=article['SAU_0'].strip()
        if unit in ('t','tonne','tonnes'):
            if sales=='KG':qty*=1000
            elif sales=='SAC' and code.startswith('CPJ'):qty*=20
            else:continue
        elif unit.startswith('kg') and sales!='KG':continue
        elif unit.startswith(('sac','sachet')) and sales!='SAC':continue
        if code in goods:goods.pop(code,None);continue
        goods[code]=qty
        price=re.search(r'(?i)(?:=|prix\s*[:=]?)\s*(\d+(?:[.,]\d+)?)\s*(?:dh|mad)?',match[4])
        if price and sales=='SAC':prices[code]=float(price[1].replace(',','.'))
    return goods,prices


def main():
    source=load('messages-layout.json')
    previous=ROOT/'runtime/sob-day-20261111/messages-reviewed.json'
    if previous.exists():
        old={r['id']:r for r in json.loads(previous.read_text(encoding='utf-8')) if r.get('visual_review')}
        for row in source:
            if row['id'] in old and hashlib.sha256((OUT/row['file']).read_bytes()).hexdigest()==old[row['id']]['visual_review']['sha256']:
                row['layout_text']=old[row['id']]['layout_text'];row['visual_review']=old[row['id']]['visual_review']
    visual=OUT/'visual-transcriptions.json'
    if visual.exists():
        reviews=load('visual-transcriptions.json')
        for row in source:
            if str(row['id']) in reviews and hashlib.sha256((OUT/row['file']).read_bytes()).hexdigest()==reviews[str(row['id'])]['sha256']:
                row['layout_text']=reviews[str(row['id'])]['text'];row['visual_review']=reviews[str(row['id'])]
    customers={r['BPCNUM_0'].strip():r for r in load('ob-customers.json')['rows']}
    identities={r['BPCNUM_0'].strip():r for r in load('ob-customer_identities.json')['rows']}
    articles={r['ITMREF_0'].strip():r for r in load('ob-articles.json')['rows']}
    names=collections.defaultdict(set);ices=collections.defaultdict(set);grams=collections.defaultdict(set)
    for code,c in customers.items():
        name=norm(c['BPCNAM_0']);names[name].add(code)
        for gram in {name[i:i+3] for i in range(len(name)-2)}:grams[gram].add(code)
        ice=str(identities.get(code,{}).get('XICE_0','')).strip()
        if ice:ices[ice].add(code)
    test_customers={r['BPCNUM_0']:1 for r in load('test_customer_catalog.json')['rows']}
    def identify(text,caption):
        explicit={c.upper() for c in re.findall(r'\bC\d{4,8}\b',caption,re.I) if c.upper() in customers}
        if len(explicit)==1:return next(iter(explicit)),'Code client explicite',1.0
        found=set().union(*(ices.get(ice,set()) for ice in document_ices(text))) if document_ices(text) else set()
        found={c for c in found if not re.search(r'(?i)(?:ould|ouled).*bouaz',customers[c]['BPCNAM_0'])}
        if len(found)==1:return next(iter(found)),'ICE exact du document',1.0
        queries=(document_issuer_names(text) if 'DOCUMENT JOINT' in text else [])+customer_phrases(caption)
        queries=[q for q in queries if norm(q) not in {'sonasid','sonasid100','sounacid','sounassid','cimat','holcim','lafarge','temara','novacim'}]
        exact=set().union(*(names.get(norm(q),set()) for q in queries)) if queries else set()
        exact={c for c in exact if not re.search(r'(?i)(?:ould|ouled).*bouaz',customers[c]['BPCNAM_0'])}
        if len(exact)==1:return next(iter(exact)),'Nom source exact et unique',.98
        ranking={}
        for query in queries:
            clean=norm(query)
            if len(clean)<5:continue
            candidates=collections.Counter(c for i in range(len(clean)-2) for c in grams.get(clean[i:i+3],set()))
            for code,_ in candidates.most_common(30):
                candidate=norm(customers[code]['BPCNAM_0'])
                score=1 if clean==candidate else SequenceMatcher(None,clean,candidate).ratio()
                if min(len(clean),len(candidate))>=6 and (candidate in clean or clean in candidate):score=max(score,.94)
                ranking[code]=max(ranking.get(code,0),score)
        top=sorted(ranking.items(),key=lambda x:x[1],reverse=True)
        if top and top[0][1]>=.90 and (len(top)==1 or top[0][1]-top[1][1]>=.07):return top[0][0],'Nom source approchant (à confirmer)',top[0][1]
        return None,'Identité source non établie',0
    ob=collections.defaultdict(list);test=collections.defaultdict(list)
    for row in load('ob-orders.json')['rows']:ob[row['SOHNUM_0'].strip()].append(row)
    for row in load('ob-test_orders_audit.json')['rows']:test[row['SOHNUM_0'].strip()].append(row)
    receipts=load('agent-reviews.json');preps={r['owner']:r for r in load('agent-sob_preparations.json')}
    batches={r['id']:r for r in load('routing-batches.json')}
    mapping={r['message']:r['batch'] for r in load('routing-source_messages.json') if r['source']==-1004375687420}
    buckets=collections.defaultdict(list)
    for row in source:buckets[mapping.get(row['id'],'unprocessed:'+str(row['id']))].append(row)
    cases=[];lines=[];document_rows=[]
    for key,rows in sorted(buckets.items(),key=lambda item:min(r['id'] for r in item[1])):
        ids=sorted(r['id'] for r in rows);batch=batches.get(key,{})
        related=[r for r in receipts if re.match(r'^telegram:-1004375687420:\d+:(?:'+ '|'.join(map(str,ids))+r')$',r['owner'])]
        reply=batch.get('reply') or 'Aucune réponse retrouvée dans le journal'
        numbers=set(re.findall(r'\b2026ARC\d+\b',reply));numbers.update(r['number'] for r in related if r.get('status')=='created' and r.get('number'))
        actual=[row for n in numbers for row in test.get(n,[])]
        source_text='\n\n'.join(r['text'] for r in rows)
        full='\n\n'.join(r['text']+('\nDOCUMENT JOINT :\n'+r.get('layout_text','') if r.get('file') else '') for r in rows)
        client,proof,confidence=identify(full,source_text)
        visual_clients={r.get('visual_review',{}).get('client_code') for r in rows if r.get('visual_review',{}).get('client_code') in customers}
        if len(visual_clients)==1:
            client=next(iter(visual_clients));proof='Identit? l?gale confirm?e visuellement sur le document';confidence=.99
        agent_clients=sorted({r['BPCORD_0'].strip() for r in actual})
        client_for_match=client or (agent_clients[0] if len(agent_clients)==1 else None)
        quantities,prices,units=metrics(actual) if actual else ({},{},{})
        explicit_goods,explicit_prices=source_goods(source_text,articles)
        for row in rows:
            visual=row.get('visual_review',{})
            explicit_goods.update(visual.get('goods',{}));explicit_prices.update(visual.get('prices',{}))
        candidate_goods=quantities or explicit_goods
        goods={k:v for k,v in candidate_goods.items() if k!='MANTD'}
        same_day=rows[0]['date'][:10]
        candidates=[]
        for number,obrows in ob.items():
            head=obrows[0]
            if not client_for_match or head['BPCORD_0'].strip()!=client_for_match:continue
            oq,op,ou=metrics(obrows);og={k:v for k,v in oq.items() if k!='MANTD'}
            common=set(goods)&set(og);union=set(goods)|set(og)
            article_match=len(common)/len(union) if union else float(bool(quantities and oq))
            qty_match=sum(abs(goods[k]-og[k])<.00001 for k in common)/max(len(union),1)
            price_match=sum(prices.get(k)==op.get(k) for k in common)/max(len(union),1) if actual else 0
            day_match=stamp(head['ORDDAT_0'])[:10]==same_day
            score=.38+.23*article_match+.25*qty_match+.08*price_match+.06*day_match
            if not goods:score=.38+.10*day_match
            candidates.append({'number':number,'score':round(score,4),'client':head['BPCORD_0'].strip(),'name':head['BPCNAM_0'].strip(),'article_match':article_match,'qty_match':qty_match,'same_day':day_match})
        candidates.sort(key=lambda c:c['score'],reverse=True)
        selected=None;match_level='Aucun rapprochement'
        if candidates:
            first=candidates[0];margin=first['score']-candidates[1]['score'] if len(candidates)>1 else 1
            if first['score']>=.82 and margin>=.04:selected=first['number'];match_level='Fort : client/articles/quantités'
            elif first['article_match']>=.75 and margin>=.07:selected=first['number'];match_level='Probable : quantités/prix à vérifier'
            elif len([c for c in candidates if c['same_day']])==1:
                selected=next(c['number'] for c in candidates if c['same_day']);match_level='Candidat : seul même client ce jour'
            else:match_level='Ambigu : plusieurs commandes possibles'
        issues=[];severity='À vérifier'
        if actual:
            severity='Contrôle source incomplet'
            if client and confidence>=.98 and any(c!=client for c in agent_clients):
                issues.append('CLIENT TEST DIFFÉRENT DE LA PREUVE SOURCE');severity='Critique — preuve source'
            for code,qty in explicit_goods.items():
                if abs(quantities.get(code,0)-qty)>.00001:
                    issues.append('Quantité source '+code+'='+str(qty)+' ; TEST='+str(quantities.get(code,0)));severity='Majeur — preuve source'
            for code,price in explicit_prices.items():
                if code in prices and any(abs(p-price)>.00001 for p in prices[code]):
                    issues.append('Prix explicite source '+code+'='+str(price)+' ; TEST='+str(prices[code]));severity='Majeur — preuve source'
            zero=[k for k,v in prices.items() if 0 in v]
            if zero:issues.append('Prix TTC nul à contrôler : '+', '.join(zero))
            if selected:
                oq,op,ou=metrics(ob[selected]);different=[]
                for code in sorted(set(quantities)|set(oq)):
                    status=[]
                    if quantities.get(code)!=oq.get(code):status.append('quantité')
                    if prices.get(code)!=op.get(code):status.append('prix')
                    if units.get(code)!=ou.get(code):status.append('unité')
                    lines.append({'case':key,'messages':','.join(map(str,ids)),'commandes_TEST':','.join(sorted(numbers)),'commande_OB':selected,'client_source':client,'article':code,'designation':articles.get(code,{}).get('ITMDES1_0',''),'quantite_source':explicit_goods.get(code),'quantite_TEST':quantities.get(code),'quantite_OB':oq.get(code),'prix_source':explicit_prices.get(code),'prix_TEST':prices.get(code),'prix_OB':op.get(code),'unite_TEST':units.get(code),'unite_OB':ou.get(code),'ecart':', '.join(status) or 'Identique','attribution':'Source explicite disponible' if code in explicit_goods or code in explicit_prices else 'Différence OB/TEST seule : décision manuelle possible'})
                    if status:different.append(code+' ('+', '.join(status)+')')
                if different:issues.append('Écarts OB/TEST (non attribués sans source) : '+', '.join(different))
                elif not issues:severity='Concordance OB/TEST sur le rapprochement retenu'
        else:
            severity='Non créée / à préciser'
            if client:issues.append('Client retrouvé dans OB : '+client+' ; présent TEST='+str(test_customers.get(client,'à contrôler')))
        attempts=[b for b in batches.values() if b['source']==-1004375687420 and (b['id'].split(':')[1].isdigit() and int(b['id'].split(':')[1]) in ids)]
        attempts.sort(key=lambda b:b.get('created_at',''))
        item={'case':key,'ids':ids,'date':rows[0]['date'],'contact':contact_name(source_text),'periode_15h':'Après 15h' if int(rows[0]['date'][11:13])>=15 else 'Avant 15h','source_text':source_text,'full_text':full,'agent_reply_first':attempts[0].get('reply','') if attempts else reply,'agent_reply':reply,'attempts':len(attempts),'test_numbers':sorted(n for n in numbers if n in test),'agent_clients':agent_clients,'source_client':client,'source_client_name':customers.get(client,{}).get('BPCNAM_0',''),'source_client_proof':proof,'source_client_confidence':confidence,'selected_ob':selected,'match_level':match_level,'ob_candidates':candidates[:5],'severity':severity,'issues':issues,'files':[r['id'] for r in rows if r.get('file')],'source_goods':explicit_goods,'source_prices':explicit_prices}
        cases.append(item)
    output={'scope':{'start':'2026-11-11','end':'2026-11-12','latest_message':max(r['date'] for r in source),'note':'Période complète, avec filtre avant/après 15h ; OB du 10 inclus comme contexte de rapprochement.'},'cases':cases,'line_differences':lines,'source':source,'counts':{'messages':len(source),'cases':len(cases),'created_cases':sum(bool(c['test_numbers']) for c in cases),'strong_matches':sum(c['match_level'].startswith('Fort') for c in cases),'source_errors':sum('preuve source' in c['severity'] for c in cases),'noncreated':sum(not c['test_numbers'] for c in cases)}}
    (OUT/'analysis-reviewed.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output['counts']))
    for c in cases:
        if 'preuve source' in c['severity'] or c['files'] or (not c['test_numbers'] and c['source_client']):
            print(json.dumps({k:c[k] for k in ['ids','test_numbers','source_client','source_client_name','source_client_proof','selected_ob','match_level','severity','agent_reply','issues','files']},ensure_ascii=True))

if __name__=='__main__':main()
