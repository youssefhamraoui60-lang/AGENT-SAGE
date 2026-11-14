from copy import deepcopy
from types import SimpleNamespace

import pytest
from lxml import etree

from app.services.sage_article_rules import validate_article, load_rules
from app.services.sage_gateway import Gateway
from app.services.sage_soap import SageError


def sample():
    values = {'ITM0_1.TCLCOD':'NEG', 'ITM0_1.ITMSTA':'1',
              'ITM0_1.DES1AXX':'SYNTHETIC', 'ITM3_1.STU':'UN',
              'ITM3_1.PUU':'UN', 'ITM3_1.SAU':'UN', 'ITM1_5.VACITM':['1','','']}
    request = SimpleNamespace(fields=[SimpleNamespace(group=k.split('.')[0], name=k.split('.')[1],
                                                       row=None, value=v) for k,v in values.items()])
    category = {'active':True,'manual_keys':True,'statuses':['1'],
                'units':{n:['UN'] for n in ('STU','PUU','SAU')},
                'unit_combinations':[{k:v for k,v in values.items() if k.startswith('ITM3_1.')}],
                'tax_fields':['ITM1_5.VACITM'], 'tax_combinations':[{'ITM1_5.VACITM':['1','','']}],
                'allowed_fields':list(values), 'requires_article_site':False,
                'supplier_required':False,'supplier_fields':[]}
    return request, {'required_fields':[], 'categories':{'NEG':category}, 'active_units':['UN']}


def run(request, rules, supplier=lambda code: {'exists':False}):
    return validate_article(request, etree.XML('<ADXDOC><ADXDATA/></ADXDOC>'), rules, supplier)


def test_complete_reviewed_combination_passes():
    request, rules = sample()
    assert run(request, rules)['validated'] is True


@pytest.mark.parametrize('mutation,code', [
    ('missing','article_required_fields_missing'), ('category','article_reference_rules_incomplete'),
    ('unit','article_unit_not_allowed'), ('tax','article_tax_configuration_invalid'),
    ('site','article_site_separate_approval_required'), ('unknown','article_field_not_business_reviewed'),
    ('supplier','article_supplier_not_found'), ('conversion','article_unit_conversion_not_verified')])
def test_invalid_or_unverified_business_values_block(mutation, code):
    request, rules = sample()
    category = rules['categories']['NEG']
    if mutation == 'missing': request.fields.pop(2)
    if mutation == 'category': rules['categories'] = {}
    if mutation == 'unit': rules['active_units'] = []
    if mutation == 'tax': category['tax_combinations'] = []
    if mutation == 'site': category['requires_article_site'] = True
    if mutation == 'unknown': category['allowed_fields'].pop()
    if mutation == 'supplier': category['supplier_fields'] = ['ITM0_1.DES1AXX']
    if mutation == 'conversion': category['unit_combinations'] = []
    with pytest.raises(SageError, match=code): run(request, rules)


def test_supplier_checked_read_only():
    request, rules = sample()
    rules['categories']['NEG']['supplier_fields'] = ['ITM0_1.DES1AXX']
    called=[]
    assert run(request, rules, lambda code: called.append(code) or {'exists':True})['validated']
    assert called == ['SYNTHETIC']


def test_missing_evidence_fails_closed(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'sage_security_policy_file', str(tmp_path/'missing'))
    with pytest.raises(SageError, match='article_reference_rules_unavailable'): load_rules('synthetic')


@pytest.mark.parametrize('method', ['save','modify','delete'])
def test_generic_gateway_cannot_write(method):
    # No network, even if a caller bypasses the HTTP route.
    gateway = object.__new__(Gateway)
    with pytest.raises(SageError, match='operation_forbidden'): gateway.call(method)
