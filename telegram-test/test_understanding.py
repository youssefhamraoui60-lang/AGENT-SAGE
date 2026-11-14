import pytest
from understanding import choose_reference,normalize_quantity,shorthand,customer_phrases
from prepare import canonical_article


def test_voyage_cement_shorthand_preserves_explicit_trip_count():
    assert shorthand('Travemac voyage cima 45 Lafarge casa')=='Travemac 1 voyage CPJ45 Lafarge casa'
    assert shorthand('2 voyages cima45 Lafarge')=='2 voyage CPJ45 Lafarge'


def test_global_vgs_equivalence_cannot_guess_current_loading():
    import learning_memory
    token=learning_memory.ACTIVE.set(({'kind':'policy','rule_key':'verified_unit_equivalences',
                                      'payload':{'value':[{'article':'CPJ45','from':'vgs','to':'SAC','factor':560}]}},))
    try:
        line={'article':'CPJ45','quantity':None,'unit':'vgs'}
        normalize_quantity(line,{'ITMREF_0':'CPJ45','SAU_0':'SAC'})
        assert line['unit']=='vgs'
        assert line['requires_pack_confirmation']
    finally:learning_memory.ACTIVE.reset(token)


def test_homonym_requires_matching_commercial():
    rows=[{'BPCNUM_0':'A','BPCNAM_0':'FETAHI ABDELHAK','REP_0':'REP019'},
          {'BPCNUM_0':'B','BPCNAM_0':'FETAHI ABDELHAK','REP_0':'REP032'}]
    assert len(choose_reference('client','Fetahi Abdelhak',rows))==2
    assert choose_reference('client','Fetahi Abdelhak',rows,{'REPNUM_0':'REP032'})[0]['BPCNUM_0']=='B'


def test_names_in_different_order():
    rows=[{'BPCNUM_0':'A','BPCNAM_0':'AIT LARBI KHALID','REP_0':'REP020'}]
    assert choose_reference('client','Khalid ait larbi',rows)==rows


@pytest.mark.parametrize('code,unit,quantity,expected',[
    ('CPJ35','tonnes',15,300),('CPJ45','palette',9,270),
    ('RAB12','fardou',2,4000),('RAB10','barre',2,15.38),('RABT6','tonne',4,4000),
    ('BQ7','palette',1,335),
])
def test_ob_verified_units(code,unit,quantity,expected):
    sales='SAC' if code.startswith('CPJ') else 'UN' if code=='BQ7' else 'KG'
    line={'quantity':quantity,'unit':unit}
    normalize_quantity(line,{'ITMREF_0':code,'SAU_0':sales})
    assert line['quantity']==expected
    assert line['unit']==sales


def test_unknown_package_never_guesses():
    line={'quantity':2,'unit':'palette'}
    normalize_quantity(line,{'ITMREF_0':'UNKNOWN','SAU_0':'UN'})
    assert line['unit']=='palette'


def test_cement_aliases_and_shorthand():
    assert shorthand('18t45\n09t35')=='18 tonnes CPJ45\n09 tonnes CPJ35'
    assert canonical_article('ciment 45 Lafarge')=='CPJ45'
    assert canonical_article('sima 35')=='CPJ35'
    assert canonical_article('rab 6 Sounacid')=='RABT6'
    assert canonical_article('perfecto')=='CPJ35P'
    assert canonical_article('fardou rab 12')=='RAB12'
    assert canonical_article('rab 12 t Sounassid')=='RAB12'


def test_client_after_quantity_is_only_a_catalog_search_candidate():
    assert 'Dior guisser' in customer_phrases('Contact : Aicha Khayr\n60 sacs ciment 45 Dior guisser')


def test_thirty_cubic_metre_sand_load_uses_catalog_sales_unit():
    line={'quantity':1,'unit':'voyage'}
    normalize_quantity(line,{'ITMREF_0':'SABL_30M3','SAU_0':'30M'})
    assert line == {'quantity':1,'unit':'30M'}


def test_packaging_equivalence_is_scoped_to_verified_article():
    import learning_memory as memory
    token=memory.ACTIVE.set(({'kind':'policy','rule_key':'verified_unit_equivalences','payload':{'value':[{'article':'SIK_2L','from':'bidon','to':'UN','factor':1}]}},))
    try:
        line={'quantity':5,'unit':'BIDON'}
        normalize_quantity(line,{'ITMREF_0':'SIK_2L','SAU_0':'UN'})
        assert line['quantity']==5 and line['unit']=='UN'
        other={'quantity':5,'unit':'BIDON'}
        normalize_quantity(other,{'ITMREF_0':'OTHER','SAU_0':'UN'})
        assert other['unit']=='BIDON'
    finally:memory.ACTIVE.reset(token)


@pytest.mark.parametrize('phrase,code',[('fer à béton 12','RAB12'),('T6','RABT6'),('fardou 14','RAB14'),('fer diam 20','RAB20'),('FER 06 FE 500','RABT6'),('FER A BETON HA12','RAB12'),('Acier à béton T12','RAB12')])
def test_steel_description_resolution_keeps_diameter(phrase,code):
    assert canonical_article(phrase)==code
