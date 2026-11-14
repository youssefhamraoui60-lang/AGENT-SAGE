"""Sage article/site partial outcomes with mocked workers and isolated local PG."""
import pytest
from test_sage_article_sites import workflow,capture
from app.services import sage_article_sites as sites
from app.services.sage_crud import CrudError


def advance(workflow):
    owner,session,parent,calls=workflow
    session=capture(workflow,'Créer les fiches article-site 201 et 202')
    session=sites.action(owner,session['id'],parent['id'],'site-prepare',session['revision'],False)
    session=sites.action(owner,session['id'],parent['id'],'site-approve',session['revision'],True)
    return owner,session,parent,calls


def test_created_parent_site_timeout_stops_and_forbids_reemission(workflow,monkeypatch):
    owner,session,parent,calls=advance(workflow)
    attempts=[]
    def worker(code,site,mode,**extra):
        attempts.append((code,site,mode));raise TimeoutError('synthetic communication failure')
    monkeypatch.setattr(sites,'worker',worker)
    result=sites.action(owner,session['id'],parent['id'],'site-execute',session['revision'],True)
    a=result['state']['articles'][0]
    assert a['outcome']['confirmed'] and a['site_request']['status']=='ambiguous'
    assert len(attempts)==1 and a['site_request']['results']['202']['SaveAttempts']==0
    with pytest.raises(CrudError):sites.action(owner,session['id'],parent['id'],'site-execute',result['revision'],True)
    assert len(attempts)==1


def test_changed_site_selection_requires_new_approval(workflow):
    owner,session,parent,calls=advance(workflow)
    old=session['state']['articles'][0]['site_request']['id']
    changed=sites.capture(owner,session['id'],'Créer les fiches article-site 209',session['revision'])
    assert changed['state']['articles'][0]['site_request']['id']!=old
    with pytest.raises(CrudError):sites.action(owner,session['id'],parent['id'],'site-execute',changed['revision'],True)
    assert not any(mode=='execute' for code,site,mode in calls)
