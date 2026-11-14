import prepare
import learning_memory


def test_inline_sacs_grade_preserves_goods_and_resolves_novacim(monkeypatch):
    rules={'cement_supplier_phrases':{'novacim':'F889'}}
    monkeypatch.setattr(learning_memory,'policy',lambda key,default=None:rules.get(key,default))
    text='Haj Nacer fouko 540 sacs 45 novacim'
    assert prepare.article_supplier(text,'CPJ45')=='F889'
    annotated=prepare.annotate_supplier_context(text)
    assert annotated.splitlines()[0]==text
    assert 'Fournisseur du ciment' in annotated
    assert prepare.article_supplier('540 sacs 45 sans novacim','CPJ45') is None
    assert prepare.article_supplier('Client Novacim 540 briques','CPJ45') is None


def test_two_different_cement_suppliers_are_scoped_to_each_line(monkeypatch):
    rules={'cement_supplier_phrases':{'holcim':'F008','cimat':'F007'}}
    monkeypatch.setattr(learning_memory,'policy',lambda key,default=None:rules.get(key,default))
    source='210 perfecto Holcim\n120 ciment 45 cimat'
    assert prepare.article_supplier(source,'CPJ35P')=='F008'
    assert prepare.article_supplier(source,'CPJ45')=='F007'
