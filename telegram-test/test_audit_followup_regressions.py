from copy import deepcopy

from prepare import apply_grouping_note


def test_grouping_with_wood_preserves_note_without_inventing_goods():
    draft = {'delivery_note': None, 'lines': [
        {'article': 'RAB8', 'quantity': 100},
        {'article': 'RAB10', 'quantity': 400},
        {'article': 'bois', 'quantity': None}]}
    apply_grouping_note(draft, 'Nohabuild 100 kgs d8\n400 kgs d10\n9.80 à grouper avec le bois')
    assert [line['article'] for line in draft['lines']] == ['RAB8', 'RAB10']
    assert 'grouper avec le bois' in draft['delivery_note']
    before = deepcopy(draft)
    apply_grouping_note(draft, 'à grouper avec le bois')
    assert draft == before


def test_grouping_note_does_not_remove_an_explicit_wood_request():
    draft = {'delivery_note': None, 'lines': [{'article': 'bois', 'quantity': 50}]}
    apply_grouping_note(draft, '50 bois\nÀ grouper avec le bois')
    assert draft['lines'] == [{'article': 'bois', 'quantity': 50}]
