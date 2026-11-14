"""Debounce consecutive messages by group, sender and commercial contact."""
import asyncio
import re
import unicodedata


def contact_name(text):
    match = re.search(r'^\s*contact\s*:\s*([^\r\n]+)', text, re.I | re.M)
    if not match:
        return None
    value = unicodedata.normalize('NFKD', match[1]).encode('ascii', 'ignore').decode()
    return re.sub(r'\W+', '', value).casefold()


def customer_codes(text):
    return frozenset(code.upper() for code in re.findall(r'\bC\d{4,8}\b',text,re.I))


def document_references(text):
    clean=re.sub(r'[|\s]+',' ',text)
    heading=r"(?:BON\s+DE\s+COMMANDE(?:\s+D['’]\s*ACHAT)?\s*(?:N[°ºo•]?\s*[:.]?\s*)?|N[°ºo•]\s*COMMANDE\s*:?|COMMANDE\s+N[°ºo•]\s*[:.]?)"
    token=r"([A-Z]{1,4}[-/]?\d{2,16}(?:[-/][A-Z0-9]{1,16})*|\d{1,12}(?:-\d+)?(?:/\d{1,12})?)"
    refs=re.findall(r'(?i)\b'+heading+r'\s*'+token+r'\b',clean)
    refs+=re.findall(r'(?i)\bBC\b\s*(?:N[°ºo]?\s*[:.]?\s*)?[:.]?\s*'+token+r'\b',clean)
    refs+=re.findall(r'(?i)\bNum[eé]ro\s+(?:de\s+)?Commande\s*[:.]?\s*'+token+r'\b',clean)
    refs+=re.findall(r'(?i)\b(?:Ref|N[°ºo])\s*:\s*(BC[A-Z0-9/-]+)',clean)
    return frozenset(re.sub(r'/20\d{2}$','',ref.upper()) for ref in refs)



def message_mode(text):
    caption=text.split('DOCUMENT JOINT')[0]
    return 'followup' if re.search(r'(?i)relanc|r[eé]clam|(?:[eé]tat|statut).{0,35}(?:commande|livraison)',caption) else 'order'


def has_goods_request(text):
    caption=text.split('DOCUMENT JOINT')[0]
    from understanding import shorthand
    caption=shorthand(caption)
    return bool(re.search(r'(?i)\b\d+(?:[.,]\d+)?\s*(?:t\b|tonnes?\b|kgs?\b|sacs?\b|rab\b|fer\b|cpj\b|voyage\b)',caption))


def separate_complete_requests(previous,current):
    """Two self-contained requests stay separate even for the same customer."""
    if re.search(r'(?im)^\s*(?:plus\b|ajout(?:er)?\b|compl[eé]ment\b|correction\b|modifier\b|\+)',current):
        return False
    return bool(named_customer(previous) and named_customer(current)
                and has_goods_request(previous) and has_goods_request(current))


def separate_document_and_goods(previous,current):
    if bool('DOCUMENT JOINT' in previous)==bool('DOCUMENT JOINT' in current):return False
    plain=current if 'DOCUMENT JOINT' in previous else previous
    # A fee, client name, phone, or explicit supplement can complete a document.
    # A separate goods request is never silently absorbed into its issuer.
    if re.search(r'(?im)^\s*(?:compl[eé]ment|ajouter|correction|modifier)\b',plain):return False
    return has_goods_request(plain) or bool(named_customer(plain))


def named_customer(text):
    """Identify a complete request's customer, including inline/trailing names."""
    body=[s.strip() for s in text.split('DOCUMENT JOINT')[0].splitlines()
          if s.strip() and not re.match(r'(?i)^\s*(?:Contact|Num[eé]ro)\s*:',s)
          and not re.fullmatch(r'[+\d ()-]{6,}',s.strip())]
    if not body:return None
    goods=r'(?i)^\d+(?:[.,]\d+)?\s*(?:tonnes?|kgs?|sacs?|cpj|ciments?|cima|briques?|rlx|fardou|rab|unit[eé]s?|palettes?|t)(?=\W|\d|$)'
    excluded=r'(?i)^(?:trs|trc|transport|livraison|le chauffeur|à côté|correction|corriger|relance|plus|bonjour|r[eè]glement|pay[eé]|lui.m[eê]me|barres?\s+droit(?:e)?s?|hdid|soun|sonasid|cimat|holcim|lafarge|novacim|temara)\b'
    first=body[0]
    inline=re.match(r'^(?P<name>[^\d]+?)\s+\d+(?:[.,]\d+)?\s*(?:kgs?|sacs?|t\b|tonnes?|unit[eé]s?)\b',first,re.I)
    if inline and not re.search(excluded,first):value=inline['name']
    elif re.match(r'^[^\W\d_]',first) and not re.search(excluded,first) and len(body)>1 and (
            any(re.search(goods,x) for x in body[1:]) or
            any(re.match(r'(?i)^(?:solo|remorque|(?:(?:un|une|\d+)\s*)?(?:voyages?|vys|vgs|vge|voy)|v)\b',x) for x in body[1:]) or
            any(re.fullmatch(r'(?i)(?:cimat|holcim|lafarge|novacim|temara)',x) for x in body[1:])):
        value=first
    elif re.search(goods,first):
        names=[x for x in body[1:] if re.fullmatch(r'[^\W\d_]+(?:[ -]+[^\W\d_]+){1,5}',x)
               and not re.search(excluded,x) and not re.search(r'(?i)\b(?:trs|transport|chauffeur|r[eè]glement)\b',x)]
        if len(names)!=1:return None
        value=names[0]
    else:return None
    value=re.sub(r'(?i)\bC\d{4,8}\b','',value)
    value=unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower()
    return re.sub(r'\W+','',value) or None


