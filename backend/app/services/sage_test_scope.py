"""Optional, fixed temporary exception; never enables writes or replaces approval."""
from datetime import datetime, timedelta, timezone


def temporary_admin_scope(policy, user):
    if policy.get('temporary_admin_test') is not True:
        return False
    try:
        expiry = datetime.fromisoformat(policy['expires_at'])
        now = datetime.now(timezone.utc)
        return (user == 'admin' and expiry.tzinfo is not None
                and now < expiry <= now + timedelta(hours=24)
                and policy['solution'] == 'V12' and policy['folder'] == 'TEST'
                and policy['pool'] == 'POOL_AI_TEST'
                and policy['base_url'] == 'https://sage:8443'
                and policy['scope'] == {'resource':'articles','action':'create',
                                        'keys':{'ITMREF':'TESTAGENT004'}}
                and set(policy['permissions']) == {'articles'}
                and set(policy['permissions']['articles']) == {'create'})
    except (KeyError, TypeError, ValueError):
        return False


def scope_matches(policy, resource, action, keys=None):
    scope = policy['scope']
    return (resource == scope['resource'] and action == scope['action']
            and (keys is None or keys == scope['keys']))
