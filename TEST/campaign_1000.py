"""Reproducible conversation corpus and independent, per-turn state oracles.

40 behavioural families x 25 personas, not a corpus of equivalent greetings.
No model-generated expectations and no execution/approval endpoints.
"""
import copy,json
from pathlib import Path
from uuid import uuid4

FAMILIES=['supplier_prose','supplier_darija','supplier_invalid_ice','supplier_email','supplier_payment','supplier_incomplete','three_ordinals','three_email','second_supplier','duplicates','pg_interruption','supplier_unknown_contact','after_creation_city','after_creation_unknown_phone','repair_resource','supplier_lookup','supplier_disable','supplier_reactivate','switch_target','cancel_phone','supplier_city','supplier_address','ambiguous_supplier','article_designation','article_tax','article_accounting','general_account','article_disable','article_used_disable','article_activate','article_site_add','article_site_remove','article_site_activate','article_creation','article_markdown','article_multiturn','mixed_summary','api_failure','json_failure','sql_failure']
CITIES=['Rabat','Casablanca','Agadir','Fes','Tanger']
def partner(name='ATLAS TEST',city='Rabat'):
 return {'id':str(uuid4()),'kind':'supplier','nom':name,'ville':city,'sources':{},'approved':False,'operation':{'status':'invalidated'}}
def group(rows):
 return {'articles':[],'partners':rows,'supplier_tasks':{'version':1,'active':'create','group':{'id':str(uuid4()),'expected_count':len(rows),'status':'draft'},'history':[],'control':None},'active_supplier_task':'create'}
def modification(resource,code):
 return {'articles':[],'partners':[],'modification_drafts':[{'id':str(uuid4()),'folder':'TEST','resource':resource,'code':code,'changes':{},'operation':{'status':'needs_input'}}]}
