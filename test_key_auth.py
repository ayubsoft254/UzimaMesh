import os
import django
import time

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')
django.setup()

from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from triage.services import CachedCredential

print("Testing direct AIProjectClient with AzureKeyCredential vs CachedCredential...")

endpoint = os.getenv("AZURE_AI_ENDPOINT")
sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
rg_name = os.getenv("AZURE_RESOURCE_GROUP", "rg-uzima-mesh")
project_name = os.getenv("AZURE_AI_PROJECT_NAME", "ai-uzima-mesh-project")
api_key = os.getenv("AZURE_AI_API_KEY")

host = endpoint.replace("https://", "").rstrip("/")
conn_str = f"{host};{sub_id};{rg_name};{project_name}"

print("1. Testing AzureKeyCredential...")
start = time.time()
try:
    client1 = AIProjectClient.from_connection_string(
        credential=AzureKeyCredential(api_key),
        conn_str=conn_str
    )
    thread1 = client1.agents.create_thread()
    print(f"SUCCESS in {time.time() - start:.3f}s. Thread: {thread1.id}")
except Exception as e:
    print(f"FAILED: {e}")

print("\n2. Testing DefaultAzureCredential...")
start = time.time()
try:
    client2 = AIProjectClient.from_connection_string(
        credential=CachedCredential(),
        conn_str=conn_str
    )
    thread2 = client2.agents.create_thread()
    print(f"SUCCESS in {time.time() - start:.3f}s. Thread: {thread2.id}")
except Exception as e:
    print(f"FAILED: {e}")
    
