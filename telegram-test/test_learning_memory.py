from contextlib import contextmanager
from uuid import uuid4
import learning_memory as memory
from prepare import canonical_article

def test_arabic_aliases_are_not_empty_or_numeric_alias_collisions():
    assert memory.key('كولة تراديسيم')=='كولةتراديسيم'
    assert memory.key('حديد 14')!=memory.key('14')
    assert memory.key('diamètre 6')==memory.key('diametre 6')

def test_other_customer_source_draft_cannot_leak_into_prompt():
    token=memory.ACTIVE.set(({'kind':'interpretation','rule_key':'source_draft_other',
                             'payload':{'source_body_key':'unrelated-hash','client':'C99999','lines':[]}},
                            {'kind':'interpretation','rule_key':'audit_source_article_5204',
                             'payload':{'source_message':5204,'expected_article':'RAB10'}}))
    try:assert memory.prompt_context('Different customer, different order')=='[]'
    finally:memory.ACTIVE.reset(token)

def test_customer_aliases_are_only_prompted_when_present_in_source():
    token=memory.ACTIVE.set(({'kind':'client_alias','rule_key':'mobilifer','payload':{'code':'C09871'}},))
    try:
        assert memory.prompt_context('Another customer')=='[]'
        assert 'C09871' in memory.prompt_context('Société Mobilifer')
    finally:memory.ACTIVE.reset(token)


def test_approved_memory_overrides_alias_without_editing_code():
    token=memory.ACTIVE.set(({'kind':'article_alias','rule_key':'pointe6','payload':{'code':'MEMORY_TEST_CODE'},'revision':2},))
    try:
        assert canonical_article('pointe 6')=='MEMORY_TEST_CODE'
        assert canonical_article('Pointes de Paris 06')=='MEMORY_TEST_CODE'
    finally:
        memory.ACTIVE.reset(token)
    assert canonical_article('pointe 6')=='PF-TP16X20'


def test_explicit_corrections_not_normal_orders():
    assert memory.parse_correction('corriger article pointe 6 = PF-TP16X20')==('pointe 6','PF-TP16X20')
    assert memory.parse_correction('remplacer TRS par MANTD')==('TRS','MANTD')
    assert memory.parse_correction("non, l’article pointe 8 c’est PF-TP08X20")==('pointe 8','PF-TP08X20')
    assert memory.parse_correction('Client C10370 : 80 sacs CPJ45') is None


def test_postgres_revision_and_pending_are_durable_transactionally(monkeypatch):
    # Real PostgreSQL, isolated by a unique alias and rollback: no test lesson survives.
    original=memory.db.connection
    with original() as conn:
        @contextmanager
        def same_transaction():
            yield conn
        monkeypatch.setattr(memory.db,'connection',same_transaction)
        alias='test'+uuid4().hex
        try:
            memory.save('article_alias',alias,{'code':'PP06'},actor='test',source='transactional-test',approved=True)
            memory.save('article_alias',alias,{'code':'PP08'},actor='test',source='explicit-correction',approved=True)
            row=next(r for r in memory.approved_rules() if r['rule_key']==alias)
            assert row['payload']['code']=='PP08' and row['revision']==2
            memory.save('article_alias',alias,{'code':'PP06'},actor='test',source='seed',approved=True,replace=False)
            row=next(r for r in memory.approved_rules() if r['rule_key']==alias)
            assert row['payload']['code']=='PP08' and row['revision']==2
            memory.save('interpretation',alias,{'text':'Not approved'},actor='test',source='proposal',approved=False)
            assert not any(r['kind']=='interpretation' and r['rule_key']==alias for r in memory.approved_rules())
        finally:
            conn.rollback()
