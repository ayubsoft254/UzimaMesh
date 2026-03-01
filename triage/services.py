import json
import requests
import time
import os
from typing import Dict, Any
from django.conf import settings
import threading
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential, AccessToken
from azure.core.exceptions import ServiceResponseTimeoutError
from azure.identity import ChainedTokenCredential, EnvironmentCredential, ManagedIdentityCredential


class ApiKeyCredential:
    """
    TokenCredential implementation that uses a static API key as the bearer token.
    The Azure AI Projects SDK internally calls get_token() on all credentials —
    this wrapper satisfies that contract without requiring az login.
    """
    def __init__(self, api_key: str):
        self._api_key = api_key
        # Set expiry far in the future (year 2099) so it never triggers a refresh
        self._token = AccessToken(token=api_key, expires_on=4102444800)

    def get_token(self, *scopes, **kwargs) -> AccessToken:
        return self._token


# Legacy cached DefaultAzureCredential (used as fallback only)
_token_cache = None
_token_expires_at = 0
_token_lock = threading.Lock()
_global_cred = None

class CachedCredential:
    """
    Caches tokens from an explicit credential chain:
      1. EnvironmentCredential  — works locally and in CI (AZURE_CLIENT_ID/SECRET/TENANT set)
      2. ManagedIdentityCredential — works on App Service with System Assigned Identity

    Avoids DefaultAzureCredential which tries ~13 providers including AzureCLI and
    VisualStudioCode that spawn subprocesses / open sockets and block Uvicorn's
    event loop, causing ServiceResponseError: Connection aborted in production.
    """
    def get_token(self, *scopes, **kwargs):
        global _token_cache, _token_expires_at, _token_lock, _global_cred
        if _global_cred is None:
            _global_cred = ChainedTokenCredential(
                EnvironmentCredential(),
                ManagedIdentityCredential(),
            )
        now = time.time()
        if _token_cache and now < _token_expires_at - 300:
            return _token_cache
        with _token_lock:
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
        api_key = os.getenv("AZURE_AI_API_KEY")

        # Agent Mapping
        self.agents = {
            "intake": os.getenv("AZURE_AI_INTAKE_AGENT_ID"),
            "guardian": os.getenv("AZURE_AI_GUARDIAN_AGENT_ID"),
            "orchestrator": os.getenv("AZURE_AI_ORCHESTRATOR_AGENT_ID"),
            "analysis": os.getenv("AZURE_AI_ANALYSIS_AGENT_ID"),
            "scheduler": os.getenv("AZURE_AI_SCHEDULER_AGENT_ID"),
            "default": os.getenv("AZURE_AI_AGENT_ID")
        }

        if not all([endpoint, self.agents["intake"]]):
            raise ValueError(
                "Missing Azure AI configuration. "
                "Check AZURE_AI_ENDPOINT and Agent IDs in .env"
            )

        # Build connection string for AIProjectClient
        host = endpoint.replace("https://", "").rstrip("/")
        conn_str = f"{host};{sub_id};{rg_name};{project_name}"

        # Use CachedCredential which wraps DefaultAzureCredential.
        # With AZURE_CLIENT_ID + AZURE_CLIENT_SECRET set in .env, 
        # EnvironmentCredential will automatically authenticate via service principal
        # — no 'az login' required.
        auth_credential = ApiKeyCredential(api_key) if api_key else CachedCredential()

        self.client = AIProjectClient.from_connection_string(
            credential=auth_credential,
            conn_str=conn_str,
            # Fail fast on cold-starts / transient Azure latency.
            # 300 s (SDK default) burns the entire App Service request timeout.
            connection_timeout=30,
            read_timeout=90,
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
            if user_data.get('rolling_summary'):
                additional_instructions += (
                    f"\n\nCRITICAL CONTEXT (PREVIOUS SUMMARY): \n{user_data['rolling_summary']}\n"
                    "Use this summary to understand the patient's history so far, as recent raw messages may be truncated."
                )
            
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
            max_completion_tokens=1000,
            truncation_strategy={"type": "last_messages", "last_messages": 10}
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
                                max_completion_tokens=1000,
                                truncation_strategy={"type": "last_messages", "last_messages": 10}
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
            if user_data.get('rolling_summary'):
                additional_instructions += (
                    f"\n\nCRITICAL CONTEXT (PREVIOUS SUMMARY): \n{user_data['rolling_summary']}\n"
                    "Use this summary to understand the patient's history so far, as recent raw messages may be truncated."
                )            

            message = f"[IDENTITY CONTEXT: User={name}, Email={email}]\n{message}"

        # Add message to thread
        context_message = f"[System Context: thread_id={thread_id}]\n{message}"
        try:
            self.client.agents.create_message(
                thread_id=thread_id,
                role="user",
                content=context_message
            )
        except ServiceResponseTimeoutError as _te:
            import logging
            logging.getLogger(__name__).warning(
                "Timeout adding message to thread %s (cold-start?): %s", thread_id, _te
            )
            def _timeout_gen():
                yield json.dumps({
                    "type": "error",
                    "content": "The AI service took too long to respond. Please wait a moment and try again."
                }) + "\n\n"
            return _timeout_gen()
        
        def stream_generator():
            try:
                def process_stream(current_stream, depth=0):
                    """Process a stream, yielding chunks and handling tool calls inline.
                    depth prevents infinite recursion (max 3 levels: init → tool_submit → handoff).
                    """
                    if depth > 3:
                        return
                    
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
                            if hasattr(event_data, 'id'):
                                run_id = event_data.id
                            if hasattr(event_data, 'required_action') and hasattr(event_data.required_action, 'submit_tool_outputs'):
                                tool_calls = list(event_data.required_action.submit_tool_outputs.tool_calls)
                        # Don't yield 'done' here; we emit it once at the very end.

                    # --- Tool calls phase (runs AFTER the for-loop, outside the stream) ---
                    if tool_calls and run_id:
                        from mcp_server.server import (
                            create_triage_record, handoff_to_agent, consult_agent, get_doctor_availability
                        )
                        import concurrent.futures

                        def execute_single_tool(tc):
                            func_name = tc.function.name
                            try:
                                args = json.loads(tc.function.arguments)
                            except json.JSONDecodeError:
                                args = {}
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
                            return {"tool_call_id": tc.id, "output": json.dumps(output)}

                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                            futures = [executor.submit(execute_single_tool, tc) for tc in tool_calls]
                            tool_outputs = [f.result() for f in concurrent.futures.as_completed(futures)]

                        if tool_outputs:
                            with self.client.agents.submit_tool_outputs_to_stream(
                                thread_id=thread_id,
                                run_id=run_id,
                                tool_outputs=tool_outputs
                            ) as resubmit_stream:
                                yield from process_stream(resubmit_stream, depth=depth + 1)

                        # --- Handoff phase: auto-trigger next agent ---
                        # Only at the outermost depth to avoid double-trigger after re-stream.
                        if depth == 0:
                            for tc in tool_calls:
                                if tc.function.name == "handoff_to_agent":
                                    try:
                                        args = json.loads(tc.function.arguments)
                                        target_role = args.get("target_role")
                                        if target_role:
                                            new_agent_id = self.get_agent_id(target_role)
                                            if new_agent_id:
                                                yield json.dumps({"type": "chunk", "content": f"\n\n*[Transferring you to the {target_role} specialist...]*\n\n"}) + "\n\n"

                                                self.client.agents.create_message(
                                                    thread_id=thread_id,
                                                    role="user",
                                                    content=f"[System: User transferred to {target_role}. Introduce yourself and continue.]"
                                                )
                                                with self.client.agents.create_stream(
                                                    thread_id=thread_id,
                                                    assistant_id=new_agent_id,
                                                    additional_instructions=(
                                                        f"You ARE talking to the user. THEY ARE ALREADY LOGGED IN. "
                                                        "Do NOT greet the user, they have been transferred to you. Continue the triage process smoothly."
                                                    ),
                                                    max_completion_tokens=1000,
                                                    truncation_strategy={"type": "last_messages", "last_messages": 10}
                                                ) as handoff_stream:
                                                    yield from process_stream(handoff_stream, depth=depth + 1)
                                    except Exception as e:
                                        print(f"Error auto-triggering handoff: {e}")
                                    break  # Only handle first handoff

                with self.client.agents.create_stream(
                    thread_id=thread_id,
                    assistant_id=agent_id,
                    additional_instructions=additional_instructions,
                    max_completion_tokens=1000,
                    truncation_strategy={"type": "last_messages", "last_messages": 10}
                ) as initial_stream:
                    yield from process_stream(initial_stream, depth=0)

                # Emit done exactly once after everything finishes
                yield json.dumps({"type": "done", "run_status": "completed"}) + "\n\n"

            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.exception(f"Failed to execute stream for thread {thread_id}")
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
    try:
        client = get_project_client()
        return client.create_thread()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Failed to create Azure AI thread")
        raise e


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
