import json
import requests
import time
import os
from typing import Dict, Any
from django.conf import settings
import threading
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# Global thread-safe token cache
_token_cache = None
_token_expires_at = 0
_token_lock = threading.Lock()
_global_cred = None

class CachedCredential:
    def get_token(self, *scopes, **kwargs):
        global _token_cache, _token_expires_at, _token_lock, _global_cred
        
        # Initialize credential lazily to avoid blocking imports
        if _global_cred is None:
            _global_cred = DefaultAzureCredential()
            
        import time
        now = time.time()
        
        # Fast path (no lock): if token is valid and not close to expiry
        if _token_cache and now < _token_expires_at - 300:
            return _token_cache
        
        # Slow path (with lock): fetch new token
        with _token_lock:
            # Double-checked locking
            now = time.time()
            if not _token_cache or now > _token_expires_at - 300:
                _token_cache = _global_cred.get_token(*scopes, **kwargs)
                _token_expires_at = _token_cache.expires_on
            return _token_cache


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

        self.client = AIProjectClient.from_connection_string(
            credential=CachedCredential(),
            conn_str=conn_str
        )

    def create_thread(self) -> str:
        """Create a new agent thread."""
        thread = self.client.agents.create_thread()
        return thread.id
    
    def get_agent_id(self, role: str = "intake") -> str:
        """Get agent ID by role."""
        return self.agents.get(role) or self.agents.get("default")

    def send_message(self, thread_id: str, message: str, role: str = "intake", user_data: dict = None) -> Dict[str, Any]:
        """Send message to a specific agent and get response."""
        agent_id = self.get_agent_id(role)
        
        # Add message to thread with system context for thread ID
        context_message = f"[System Context: thread_id={thread_id}]\n{message}"
        
        # Prepare personalization instructions if user_data is provided
        additional_instructions = None
        if user_data:
            name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or "Guest"
            email = user_data.get('email', 'unknown')
            first_name = user_data.get('first_name') or name.split()[0] or "there"
            
            # Additional run instructions
            if role == "intake":
                additional_instructions = (
                    f"You ARE talking to {name} (Email: {email}). "
                    "THEY ARE ALREADY LOGGED IN. DO NOT ASK FOR THEIR NAME, EMAIL, OR IDENTITY. "
                    f"Greet them by saying 'Welcome {first_name} to Uzima Mesh. How are you feeling today?'"
                )
            else:
                additional_instructions = (
                    f"You ARE talking to {name} (Email: {email}). "
                    "THEY ARE ALREADY LOGGED IN. DO NOT ASK FOR THEIR NAME, EMAIL, OR IDENTITY. "
                    "Do NOT greet the user, they have been transferred to you. Continue the triage process smoothly."
                )
            # Inject context into message for absolute certainty
            message = f"[IDENTITY CONTEXT: User={name}, Email={email}]\n{message}"

        context_message = f"[System Context: thread_id={thread_id}]\n{message}"

        self.client.agents.create_message(
            thread_id=thread_id,
            role="user",
            content=context_message
        )
        
        # Create run manually and poll to handle tool calls
        run = self.client.agents.create_run(
            thread_id=thread_id,
            assistant_id=agent_id,
            additional_instructions=additional_instructions,
            max_completion_tokens=10000  # Increased for detailed assessments
        )
        
        import time
        start_time = time.time()
        
        while True:
            if run.status in ["queued", "in_progress"]:
                if time.time() - start_time > 60:
                    print(f"Cancelling stalled run after 60 seconds. Run ID: {run.id}, Status: {run.status}")
                    self.client.agents.cancel_run(thread_id=thread_id, run_id=run.id)
                    return {"content": "I am experiencing delays connecting to the triage systems. Please try again.", "run_status": "error", "agent_role": role}
                time.sleep(0.5)
                run = self.client.agents.get_run(thread_id=thread_id, run_id=run.id)
            elif run.status == "requires_action":
                start_time = time.time()  # Reset timeout for tool execution and subsequent steps
                # Extract tool calls and execute them concurrently
                from mcp_server.server import (
                    create_triage_record, handoff_to_agent, consult_agent, get_doctor_availability
                )
                import concurrent.futures
                
                tool_outputs = []
                if hasattr(run, "required_action") and hasattr(run.required_action, "submit_tool_outputs"):
                    
                    def execute_single_tool(tool_call):
                        func_name = tool_call.function.name
                        try:
                            args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            args = {}
                        
                        output = None
                        try:
                            if func_name == "create_triage_record":
                                output = create_triage_record(**args)
                            elif func_name == "handoff_to_agent":
                                output = handoff_to_agent(**args)
                            elif func_name == "consult_agent":
                                output = consult_agent(**args)
                            elif func_name == "get_doctor_availability":
                                output = get_doctor_availability(**args)
                            else:
                                output = {"error": f"Unknown tool: {func_name}"}
                        except Exception as e:
                            output = {"error": str(e)}
                        
                        return {
                            "tool_call_id": tool_call.id,
                            "output": json.dumps(output)
                        }

                    tool_calls = run.required_action.submit_tool_outputs.tool_calls
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        futures = [executor.submit(execute_single_tool, tc) for tc in tool_calls]
                        for future in concurrent.futures.as_completed(futures):
                            tool_outputs.append(future.result())
                    
                    if tool_outputs:
                        run = self.client.agents.submit_tool_outputs_to_run(
                            thread_id=thread_id,
                            run_id=run.id,
                            tool_outputs=tool_outputs
                        )
                        
                        # Check if handoff occurred
                        handoff_target = None
                        for tc in tool_calls:
                            if tc.function.name == "handoff_to_agent":
                                try:
                                    args = json.loads(tc.function.arguments)
                                    handoff_target = args.get("target_role")
                                except:
                                    pass
                        
                        if handoff_target:
                            # We just wait for the current run to finish (it will likely be blank)
                            while run.status in ["queued", "in_progress"]:
                                time.sleep(0.5)
                                run = self.client.agents.get_run(thread_id=thread_id, run_id=run.id)
                            
                            # Automatically trigger the new agent
                            new_agent_id = self.get_agent_id(handoff_target)
                            new_instructions = (
                                f"You ARE talking to user. THEY ARE ALREADY LOGGED IN. "
                                "Do NOT greet the user, they have been transferred to you. Continue the triage process smoothly."
                            )
                            
                            self.client.agents.create_message(
                                thread_id=thread_id,
                                role="user",
                                content=f"[System Context: User was successfully transferred to {handoff_target}. Please introduce yourself and continue.]"
                            )
                            
                            run = self.client.agents.create_run(
                                thread_id=thread_id,
                                assistant_id=new_agent_id,
                                additional_instructions=new_instructions,
                                max_completion_tokens=10000
                            )
                            role = handoff_target # update role for final return
                            
                    else:
                        break
                else:
                    break
            else:
                break

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



    def send_message_stream(self, thread_id: str, message: str, role: str = "intake", user_data: dict = None):
        """Streams message to a specific agent using Azure generator API."""
        agent_id = self.get_agent_id(role)
        
        # Add message to thread
        context_message = f"[System Context: thread_id={thread_id}]\n{message}"
        
        # Prepare personalization instructions if user_data is provided
        additional_instructions = None
        if user_data:
            name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or "Guest"
            email = user_data.get('email', 'unknown')
            first_name = user_data.get('first_name') or name.split()[0] or "there"
            
            # Additional run instructions
            if role == "intake":
                additional_instructions = (
                    f"You ARE talking to {name} (Email: {email}). "
                    "THEY ARE ALREADY LOGGED IN. DO NOT ASK FOR THEIR NAME, EMAIL, OR IDENTITY. "
                    f"Greet them by saying 'Welcome {first_name} to Uzima Mesh. How are you feeling today?'"
                )
            else:
                additional_instructions = (
                    f"You ARE talking to {name} (Email: {email}). "
                    "THEY ARE ALREADY LOGGED IN. DO NOT ASK FOR THEIR NAME, EMAIL, OR IDENTITY. "
                    "Do NOT greet the user, they have been transferred to you. Continue the triage process smoothly."
                )
            # Inject context into message for absolute certainty
            message = f"[IDENTITY CONTEXT: User={name}, Email={email}]\n{message}"

        # Add message to thread
        context_message = f"[System Context: thread_id={thread_id}]\n{message}"
        self.client.agents.create_message(
            thread_id=thread_id,
            role="user",
            content=context_message
        )
        
        def stream_generator():
            try:
                def process_stream(current_stream):
                    requires_action = False
                    run_id = None
                    tool_calls = []
                    
                    for event_tuple in current_stream:
                        if not isinstance(event_tuple, tuple) or len(event_tuple) != 2:
                            continue
                        event_type, event_data = event_tuple
                        
                        if event_type == "thread.run.created":
                            run_id = getattr(event_data, "id", None)
                        elif event_type == "thread.message.delta":
                            for block in event_data.delta.content:
                                if getattr(block, 'type', None) == 'text' or (isinstance(block, dict) and block.get('type') == 'text'):
                                    text_val = block.text.value if not isinstance(block, dict) else block["text"]["value"]
                                    yield json.dumps({"type": "chunk", "content": text_val}) + "\n\n"
                        elif event_type == "thread.run.requires_action":
                            requires_action = True
                            if hasattr(event_data, 'id'):
                                run_id = event_data.id
                            if hasattr(event_data, 'required_action') and hasattr(event_data.required_action, 'submit_tool_outputs'):
                                tool_calls = event_data.required_action.submit_tool_outputs.tool_calls
                        elif event_type == "thread.run.completed":
                            yield json.dumps({"type": "done", "run_status": "completed"}) + "\n\n"
                    
                    if requires_action and tool_calls and run_id:
                        from mcp_server.server import (
                            create_triage_record, handoff_to_agent, consult_agent, get_doctor_availability
                        )
                        import concurrent.futures
                        
                        tool_outputs = []
                        def execute_single_tool(tc):
                            func_name = tc.function.name
                            try:
                                args = json.loads(tc.function.arguments)
                            except json.JSONDecodeError:
                                args = {}
                                
                            output = None
                            try:
                                if func_name == "create_triage_record":
                                    output = create_triage_record(**args)
                                elif func_name == "handoff_to_agent":
                                    output = handoff_to_agent(**args)
                                elif func_name == "consult_agent":
                                    output = consult_agent(**args)
                                elif func_name == "get_doctor_availability":
                                    output = get_doctor_availability(**args)
                                else:
                                    output = {"error": f"Unknown tool: {func_name}"}
                            except Exception as e:
                                output = {"error": str(e)}
                                
                            return {
                                "tool_call_id": tc.id,
                                "output": json.dumps(output)
                            }

                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                            futures = [executor.submit(execute_single_tool, tc) for tc in tool_calls]
                            for future in concurrent.futures.as_completed(futures):
                                tool_outputs.append(future.result())
                                
                        if tool_outputs:
                            with self.client.agents.submit_tool_outputs_to_stream(
                                thread_id=thread_id,
                                run_id=run_id,
                                tool_outputs=tool_outputs
                            ) as new_stream:
                                yield from process_stream(new_stream)

                        # Check if a handoff occurred to auto-trigger the next agent
                        for tc in tool_calls:
                            if tc.function.name == "handoff_to_agent":
                                try:
                                    args = json.loads(tc.function.arguments)
                                    target_role = args.get("target_role")
                                    if target_role:
                                        yield json.dumps({"type": "chunk", "content": f"\n\n*[System: Transferring you to the {target_role} agent...]*\n\n"}) + "\n\n"
                                        
                                        new_agent_id = self.get_agent_id(target_role)
                                        new_instructions = (
                                            f"You ARE talking to user. THEY ARE ALREADY LOGGED IN. "
                                            "Do NOT greet the user, they have been transferred to you. Continue the triage process smoothly."
                                        )
                                        
                                        # Auto-trigger the new agent without requiring the user to send a message
                                        self.client.agents.create_message(
                                            thread_id=thread_id,
                                            role="user",
                                            content=f"[System Context: User was successfully transferred to {target_role}. Please introduce yourself and continue.]"
                                        )
                                        
                                        with self.client.agents.create_stream(
                                            thread_id=thread_id,
                                            assistant_id=new_agent_id,
                                            additional_instructions=new_instructions,
                                            max_completion_tokens=10000
                                        ) as next_agent_stream:
                                            yield from process_stream(next_agent_stream)
                                except Exception as e:
                                    print(f"Error auto-triggering handoff: {e}")
                                break

                with self.client.agents.create_stream(
                    thread_id=thread_id,
                    assistant_id=agent_id,
                    additional_instructions=additional_instructions,
                    max_completion_tokens=10000
                ) as initial_stream:
                    yield from process_stream(initial_stream)

            except Exception as e:
                yield json.dumps({"type": "error", "content": str(e)}) + "\n\n"
        
        return stream_generator()

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


def send_message(thread_id: str, message: str, role: str = "intake", user_data: dict = None) -> dict:
    """
    Sends a message to the thread, runs the agent, and returns response.
    """
    client = get_project_client()
    return client.send_message(thread_id, message, role=role, user_data=user_data)

def send_message_stream(thread_id: str, message: str, role: str = "intake", user_data: dict = None):
    """
    Sends a message to the thread, runs the agent via stream, and returns a generator.
    """
    client = get_project_client()
    return client.send_message_stream(thread_id, message, role=role, user_data=user_data)
