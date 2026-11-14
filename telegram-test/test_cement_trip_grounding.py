import asyncio,json
import pytest
from understanding import shorthand,normalize_quantity
from cement_trips import apply
from prepare import canonical_article

@pytest.mark.parametrize('abbr',['VYS','VGS','voyage','voy','vge'])
@pytest.mark.parametrize('count',[1,2])
@pytest.mark.parametrize('grade',['35','45'])
def test_trip_spelling_grounding_blocks_guessed_sack_count(abbr,count,grade):
    text=f'{count} {abbr} de CPJ{grade}'
    draft={'lines':[{'article':'CPJ'+grade,'quantity':count*560,'unit':'SAC','price':80}]}
    apply(draft,text,canonical_article)
    line=draft['lines'][0];normalize_quantity(line,{'ITMREF_0':'CPJ'+grade,'SAU_0':'SAC'})
    assert line['quantity']==count and line['unit']=='voyage'
    assert line['requires_pack_confirmation']

@pytest.mark.parametrize('text',['2VYScpj35','2vgs CPJ35','2 voy cpj35','2 voiage ciment35'])
def test_missing_spaces_and_common_trip_typos_do_not_invent_loading(text):
    d={'lines':[]};apply(d,text,canonical_article)
    assert d['lines'][0]['quantity']==2 and d['lines'][0]['unit']=='voyage'

@pytest.mark.parametrize('count,factor',[(1,560),(2,560),(2,540)])
def test_explicit_load_in_source_is_converted(count,factor):
    draft={'lines':[]}
    apply(draft,f'{count} VYS CPJ35\n{factor} sacs par voyage',canonical_article)
    line=draft['lines'][0];normalize_quantity(line,{'ITMREF_0':'CPJ35','SAU_0':'SAC'})
    assert line['quantity']==count*factor and line['unit']=='SAC'
    assert not line['requires_pack_confirmation']

def test_conflicting_load_is_not_confirmed():
    draft={'lines':[]};apply(draft,'2 voy CPJ45\n560 sacs par voyage\ntotal 1080 sacs',canonical_article)
    assert 'confirmed_sacks_per_trip' not in draft['lines'][0]

def test_explicit_total_confirms_trip_without_multiplying_it_twice():
    draft={'lines':[]};apply(draft,'2 VGS CPJ45 soit 1120 sacs',canonical_article)
    line=draft['lines'][0];normalize_quantity(line,{'ITMREF_0':'CPJ45','SAU_0':'SAC'})
    assert line['quantity']==1120

def test_mixed_grades_cannot_share_an_unscoped_confirmation():
    draft={'lines':[]};apply(draft,'1 voy CPJ35\n1 voy CPJ45\n560 sacs par voyage',canonical_article)
    assert all('confirmed_sacks_per_trip' not in l for l in draft['lines'])

def test_duplicate_trip_mentions_cannot_bypass_load_confirmation():
    d={'lines':[{'article':'CPJ35','quantity':1120,'unit':'SAC','price':80}]}
    apply(d,'1 voyage CPJ35\n1 voyage CPJ35',canonical_article)
    normalize_quantity(d['lines'][0],{'ITMREF_0':'CPJ35','SAU_0':'SAC'})
    assert d['lines'][0]['requires_pack_confirmation']

def test_full_preparation_never_exposes_a_trip_as_one_sack(monkeypatch):
    import prepare as module
    import learning_memory
    from app.services import ai_provider
    from app.core.config import settings
    async def complete(*args,**kwargs):return {'message':{'content':json.dumps({'intent':'order','client':'C10246','lines':[{'article':'CPJ45','quantity':560,'unit':'SAC','price':80}]})}}
    def lookup(kind,code,*args,**kwargs):
        if kind=='client':return [{'BPCNUM_0':'C10246','BPCNAM_0':'Client','CUR_0':'MAD','REP_0':'REP012','VACBPR_0':'MAR'}]
        if kind=='article':return [{'ITMREF_0':'CPJ45','ITMDES1_0':'Ciment CPJ45','SAU_0':'SAC','VACITM_0':'T20','SITE_OK':1}]
        return []
    monkeypatch.setattr(settings,'ai_provider','deepseek');monkeypatch.setattr(ai_provider,'complete',complete)
    monkeypatch.setattr(module,'lookup',lookup);monkeypatch.setattr(learning_memory,'approved_rules',lambda:[])
    d=asyncio.run(module.prepare([{'role':'user','content':'C10246\n1 VYS CPJ45'}],details=True))
    assert d['lines'][0]['quantity'] is None
    assert 'tonnage du voyage CPJ45' in d['missing_fields']
    assert 'nombre de sacs à confirmer' in d['reply']
