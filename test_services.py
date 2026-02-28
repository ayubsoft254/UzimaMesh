import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')
django.setup()

from triage.services import create_thread, send_message_stream, get_project_client
try:
    print("Testing get_project_client()...")
    client = get_project_client()
    print("Client initialized successfully.")
    
    print("Testing create_thread()...")
    thread_id = create_thread()
    print(f"Created thread: {thread_id}")
    
    print("Testing send_message_stream()...")
    generator = send_message_stream(thread_id, "Hello from local test", role="intake")
    for chunk in generator:
        print(chunk)
        
    print("All tests passed.")
except Exception as e:
    print(f"FAILED WITH EXCEPTION: {e}")
    import traceback
    traceback.print_exc()
