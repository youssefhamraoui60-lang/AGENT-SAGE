"""Calendar validation and normalization for explicitly supplied supplier dates."""
from datetime import datetime

def normalize_date(value):
    value=value.strip().rstrip('.')
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d.%m.%Y'):
        try:return datetime.strptime(value,fmt).date().isoformat()
        except ValueError:continue
    raise ValueError('Date de régularité invalide : utilisez JJ/MM/AAAA.')
