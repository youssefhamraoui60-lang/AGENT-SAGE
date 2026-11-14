import json
from types import SimpleNamespace
import prepare


def test_unique_exact_name_can_belong_to_another_default_salesman(monkeypatch):
    calls=[]
    row={'BPCNUM_0':'C09716','BPCNAM_0':'BAKHROUCHI EL MEKKI','REP_0':'REP032'}
    def run(*args,**kwargs):
        request=json.loads(kwargs['input']);calls.append(request)
        return SimpleNamespace(stdout=json.dumps({'ok':True,'rows':[] if request.get('representative') else [row]}))
    monkeypatch.setattr(prepare.subprocess,'run',run)
    assert prepare.lookup('client','Bakhrouchi El Mekki',representative='REP001')==[row]
    assert [x.get('representative') for x in calls]==['REP001',None]


def test_partial_name_from_another_salesman_is_not_silently_accepted(monkeypatch):
    row={'BPCNUM_0':'C09716','BPCNAM_0':'BAKHROUCHI EL MEKKI','REP_0':'REP032'}
    def run(*args,**kwargs):
        request=json.loads(kwargs['input'])
        return SimpleNamespace(stdout=json.dumps({'ok':True,'rows':[] if request.get('representative') else [row]}))
    monkeypatch.setattr(prepare.subprocess,'run',run)
    assert prepare.lookup('client','Bakhrouchi',representative='REP001')==[]
