import json
import requests
import time
import os
from typing import Dict, Any
from django.conf import settings


class AzureAgentClient:
    """Call Azure AI agents using the official SDK, supporting multiple roles."""
    
    def __init__(self):
        endpoint = settings.AZURE_AI_ENDPOINT
        sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        rg_name = os.getenv("AZURE_RESOURCE_GROUP", "rg-uzima-mesh")
        project_name = os.getenv("AZURE_AI_PROJECT_NAME", "ai-uzima-mesh-project")
        
        # Agent Mapping
        self.agents = {
            "intake": os.getenv("AZURE_AI_INTAKE_AGENT_ID"),
            "guardian": os.getenv("AZURE_AI_GUARDIAN_AGENT_ID"),
            "orchestrator": os.getenv("AZURE_AI_ORCHESTRATOR_AGENT_ID"),
            "analysis": os.getenv("AZURE_AI_ANALYSIS_AGENT_ID"),
            "scheduler": os.getenv("AZURE_AI_SCHEDULER_AGENT_ID"),
            "default": os.getenv("AZURE_AI_AGENT_ID")
        }

        if not all([endpoint, sub_id, self.agents["intake"]]):
            raise ValueError(
                "Missing Azure AI configuration. "
                "Check AZURE_AI_ENDPOINT, AZURE_SUBSCRIPTION_ID, and Agent IDs in .env"
            )

        # Construct connection string
        host = endpoint.replace("https://", "").rstrip("/")
        conn_str = f"{host};{sub_id};{rg_name};{project_name}"

        from azure.ai.projects import AIProjectClient
        from azure.identity import DefaultAzureCredential
        
        self.client = AIProjectClient.from_connection_string(
            credential=DefaultAzureCredential(),
            conn_str=conn_str
        )

    def create_thread(self) -> str:
        """Create a new agent thread."""
        thread = self.client.agents.create_thread()
        return thread.id
    
    def get_agent_id(self, role: str = "intake") -> str:
        """Get agent ID by role."""
        return self.agents.get(role) or self.agents.get("default")

    def send_message(self, thread_id: str, message: str, role: str = "intake") -> Dict[str, Any]:
        """Send message to a specific agent and get response."""
        agent_id = self.get_agent_id(role)
        
        # Add message to thread with system context for thread ID
        context_message = f"[System Context: thread_id={thread_id}]\n{message}"
        
        self.client.agents.create_message(
            thread_id=thread_id,
            role="user",
            content=context_message
        )
        
        # Create and poll run
        run = self.client.agents.create_and_process_run(
            thread_id=thread_id,
            assistant_id=agent_id
        )
        
        # Get latest assistant message
        messages = self.client.agents.list_messages(thread_id=thread_id)
        
        content = ""
        for msg in messages.data:
            if msg.role == "assistant":
                for block in msg.content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            content += block["text"]["value"]
                    else:
                        if getattr(block, "type", None) == "text":
                            content += block.text.value
                break
        
        return {
            "content": content or "No response",
            "run_status": run.status,
            "agent_role": role
        }


# Cache the client instance
_client = None

def get_project_client() -> AzureAgentClient:
    global _client
    if _client is None:
        _client = AzureAgentClient()
    return _client

def create_thread() -> str:
    """Creates a new agent thread and returns its ID."""
    client = get_project_client()
    return client.create_thread()


def send_message(thread_id: str, message: str, role: str = "intake") -> dict:
    """
    Sends a message to the thread, runs the agent, and returns response.
    """
    client = get_project_client()
    return client.send_message(thread_id, message, role=role)
