"""Bounded per-folder admission; SQL transaction locks remain authoritative."""
from contextlib import contextmanager
import threading

SLOTS={'TEST':threading.Lock(),'OB':threading.Lock()}
class SagePlanBusy(Exception):pass

@contextmanager
def plan_slot(folder,timeout=30):
    if folder not in SLOTS:raise ValueError('Invalid Sage folder')
    lock=SLOTS[folder]
    if not lock.acquire(timeout=timeout):raise SagePlanBusy()
    try:yield
    finally:lock.release()

def not_started(folder):
    return {'ok':False,'folder':folder,'executed':False,'transaction_state':'NOT_STARTED','confirmed_not_executed':True,'retry_allowed':False,'code':'sage_write_queue_busy','message':'Une autre opération est en cours dans ce dossier. Aucun ordre SQL de cette demande n’a été envoyé. Patientez, puis préparez et confirmez de nouveau.'}
