import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'
exists = env_path.exists()
loaded = load_dotenv()

print(f"BASE_DIR: {BASE_DIR}")
print(f".env exists: {exists}")
print(f".env loaded: {loaded}")
print(f"AZURE_CLIENT_ID: {os.getenv('AZURE_CLIENT_ID')}")
print(f"AZURE_CLIENT_SECRET: {'***' if os.getenv('AZURE_CLIENT_SECRET') else None}")
