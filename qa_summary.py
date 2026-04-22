import sys, os
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
from core.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    conn.execute(text('ALTER TABLE agent_states ADD COLUMN IF NOT EXISTS qa_summary TEXT'))
    conn.commit()
print('Done: qa_summary added.')
