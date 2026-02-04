"""
Run database schema creation via Supabase.
"""
from dotenv import load_dotenv
import os
import sys

# Load environment
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')

if not url or not key:
    print("ERROR: Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env")
    sys.exit(1)

# Read schema (path relative to this script's location)
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(_backend_dir, 'src', 'db', 'schema.sql'), 'r') as f:
    schema_sql = f.read()

print("Schema SQL loaded successfully!")
print("=" * 60)
print()
print("⚠️  Supabase REST API doesn't support direct SQL execution.")
print("   You need to run the schema manually:")
print()
print("   1. Go to: https://supabase.com/dashboard")
print("   2. Select the project matching your SUPABASE_URL")
print("   3. Click 'SQL Editor' in the sidebar")
print("   4. Click 'New query'")
print("   5. Paste the SQL below and click 'Run'")
print()
print("=" * 60)
print("COPY THIS SQL:")
print("=" * 60)
print()
print(schema_sql)
