"""Fail-closed article checks using a reviewed, hashed TEST reference snapshot.

The snapshot is evidence, not an invented Sage dictionary. Sage remains the final
validator. Expiry and publication binding prevent silently reusing old rules.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.sage_soap import SageError


def load_rules(description_hash,resource='articles'):
    try:
        if resource not in ('articles','article-sites'):raise ValueError()
        policy = json.loads(Path(settings.sage_security_policy_file).read_text(encoding='utf-8'))
        evidence = policy['permissions'][resource]['create']['business_rules_evidence']
        raw = Path(evidence['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != evidence['sha256']:
            raise ValueError()
        rules = json.loads(raw)
        expiry = datetime.fromisoformat(rules['expires_at'])
        if (expiry.tzinfo is None or expiry <= datetime.now(timezone.utc)
                or rules['folder'] != 'TEST' or rules['solution'] != 'V12'
                or rules['description_sha256'] != description_hash
                or rules['reviewed'] is not True):
            raise ValueError()
        return rules
    except (OSError, ValueError, KeyError, TypeError):
        raise SageError('article_reference_rules_unavailable', 422) from None


def validate_article(request, description, rules, read_supplier):
    """Validate each supplied field path; never create a supplier or site implicitly."""
    fields = {f.group + (f'[{f.row}]' if f.row else '') + '.' + f.name: f.value
              for f in request.fields}
    try:
        required = set(rules['required_fields']) | {
            'ITM0_1.TCLCOD', 'ITM0_1.ITMSTA', 'ITM0_1.DES1AXX',
            'ITM3_1.STU', 'ITM3_1.PUU', 'ITM3_1.SAU'}
        for group in description.findall('./ADXDATA/GRP'):
            for field in group.findall('FLD'):
                if field.get('OBL') == '1' and field.get('NAM') != 'ITMREF':
                    required.add(group.get('NAM') + '.' + field.get('NAM'))
        if any(not fields.get(name) for name in required):
            raise SageError('article_required_fields_missing', 422)
        category = rules['categories'][fields['ITM0_1.TCLCOD']]
        if category['active'] is not True or category['manual_keys'] is not True:
            raise SageError('article_category_not_creatable', 422)
        if fields['ITM0_1.ITMSTA'] not in category['statuses']:
            raise SageError('article_status_not_allowed', 422)
        if fields.get('ITM2_1.STOMGTCOD') and fields['ITM2_1.STOMGTCOD'] not in category.get('stock_management',[]):
            raise SageError('article_stock_management_not_allowed',422)
        for name in ('STU', 'PUU', 'SAU'):
            value = fields['ITM3_1.' + name]
            if value not in rules['active_units'] or value not in category['units'][name]:
                raise SageError('article_unit_not_allowed', 422)
        # Exact reviewed combinations include conversion coefficients when necessary.
        if not any(all(fields.get(k) == v for k, v in combo.items())
                   and all('ITM3_1.' + n in combo for n in ('STU', 'PUU', 'SAU'))
                   for combo in category['unit_combinations']):
            raise SageError('article_unit_conversion_not_verified', 422)
        tax = category['tax_fields']
        if tax:
            if not any(set(combo) == set(tax) and all(fields.get(k) == v for k, v in combo.items())
                       for combo in category['tax_combinations']):
                raise SageError('article_tax_configuration_invalid', 422)
        elif category.get('tax_default_verified') is not True:
            raise SageError('article_tax_defaults_unverified', 422)
        allowed = set(category['allowed_fields'])
        if not set(fields) <= allowed or not set(required) <= allowed:
            raise SageError('article_field_not_business_reviewed', 422)
        # Site creation is a separate approved WS_AR_SITE operation, after the article.
        if category['requires_article_site'] is True:
            raise SageError('article_site_separate_approval_required', 422)
        suppliers = category['supplier_fields']
        if category['supplier_required'] and not any(fields.get(k) for k in suppliers):
            raise SageError('article_supplier_required', 422)
        for name in suppliers:
            value = fields.get(name)
            if value and (not isinstance(value, str) or not read_supplier(value).get('exists')):
                raise SageError('article_supplier_not_found', 422)
    except (KeyError, TypeError, AttributeError):
        raise SageError('article_reference_rules_incomplete', 422) from None
    return {'validated': True, 'source': 'reviewed_TEST_reference_snapshot',
            'category': fields['ITM0_1.TCLCOD'], 'tax_validated': True,
            'units_validated': True, 'associations_validated': True}


def check(request, description, description_hash):
    from app.services.sage_gateway import Gateway
    rules = load_rules(description_hash)
    result = validate_article(request, description, rules,
                              lambda code: Gateway('suppliers').read({'BPSNUM': code}))
    result['rules_sha256'] = hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()
    return result
