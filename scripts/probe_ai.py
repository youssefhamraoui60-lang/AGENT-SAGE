import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services.ai import extract
from test_ai import CASES

async def probe():
    try:
        result=await extract(CASES[0])
        print(result.model_dump_json(indent=2))
    except Exception as exc:
        print(type(exc).__name__,str(exc))
        print(getattr(exc,'raw',''))
        raise

asyncio.run(probe())
