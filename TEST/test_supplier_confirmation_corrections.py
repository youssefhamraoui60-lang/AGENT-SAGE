"""Pasted conversation regression; all SQL transports are simulated."""
import sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from test_chat_supplier_sql import workflow
from app.services import supplier_dialogue as dialogue,supplier_followups,supplier_sql

def initial():
    return dialogue.handle("bonjour je veux crrer un nevelle fourniseur, il s'appelle ATLAS BUREAU TEST, c'est une SARL AU à Rabat, mais j'ai pas encore son ICE ni son téléphone. Prépare sa fiche avec les informations que je t'ai données.",{'articles':[],'partners':[]})['state']

def test_initial_legal_form_city_and_name_are_independent():
    p=initial()['partners'][0]
    assert p['nom']=='ATLAS BUREAU TEST' and p['ville']=='Rabat' and p['forme_juridique']=='SARL AU'
    assert not p.get('ice')

def test_days_then_mode_and_no_invalid_payment_overwrite():
    s=initial()
    for message in ['60 jour','la codition de payment est 60 jour']:
        result=dialogue.handle(message,s);s=result['state']
        assert 'chèque' in result['reply'] and not s['partners'][0].get('conditions_paiement')
    s=dialogue.handle('60 jour chéque',s)['state']
    assert s['partners'][0]['conditions_paiement']=='cheque 60 jours'
    assert not s['_supplier_dialogue'].get('expected_field')
    result=dialogue.handle('Paiement fix',s)
    assert result['state']['partners'][0]['conditions_paiement']=='cheque 60 jours'
    assert 'ne précise pas' in result['reply']

def test_darija_new_supplier_does_not_inherit_previous_private_fields():
    s=initial();s['partners'][0].update(ice='098765432112345',adresse='123 HAY RAHA')
    result=dialogue.handle('بغيت نزيد مورد جديد سميتو النور تيست فالرباط وما عنديش دابا رقم ICE',s)
    p=result['state']['partners'][0]
    assert p['nom']=='النور تيست' and p['ville']=='Rabat'
    assert not p.get('ice') and not p.get('adresse') and not p.get('forme_juridique')

def test_phone_correction_does_not_invent_digits_or_silently_rename_city():
    s=initial();p=s['partners'][0];p.update(telephone='0987367238',ville='BERRCHIDE')
    assert supplier_followups.phone_warning(p)
    result=dialogue.handle('mais ne pas un télefon de maroc valider ou un téle de fix valder pour la ville il des aurtografe pas bin dois le coriger',s)
    assert 'Berrechid' in result['reply'] and 'Quel numéro' in result['reply']
    assert result['state']['partners'][0]['telephone']=='0987367238'
    assert result['state']['partners'][0]['ville']=='BERRCHIDE'

def test_scope_acknowledgment_required_before_sql_approval(workflow):
    s,calls,call=workflow;p=s['partners'][0];p['forme_juridique']='SARL AU'
    r=call('prepare');assert r.status_code==200,r.text
    op=s['partners'][0]['operation'];assert op['status']=='prepared' and op['draft_only_fields'][0]['value']=='SARL AU'
    assert 'forme_juridique' not in op['parameters']
    assert call('approve',True).status_code==423 and calls==[False]
    assert call('approve',True,confirm_draft_only_fields=True).status_code==200
    assert calls==[False]  # Approving is not a SQL INSERT.
    p=s['partners'][0];p['forme_juridique']='SA'
    assert call('execute',True).status_code==403 and calls==[False]

def test_invalid_phone_blocks_even_direct_prepare_endpoint(workflow):
    s,calls,call=workflow;s['partners'][0]['telephone']='0987367238'
    assert call('prepare').status_code==423 and not calls
