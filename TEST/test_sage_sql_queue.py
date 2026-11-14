import concurrent.futures,threading,time
import pytest
from app.services.sage_sql_queue import plan_slot,SagePlanBusy,SLOTS
from app.services import article_sql,erp_modification

def test_plans_are_serialized_and_slot_is_released_after_exception():
    state={'active':0,'max':0};guard=threading.Lock()
    def work(i):
        with plan_slot('TEST',timeout=2):
            with guard:state['active']+=1;state['max']=max(state['max'],state['active'])
            time.sleep(.01)
            with guard:state['active']-=1
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:list(executor.map(work,range(12)))
    assert state['max']==1
    with pytest.raises(RuntimeError):
        with plan_slot('TEST'):raise RuntimeError('test')
    with plan_slot('TEST',timeout=.01):pass

def test_folders_are_independent_and_queue_is_bounded():
    with plan_slot('TEST'):
        with plan_slot('OB',timeout=.01):pass
        with pytest.raises(SagePlanBusy):
            with plan_slot('TEST',timeout=.01):pass

@pytest.mark.parametrize('module',[article_sql,erp_modification])
def test_queue_rejection_proves_no_sql_was_sent(monkeypatch,module):
    import app.services.sage_sql_queue as queue
    from contextlib import contextmanager
    @contextmanager
    def busy(*args,**kwargs):
        raise SagePlanBusy()
        yield
    monkeypatch.setattr(queue,'plan_slot',busy)
    monkeypatch.setattr(module,'_transport',lambda *args,**kwargs:pytest.fail('SQL must not run'))
    result=module.transport('plan',execute=True)
    assert result['executed'] is False and result['transaction_state']=='NOT_STARTED'
    assert result['confirmed_not_executed'] and not result['retry_allowed']
