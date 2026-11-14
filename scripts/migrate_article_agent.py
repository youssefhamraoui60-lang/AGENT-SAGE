"""Apply additive local PostgreSQL migration; no SQL Server/Sage writes."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services.article_agent import migrate
if __name__=='__main__':print('Article-agent migration applied' if migrate() else 'Article-agent migration verified')
