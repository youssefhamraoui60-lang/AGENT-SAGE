from delivery_notes import compact

def test_short_notes_are_unchanged():
    assert compact('AIN CHOCK BOULEVARD SIDI MASSOUD CASA')=='AIN CHOCK BOULEVARD SIDI MASSOUD CASA'

def test_long_address_preserves_place_names_and_both_phone_contacts():
    source="Livraison à : préfecture d'arrondissements sidi Bernoussi, arrondissement sidi Moumen, quartier Ahl Lghalm, Casablanca. Contacts sur place : Mr ACHRAF 06 61 58 34 12 ; Mr NABIL MIARA 06 61 10 24 48."
    result=compact(source)
    for name in ['Bernoussi','Moumen','Ahl Lghalm','ACHRAF','NABIL MIARA','0661583412','0661102448']:assert name in result
    assert len(result)<=100
    variant=source.replace('Livraison à :','Livraison :').replace('Contacts sur place :','Contacts :')
    assert len(compact(variant))<=100

def test_compaction_never_silently_truncates_unknown_content():
    source='LOT XYZ BLOC 1 ETAGE 3 '+('INSTRUCTION SPECIALE '*10)
    result=compact(source)
    assert len(result)>100
    assert result.endswith('INSTRUCTION SPECIALE')

def test_courtesy_is_compacted_without_removing_supplier_or_contacts():
    source='AIN CHOCK BOULEVARD SIDI MASSOUD CASA. Rachid : 06 62 33 14 35 / Khalid : 06 67 33 35 15. Merci de nous livrer fer sonasid'
    result=compact(source)
    assert len(result)<=100
    for value in ['Rachid','Khalid','0662331435','0667333515','fer sonasid']:assert value in result
