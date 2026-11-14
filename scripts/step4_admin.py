"""Explicit additive local migration; never calls Sage write operations."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services import sage_preparations
if __name__=='__main__':
    print('Migration applied' if sage_preparations.migrate() else 'Migration checksum verified')
