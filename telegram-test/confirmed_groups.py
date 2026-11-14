"""Apply scoped, user-confirmed source/reference links from learning memory.

Source and reference fingerprints must still match. No write authority or SQL
can come from a correction; the normal TEST execution checks remain in force.
"""
import hashlib
import json

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def reference_lines(rows):
    return sorted((r['ITMREF_0'].strip(),str(float(r['QTY_0'])),str(float(r['NETPRIATI_0']))) for r in rows)

def apply(rules,orders,source,links,outcomes):
    for rule in rules:
        if rule['kind']!='interpretation' or not rule['rule_key'].startswith('confirmed_source_group_'):continue
        data=rule['payload']
        ids=data.get('message_ids',[]);number=data.get('ob_number')
        if not ids or number not in orders or any(i not in source for i in ids):continue
        if fingerprint([source[i]['text'] for i in ids])!=data.get('source_sha256'):continue
        if fingerprint(reference_lines(orders[number]))!=data.get('reference_sha256'):continue
        if orders[number][0]['BPCORD_0'].strip()!=data.get('client'):continue
        involved=[o for o in outcomes if set(o['message_ids']) & set(ids)]
        if any(o['status']=='linked' and o.get('ob_number')!=number for o in involved):continue
        if any(set(o['message_ids'])-set(ids) for o in involved):continue
        outcomes[:]=[o for o in outcomes if o not in involved]
        item={'message_ids':ids,'source_date':source[ids[0]]['date'],'contact':data['contact'],
              'client_hint':data['client'],'missing':[],'candidates':[],
              'status':'linked','ob_number':number,'method':'user_confirmed_source_group',
              'correction_revision':rule.get('revision',1)}
        outcomes.append(item)
        link=links.setdefault(number,{'ob_number':number,'message_ids':[],'cases':[]})
        link['message_ids'].extend(ids);link['cases'].append(item)
