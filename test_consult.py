import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')
django.setup()

from triage.services import AzureAgentClient

def test():
    client = AzureAgentClient()
    print("Client initialized.")
    thread_id = client.create_thread()
    print(f"Created thread: {thread_id}")
    
    messages = [
        "hi",
        "i have a headache",
        "since yesterday",
        "mild",
        "generalized",
        "resting",
        "not really",
        "it is the first time",
        "no i havd not taken any medication",
        "lack of sleep"
    ]
    
    for msg in messages:
        print(f"\nUser: {msg}")
        response = client.send_message(thread_id, msg, role="intake")
        print(f"Agent: {response.get('content')}")
        print(f"Status: {response.get('run_status')}")

if __name__ == "__main__":
    test()
