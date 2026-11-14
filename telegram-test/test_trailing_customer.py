import prepare
import learning_memory


def test_verified_customer_after_goods_overrides_old_phone_note(monkeypatch):
    monkeypatch.setattr(prepare,'lookup',lambda kind,name:[{'BPCNUM_0':'C07792','BPCNAM_0':'LAGHI MRABAT MOHAMED'}])
    text='Contact : Rachida\nFaris Ameur\n+212675072778\nContact : Rachida\n1500 kg fer 12\nContact : Rachida\nLaghi mrabat mohamed\nContact : Rachida\n9.80'
    assert prepare.trailing_customer_complement(text)=='C07792'
    assert prepare.trailing_customer_complement(text.replace('Laghi mrabat mohamed','Client inconnu')) is None
    assert prepare.trailing_customer_complement(text.replace('Contact : Rachida\nLaghi','Contact : Wiam\nLaghi')) is None
    assert prepare.trailing_customer_complement('Contact : Rachida\nFaris Ameur\n+212675072778') is None
