"""SOB document decoding subprocess, called with the backend Python environment."""
import json
from pathlib import Path
import sys
from read_documents_layout import read
from document_memory import decode

if __name__=='__main__':
    try:
        path=Path(sys.argv[1]).resolve()
        allowed=Path(__file__).resolve().parents[1]/'runtime/telegram-test/documents'
        if not path.is_relative_to(allowed.resolve()) or path.stat().st_size>10*1024*1024:raise ValueError('Document hors périmètre ou trop volumineux')
        print(json.dumps(decode(path, read),ensure_ascii=False))
    except Exception:
        print(json.dumps({'ok':False,'text':'Lecture du document à vérifier : préciser le client, les articles et quantités sans inventer les données.'}))
