from contextvars import ContextVar
RESERVATION=ContextVar('chat_storage_reservation',default=None)