def step(text,eq=None,contains=(),**kw):return {'text':text,'eq':eq or {},'contains':list(contains),**kw}
def build(family,i):
 name=['ATLAS NEGOCE','RIF ELECTRIC','NOVA EQUIPEMENT','SUD SERVICES','OCEAN LOGISTICS'][i%5]+' '+str(i).zfill(2)
 city=CITIES[i%5];phone='06'+str(10000000+i);newphone='07'+str(20000000+i);code='F'+str(500+i);art='CAMPART'+str(i).zfill(3);ice='00'+str(1000000000000+i)
 s={'id':family+'-'+str(i).zfill(2),'family':family,'persona':i,'language':['fr','fr_fautes','darija_fr','fr_email','fr_incomplet'][i%5],'initial':{},'steps':[],'fault':None}
 p={'partners.0.nom':name,'partners.0.ville':city};md='modification_drafts.-1.'
 def supplier_seed():s['initial']=modification('supplier',code)
 def article_seed():s['initial']=modification('article',art)
 if family=='supplier_prose':
  s['steps']=[step(f"bonjour je veux crrer un nevelle fourniseur il s'appelle {name}, c'est une SARL AU à {city}, mais je connais pas encore son ICE",p),step('la ville aussi c’est Casablanca, machi Rabat',{'partners.0.ville':'Casablanca','partners.0.nom':name}),step('ne crée rien pour le moment, conserve seulement le brouillon',{'supplier_creation_hold':True})]
 elif family=='supplier_darija':
  s['steps']=[step(f'Salam bghit ncréer fournisseur jdid smito {name}, kayn f {city}, SARL AU, téléphone {phone}, ICE mazal ma3ndich.',{**p,'partners.0.telephone':phone}),step('had fournisseur rah SARL AU walakin ma3ndich ICE daba',{**p,'partners.0.telephone':phone}),step('résume les informations manquantes',p,contains=[name])]
 elif family=='supplier_invalid_ice':
  s['steps']=[step(f'bonjour je veux céer un fourniseur {name} leur ville est {city} le ice est {ice[:-1]}',{**p,'partners.0.ice':ice[:-1],'partners.0.operation.status':'blocked'},contains=['14']),step('OUI',{'partners.0.operation.status':'blocked'},contains=['15']),step('cv',p,contains=['Ça va'])]
 elif family=='supplier_email':
  text=f'Objet : création fournisseur\nBonjour Youssef,\nMerci de créer le fournisseur suivant :\nNom : {name}\nVille : {city}\nICE : {ice}\nTéléphone : {phone}\nCordialement.'
  s['steps']=[step(text,{**p,'partners.0.ice':ice,'partners.0.telephone':phone}),step('le nom est '+name+' BIS',{'partners.0.nom':name+' BIS','partners.0.ice':ice}),step('bonjour',{'partners.0.ice':ice})]
 elif family=='supplier_payment':
  s['initial']={'articles':[],'partners':[partner(name,city)]};s['steps']=[step('paiement cheque 30 jours',{'partners.0.conditions_paiement':'cheque 30 jours'}),step('paiement effet 60 jours',{'partners.0.conditions_paiement':'effet 60 jours','partners.0.nom':name}),step('je ne connais pas encore son ICE',{'partners.0.conditions_paiement':'effet 60 jours'})]
 elif family=='supplier_incomplete':
  s['steps']=[step('je veux créer un fournisseur',contains=['nom']),step('le fournisseur s’appelle '+name,{'partners.0.nom':name}),step('la ville est '+city,p)]
 elif family in ('three_ordinals','three_email'):
  names=[name+' A',name+' B',name+' C']
  if family=='three_email':opening='Bonjour, merci de préparer les fiches des trois fournisseurs suivants : '+ ' '.join(f'{j+1}. {n} — {c} — SARL AU' for j,(n,c) in enumerate(zip(names,['Casablanca','Rabat','Agadir'])))+' Nous ne disposons pas encore des ICE ni des registres de commerce. Merci de vérifier les éventuels doublons.';s['steps']=[step(opening,{f'partners.{j}.nom':n for j,n in enumerate(names)})]
  else:s['steps']=[step('je veux crrer 3 nevelle fourniseur en même temps',length={'partners':3}),step(f"le premier c'est {names[0]} à casa, le 2eme {names[1]} f rabat et le troisième c'est {names[2]} à agadir",{f'partners.{j}.nom':n for j,n in enumerate(names)})]
  s['steps'] += [step('pour le premier c’est SARL AU, le 2eme SARL et le 3eme je connais pas encore la forme juridique',{'partners.0.forme_juridique':'SARL AU','partners.1.forme_juridique':'SARL'}),step('résume mes demandes séparément',length={'partners':3},contains=names)]
 elif family=='second_supplier':
  s['steps']=[step(f'zid fournisseur jdid smito {name}, kayn f {city}',p),step(f'zid fournisseur tani smito AUTRE {i}, f Rabat, SARL, téléphone {phone}. Kheli le premier kif ma howa.',{**p,'partners.1.nom':f'AUTRE {i}'}),step('Pour le premier le bon numéro c’est '+newphone+', matbdelch dyal deuxième.',{'partners.0.telephone':newphone,'partners.1.telephone':phone})]
 elif family=='duplicates':
  s['initial']=group([partner(name,city)]);s['fault']='duplicate';s['steps']=[step('vérifie les doublons dans Sage TEST',{'partners.0.operation.status':'blocked'},contains=['F900']),step('résume les demandes',{'partners.0.operation.status':'blocked'},contains=['F900']),step('ne crée rien pour le moment',{'supplier_creation_hold':True})]
 elif family=='pg_interruption':
  s['steps']=[step('cv',contains=['Ça va']),step('cv',pg_fail=True),step('je veux créer un article',{'pending_creation.resource':'article'},contains=['désignation'])]
 elif family=='supplier_unknown_contact':
  s['initial']=group([partner(name,city)]);s['steps']=[step('had fournisseur rah SARL AU walakin ma3ndich ICE daba',{'partners.0.forme_juridique':'SARL AU',**p}),step('je veux ajouter son email mais je le connais pas encore',p),step('le fournisseur est une SARL AU avec un capital de '+str(100000+i)+' DH',{'partners.0.capital':str(100000+i)+' DH'})]
 elif family in ('after_creation_city','after_creation_unknown_phone'):
  row=partner(name,city);row['operation']={'status':'succeeded','record_keys':{'BPSNUM':code}};s['initial']=group([row])
  if family=='after_creation_city':s['steps']=[step('je veux modifier le vile a Agadir',{md+'resource':'supplier',md+'code':code,md+'changes.city':'Agadir','partners.0.ville':city}),step('pour quoi tu pas comprer mon message',contains=[code,'Agadir']),step('bonjour',contains=['Bonjour'])]
  else:s['steps']=[step(f'Je veux modifier le téléphone de {code}, mais je connais pas encore le nouveau numéro. Prépare rien à enregistrer.',{md+'resource':'supplier',md+'changes':{}}),step('dans le fiche fourniseur pas articles',{md+'resource':'supplier',md+'changes':{}}),step('annule la modification',{md+'operation.status':'cancelled'})]
 elif family=='repair_resource':
  s['initial']=modification('article',code);s['initial']['modification_drafts'][0]['pending_field']='phone'
  s['steps']=[step('c’est un fournisseur pas articles',{md+'resource':'supplier',md+'code':code}),step('dans la fiche fournisseur pas articles',{md+'changes':{}}),step('annule la modification',{md+'operation.status':'cancelled'})]
 elif family in ('supplier_lookup','supplier_disable','supplier_reactivate','sql_failure'):
  s['initial']=group([partner(name,city)])
  if family=='sql_failure':s['fault']='sql'
  first=f'cherche le fournisseur {code} et donne son nom et statut' if family in ('supplier_lookup','sql_failure') else f'je veux désactiver {code} mais vérifie les commandes et factures' if family=='supplier_disable' else f'peut-on réactiver {code} s’il est inactif ?'
  s['steps']=[step(first,{'supplier_tasks.control.code':code},contains=[code]),step('résume mes demandes',p,contains=[code]),step('bonjour',p)]
  if family=='supplier_disable':s['steps'][0]['contains']+=['non prise en charge']
  if family=='supplier_reactivate':s['steps'][0]['contains']+=['consultation']
 elif family in ('switch_target','cancel_phone'):
  s['initial']=group([partner(name,city)])
  s['steps']=[step(f'je veux modifier le téléphone de {code}, mais je ne connais pas encore le nouveau numéro',{'supplier_tasks.control.field':'phone'}),step(f'Non kan9sed F007 machi {code}, touche pas à l’autre',{'supplier_tasks.control.code':'F007'}),step('Le nouveau téléphone de F007 est '+newphone+', prépare mais ne valide pas',{md+'code':'F007',md+'changes.phone':newphone}),step('Pour F007 annule la modification du téléphone, je veux seulement consulter sa fiche',{md+'operation.status':'cancelled','supplier_tasks.control.kind':'search'})]
 elif family in ('supplier_city','supplier_address'):
  supplier_seed();field='city' if family=='supplier_city' else 'address';cue='ville' if field=='city' else 'adresse';value='Agadir' if field=='city' else f'Lot {i}, zone artisanale'
  s['steps']=[step(f'modifie la {cue} du fournisseur {code} en {value}',{md+'changes.'+field:value,md+'resource':'supplier'}),step('bonjour',{md+'changes.'+field:value}),step('annule la modification',{md+'operation.status':'cancelled'})]
 elif family=='ambiguous_supplier':
  s['initial']=group([partner(name,city),partner('AUTRE '+name,'Rabat')]);s['steps']=[step('corrige son nom : ENTREPRISE CORRIGEE',{'partners.0.nom':name,'partners.1.nom':'AUTRE '+name},contains=['fournisseur']),step('pour le premier le bon numéro c’est '+phone,{'partners.0.telephone':phone}),step('résume les demandes',length={'partners':2})]
 elif family in ('article_designation','article_tax','article_accounting','general_account','article_disable','article_used_disable','article_activate','article_site_add','article_site_remove','article_site_activate'):
  article_seed();text='';field=None;value=None
  if family=='article_designation':text=f'Change le nom de l’article {art} en FOURNITURE {i}';field='designation';value=f'FOURNITURE {i}'
  elif family=='article_tax':text=f'Change la TVA de {art} à 10 %';field='tax_rate';value='10'
  elif family=='article_accounting':text=f'Change le code comptable de {art} en STD';field='accounting';value='STD'
  elif family=='general_account':text=f'Modifie le compte général de l’article {art} en 61253000';field='general_account';value='61253000'
  elif family in ('article_disable','article_used_disable'):text=f'Désactive l’article {art}';field='deactivate';value=True
  elif family=='article_activate':text=f'Réactive l’article {art}, sans l’enregistrer';s['unsupported']=True
  elif family=='article_site_add':text=f'Pour l’article {art}, ajoute le site 202';field='add_sites';value=['202']
  elif family=='article_site_remove':text=f'Pour l’article {art}, retire le site 201';field='remove_sites';value=['201']
  else:text=f'Active le site 201 de l’article {art}, sans enregistrer';s['unsupported']=True
  if family=='article_used_disable':s['fault']='used'
  e={md+'resource':'article'}
  if field:e[md+'changes.'+field]=value
  s['steps']=[step(text,e),step('bonjour',e),step('annule la modification',{md+'operation.status':'cancelled'})]
  if family in ('general_account','article_used_disable','article_site_remove'):s['steps'][0]['eq'][md+'operation.status']='blocked'
  if s.get('unsupported'):s['steps'][0]['contains']=['non prise en charge']
 elif family in ('article_creation','article_markdown','article_multiturn'):
  mark='**' if family=='article_markdown' else ''
  opening=f'Bonjour je veux créer un article {mark}{art}{mark}, désignation {mark}FOURNITURE BUREAU {i}{mark}, catégorie {mark}AVNS{mark}, non géré en stock, acheté et vendu, unité UN, site 202, sans fournisseur.'
  e={'articles.0.code_article':art,'articles.0.designation':f'FOURNITURE BUREAU {i}','articles.0.categorie':'AVNS','articles.0.unite':'UN','articles.0.site':'202','articles.0.flag_fournisseur':'1'}
  s['steps']=[step(opening,e),step('J’ai déjà donné le code AVNS',e),step('Supprime les étoiles dans les valeurs',e)]
  if family=='article_multiturn':s['steps']+=[step('site 201',{**e,'articles.0.site':'201'})]
 elif family=='mixed_summary':
  s['initial']=group([partner(name,city),partner('AUTRE '+name,'Rabat')]);s['steps']=[step(f'cherche le fournisseur {code}',{'supplier_tasks.control.code':code}),step(f'je veux désactiver {code}, vérifie les factures',contains=['non prise en charge']),step('reviens aux fournisseurs et résume mes demandes',contains=[name,code])]
 elif family=='api_failure':
  s['fault']=['401','402','429','500','503','timeout','empty','truncated'][i%8]
  s['steps']=[step('Salam, explique ton rôle simplement',contains=['secours']),step('Merci, explique la confirmation',recover=True,contains=['confirmation']),step('cv',contains=['Ça va'])]
 elif family=='json_failure':
  s['fault']='json';s['steps']=[step(f"je veux créer un fournisseur il s'appelle {name}, c'est une SARL AU à {city}, mais je connais pas encore son ICE",p),step('la ville aussi c’est Agadir',{'partners.0.ville':'Agadir'}),step('ne crée rien pour le moment, conserve seulement le brouillon',recover=True)]
 else:raise ValueError(family)
 return s

def corpus():return [build(f,i) for i in range(25) for f in FAMILIES]
if __name__=='__main__':
 rows=corpus();out=Path(__file__).with_name('campaign-1000-corpus.jsonl');out.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8');print(json.dumps({'scenarios':len(rows),'families':len(FAMILIES),'turns':sum(len(r['steps']) for r in rows),'path':str(out)}))