def client_scoped_history(history, text):
    previous_text=next((m['content'] for m in reversed(history) if m['role']=='user'),'')
    if separate_complete_requests(previous_text,text):return []
    if separate_document_and_goods(previous_text,text):return []
    if message_mode(text)=='followup' or message_mode(previous_text)=='followup':
        return []
    refs=document_references(text);old_refs=document_references(previous_text)
    if 'DOCUMENT JOINT' in text and 'DOCUMENT JOINT' in previous_text and not (refs and refs==old_refs):
        return []
    if refs and old_refs and refs!=old_refs:
        return []
    current_name=named_customer(text);previous_name=named_customer(previous_text)
    if current_name and previous_name and current_name!=previous_name:
        return []
    previous=frozenset().union(*(customer_codes(m['content']) for m in history if m['role']=='user'))
    current=customer_codes(text)
    if current_name and not previous_name and previous and not current:return []
    if current and previous_name and not previous and has_goods_request(text):return []
    return [] if current and previous and current!=previous else history


class OrderBatches:
    def __init__(self, process, delay=90, aggregate=True):
        self.process = process
        self.delay = delay
        self.aggregate = aggregate
        self.pending = {}
        self.last_contact = {}
        self.tasks = set()

    def add(self, group, sender, message_id, text):
        if not self.aggregate:
            # Each source message owns its request and conversation history.
            key = (group, sender, 'message', message_id)
            task = asyncio.create_task(self.process(key, [(message_id, text)]))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return
        base = (group, sender)
        contact = contact_name(text) or self.last_contact.get(base) or 'unspecified'
        self.last_contact[base] = contact
        key = (group, sender, contact)
        entry = self.pending.get(key)
        clients=customer_codes(text)
        refs=document_references(text);mode=message_mode(text);name=named_customer(text)
        if entry and (separate_complete_requests('\n\n'.join(t for _,t in entry['messages']),text)
                      or (clients and entry['clients'] and clients!=entry['clients'])
                      or (name and not entry['name'] and entry['clients'] and not clients)
                      or (clients and entry['name'] and not entry['clients'] and has_goods_request(text))
                      or separate_document_and_goods('\n\n'.join(t for _,t in entry['messages']),text)
                      or ('DOCUMENT JOINT' in text and any('DOCUMENT JOINT' in t for _,t in entry['messages'])
                          and not (refs and refs==entry['references']))
                      or mode!=entry['mode']
                      or (name and entry['name'] and name!=entry['name'])
                      or (refs and entry['references'] and refs!=entry['references'])):
            # Same commercial, different client: dispatch the old order and
            # start a separate batch. Never attach the new client's fees.
            entry['timer'].cancel()
            self.pending.pop(key)
            task=asyncio.create_task(self.process(key,entry['messages']))
            self.tasks.add(task);task.add_done_callback(self.tasks.discard)
            entry=None
        if entry:
            entry['timer'].cancel()
            entry['messages'].append((message_id, text))
            if clients:entry['clients']=clients
            if refs:entry['references']=refs
            if name:entry['name']=name
        else:
            entry = {'messages': [(message_id, text)],'clients':clients,'mode':mode,'references':refs,'name':name}
            self.pending[key] = entry
        task = asyncio.create_task(self.flush(key, entry))
        entry['timer'] = task
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def flush(self, key, entry):
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            return
        if self.pending.get(key) is not entry:
            return
        self.pending.pop(key)
        await self.process(key, entry['messages'])

    async def close(self):
        tasks = list(self.tasks)
        for entry in list(self.pending.values()):
            entry['timer'].cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
