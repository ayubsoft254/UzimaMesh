import json
from django.conf import settings
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

# Cache the client so we don't recreate it on every request
_client = None

def get_project_client() -> AIProjectClient:
    global _client
    if _client is None:
        if not settings.AZURE_AI_PROJECT_CONNECTION_STRING:
            raise ValueError("AZURE_AI_PROJECT_CONNECTION_STRING is not set in settings.")
            
        _client = AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(),
            conn_str=settings.AZURE_AI_PROJECT_CONNECTION_STRING,
        )
    return _client

def create_thread() -> str:
    """Creates a new agent thread and returns its ID."""
    client = get_project_client()
    thread = client.agents.create_thread()
    return thread.id

def send_message(thread_id: str, message: str) -> dict:
    """
    Sends a message to the thread, runs the agent, and blocks until 
    completed. Handles tool calls internally.
    Returns the agent's textual response and any relevant status.
    """
    if not settings.AZURE_AI_AGENT_ID:
        raise ValueError("AZURE_AI_AGENT_ID is not set in settings.")

    client = get_project_client()
    
    # Send user message
    client.agents.create_message(
        thread_id=thread_id,
        role="user",
        content=message,
    )
    
    # Run the agent
    run = client.agents.create_and_process_run(
        thread_id=thread_id,
        assistant_id=settings.AZURE_AI_AGENT_ID
    )

    # Note: create_and_process_run automatically handles the MCP tools 
    # attached to the agent configuration on Azure !
    
    # Fetch the assistant's latest message after completion
    messages = client.agents.list_messages(thread_id=thread_id)
    
    # Messages are ordered latest first
    latest_msg = messages.data[0]
    content = ""
    # Filter text blocks
    for text_item in latest_msg.content:
        # Assuming TextContentBlock type from SDK
        if hasattr(text_item, 'text'):
            content += text_item.text.value
            
    return {
        "content": content,
        "run_status": run.status
    }
