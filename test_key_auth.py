import os
import django
import time

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')
django.setup()

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

print("Testing AIProjectClient with DefaultAzureCredential...")

endpoint = os.getenv("AZURE_AI_ENDPOINT")
sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
rg_name = os.getenv("AZURE_RESOURCE_GROUP", "rg-uzima-mesh")
project_name = os.getenv("AZURE_AI_PROJECT_NAME", "ai-uzima-mesh-project")

host = endpoint.replace("https://", "").rstrip("/")
conn_str = f"{host};{sub_id};{rg_name};{project_name}"

print("Testing DefaultAzureCredential...")
start = time.time()
try:
    client = AIProjectClient.from_connection_string(
        credential=DefaultAzureCredential(),
        conn_str=conn_str
    )
    thread = client.agents.create_thread()
    print(f"SUCCESS in {time.time() - start:.3f}s. Thread: {thread.id}")
except Exception as e:
    print(f"FAILED: {e}")
    print(f"FAILED: {e}")

