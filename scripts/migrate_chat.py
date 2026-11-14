from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.services.conversation_chat import migrate
if __name__=='__main__':print('Chat migration applied' if migrate() else 'Chat migration verified')
