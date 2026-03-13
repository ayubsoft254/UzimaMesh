import json
import logging
import time
import os
import threading
import concurrent.futures
from typing import Dict, Any, Generator

from django.conf import settings
from django.core.exceptions import SuspiciousOperation

from azure.ai.projects import AIProjectClient
from azure.core.exceptions import ServiceResponseTimeoutError
from azure.identity import DefaultAzureCredential

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe singleton helpers
# ---------------------------------------------------------------------------
_client: "AzureAgentClient | None" = None
_client_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Azure Agent Client
# ---------------------------------------------------------------------------

class AzureAgentClient:
    """Call Azure AI agents using the official SDK, supporting multiple roles."""

    def __init__(self) -> None:
        endpoint = settings.AZURE_AI_ENDPOINT
        sub_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        rg_name = os.getenv("AZURE_RESOURCE_GROUP", "rg-uzima-mesh")
        project_name = os.getenv("AZURE_AI_PROJECT_NAME", "ai-uzima-mesh-project")

        # Agent ID mapping (using a single agent for all roles for now)
        single_agent_id = os.getenv("AZURE_AI_INTAKE_AGENT_ID") or os.getenv("AZURE_AI_AGENT_ID")
        self.agents: Dict[str, str | None] = {
            "intake":       single_agent_id,
            "guardian":     single_agent_id,
            "orchestrator": single_agent_id,
            "analysis":     single_agent_id,
            "scheduler":    single_agent_id,
            "default":      single_agent_id,
        }

        if not all([endpoint, self.agents["intake"]]):
            raise ValueError(
                "Missing Azure AI configuration. "
                "Check AZURE_AI_ENDPOINT and Agent IDs in .env"
            )



        # Build connection string for AIProjectClient
        host = endpoint.replace("https://", "").rstrip("/")
        conn_str = f"{host};{sub_id};{rg_name};{project_name}"

        api_key = os.getenv("AZURE_AI_API_KEY")
        if not api_key:
             credential = DefaultAzureCredential()
        else:
            # We must wrap the raw API Key in a TokenCredential interface to satisfy the AIProjectClient
            from azure.core.credentials import AccessToken
            class GenericTokenCredential:
                def __init__(self, key):
                     self.key = key
                def get_token(self, *scopes, **kwargs):
                     return AccessToken(self.key, int(time.time()) + 3600)
            credential = GenericTokenCredential(api_key)

        self.client = AIProjectClient.from_connection_string(
            credential=credential,
            conn_str=conn_str,
            connection_timeout=30,
            read_timeout=90,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def create_thread(self) -> str:
        """Create a new agent thread and return its ID."""
        from azure.core.exceptions import ServiceResponseTimeoutError
        for attempt in range(3):
            try:
                thread = self.client.agents.create_thread()
                return thread.id
            except ServiceResponseTimeoutError as exc:
                if attempt == 2:
                    logger.error("Failed to create thread after 3 attempts due to timeout")
                    raise
                logger.warning("Timeout creating thread, retrying... (attempt %d/3)", attempt + 1)
                time.sleep(1)

    def get_agent_id(self, role: str = "intake") -> str | None:
        """Return the agent ID for *role*, falling back to 'default'."""
        return self.agents.get(role) or self.agents.get("default")

    # ------------------------------------------------------------------
    # Build per-request context helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_additional_instructions(role: str, user_data: dict | None) -> str | None:
        if not user_data:
            return None

        name = (
            f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
            or "Guest"
        )
        email = user_data.get("email", "unknown")
        first_name = (user_data.get("first_name") or name.split()[0]) or "there"

        if role == "intake":
            instructions = (
                f"You ARE talking to {name} (Email: {email}). "
                "THEY ARE ALREADY LOGGED IN. DO NOT ASK FOR THEIR NAME, EMAIL, OR IDENTITY. "
                f"Greet them by saying 'Welcome {first_name} to Uzima Mesh. How are you feeling today?'\n"
                "IMPORTANT: Ask a MAXIMUM of 3-4 questions about their symptoms. After that, STOP asking questions and provide a preliminary triage assessment directly."
            )
        else:
            instructions = (
                f"You ARE talking to {name} (Email: {email}). "
                "THEY ARE ALREADY LOGGED IN. DO NOT ASK FOR THEIR NAME, EMAIL, OR IDENTITY. "
                "Do NOT greet the user, they have been transferred to you. Continue the triage process smoothly.\n"
                "IMPORTANT: Limit your questioning. Once you have a sufficient understanding, do not ask further questions and proceed with the assessment."
            )

        rolling_summary = user_data.get("rolling_summary")
        if rolling_summary:
            instructions += (
                f"\n\nCRITICAL CONTEXT (PREVIOUS SUMMARY):\n{rolling_summary}\n"
                "Use this summary to understand the patient's history so far, "
                "as recent raw messages may be truncated."
            )

        return instructions

    @staticmethod
    def _build_context_message(thread_id: str, message: str, user_data: dict | None) -> str:
        """Inject identity and thread context into the user message (single construction)."""
        if user_data:
            name = (
                f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
                or "Guest"
            )
            email = user_data.get("email", "unknown")
            message = f"[IDENTITY CONTEXT: User={name}, Email={email}]\n{message}"

        return f"[System Context: thread_id={thread_id}]\n{message}"

    # ------------------------------------------------------------------
    # Tool execution (shared between streaming and non-streaming paths)
    # ------------------------------------------------------------------

    @staticmethod
    def _execute_tool(tool_call) -> dict:
        from mcp_server.server import (  # local import to avoid circular deps
            create_triage_record,
            handoff_to_agent,
            consult_agent,
            get_doctor_availability,
        )

        func_name = tool_call.function.name
        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            args = {}

        try:
            import inspect
            from asgiref.sync import async_to_sync

            async def await_res(res):
                return await res

            def run_sync(tool_func, **kw):
                res = tool_func(**kw)
                if inspect.isawaitable(res):
                    return async_to_sync(await_res)(res)
                return res

            if func_name == "create_triage_record":
                output = run_sync(create_triage_record, **args)
            elif func_name == "handoff_to_agent":
                output = run_sync(handoff_to_agent, **args)
            elif func_name == "consult_agent":
                output = run_sync(consult_agent, **args)
            elif func_name == "get_doctor_availability":
                output = run_sync(get_doctor_availability, **args)
            else:
                output = {"error": f"Unknown tool: {func_name}"}
        except Exception as exc:
            output = {"error": str(exc)}

        try:
            output_str = json.dumps(output)
        except Exception as exc:
            output_str = json.dumps({"error": f"Unserializable output: {str(exc)}"})

        return {"tool_call_id": tool_call.id, "output": output_str}

    def _run_tools_parallel(self, tool_calls) -> list:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(self._execute_tool, tc) for tc in tool_calls]
            return [f.result() for f in concurrent.futures.as_completed(futures)]

    # ------------------------------------------------------------------
    # Non-streaming send
    # ------------------------------------------------------------------

    def send_message(
        self,
        thread_id: str,
        message: str,
        role: str = "intake",
        user_data: dict | None = None,
    ) -> Dict[str, Any]:
        """Send a message to a specific agent and return its response."""
        agent_id = self.get_agent_id(role)
        additional_instructions = self._build_additional_instructions(role, user_data)
        context_message = self._build_context_message(thread_id, message, user_data)

        self.client.agents.create_message(
            thread_id=thread_id,
            role="user",
            content=context_message,
        )

        run = self.client.agents.create_run(
            thread_id=thread_id,
            assistant_id=agent_id,
            additional_instructions=additional_instructions,
            max_completion_tokens=10000,
            truncation_strategy={"type": "last_messages", "last_messages": 10},
        )

        start_time = time.time()
        POLL_TIMEOUT = 60  # seconds

        while True:
            if run.status in ("queued", "in_progress"):
                if time.time() - start_time > POLL_TIMEOUT:
                    logger.warning(
                        "Cancelling stalled run after %ds. run_id=%s status=%s",
                        POLL_TIMEOUT, run.id, run.status,
                    )
                    self.client.agents.cancel_run(thread_id=thread_id, run_id=run.id)
                    return {
                        "content": (
                            "I am experiencing delays connecting to the triage systems. "
                            "Please try again."
                        ),
                        "run_status": "error",
                        "agent_role": role,
                    }
                time.sleep(0.5)
                run = self.client.agents.get_run(thread_id=thread_id, run_id=run.id)

            elif run.status == "requires_action":
                start_time = time.time()  # reset so tool execution doesn't eat poll time

                if not (
                    hasattr(run, "required_action")
                    and hasattr(run.required_action, "submit_tool_outputs")
                ):
                    break

                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                tool_outputs = self._run_tools_parallel(tool_calls)

                if not tool_outputs:
                    break

                run = self.client.agents.submit_tool_outputs_to_run(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs,
                )

                # Detect handoff and auto-trigger the target agent
                handoff_target = None
                for tc in tool_calls:
                    if tc.function.name == "handoff_to_agent":
                        try:
                            handoff_target = json.loads(tc.function.arguments).get("target_role")
                        except (json.JSONDecodeError, KeyError):
                            pass
                        break

                if handoff_target:
                    handoff_start = time.time()
                    while run.status in ("queued", "in_progress"):
                        if time.time() - handoff_start > POLL_TIMEOUT:
                            break
                        time.sleep(0.5)
                        run = self.client.agents.get_run(thread_id=thread_id, run_id=run.id)

                    new_agent_id = self.get_agent_id(handoff_target)
                    self.client.agents.create_message(
                        thread_id=thread_id,
                        role="user",
                        content=(
                            f"[System Context: User was successfully transferred to "
                            f"{handoff_target}. Please introduce yourself and continue.]"
                        ),
                    )
                    run = self.client.agents.create_run(
                        thread_id=thread_id,
                        assistant_id=new_agent_id,
                        additional_instructions=(
                            "You ARE talking to the user. THEY ARE ALREADY LOGGED IN. "
                            "Do NOT greet the user, they have been transferred to you. "
                            "Continue the triage process smoothly."
                        ),
                        max_completion_tokens=10000,
                        truncation_strategy={"type": "last_messages", "last_messages": 10},
                    )
                    role = handoff_target
                    start_time = time.time()  # reset for new run

            else:
                break

        # Retrieve the latest assistant message
        messages = self.client.agents.list_messages(thread_id=thread_id)
        content = ""
        for msg in messages.data:
            if msg.role == "assistant":
                for block in getattr(msg, "content", []):
                    if hasattr(block, 'text') and hasattr(block.text, 'value'):
                        content += block.text.value
                    elif hasattr(block, 'type') and getattr(block, 'type') == 'text' and hasattr(block, 'text'):
                        content += block.text.value if hasattr(block.text, 'value') else getattr(block.text, 'value', str(block.text))
                    elif isinstance(block, dict):
                        text_val = block.get('text', {}).get('value', '') if isinstance(block.get('text'), dict) else block.get('text', '')
                        if text_val:
                            content += text_val
                break

        return {
            "content": content or "No response",
            "run_status": run.status,
            "agent_role": role,
        }

    # ------------------------------------------------------------------
    # Streaming send
    # ------------------------------------------------------------------

    def send_message_stream(
        self,
        thread_id: str,
        message: str,
        role: str = "intake",
        user_data: dict | None = None,
    ) -> Generator:
        """Stream a message to a specific agent and yield SSE-style JSON chunks."""
        agent_id = self.get_agent_id(role)
        additional_instructions = self._build_additional_instructions(role, user_data)
        context_message = self._build_context_message(thread_id, message, user_data)

        try:
            self.client.agents.create_message(
                thread_id=thread_id,
                role="user",
                content=context_message,
            )
        except ServiceResponseTimeoutError as exc:
            logger.warning(
                "Timeout adding message to thread %s (cold-start?): %s", thread_id, exc
            )

            def _timeout_gen():
                yield json.dumps({
                    "type": "error",
                    "content": (
                        "The AI service took too long to respond. "
                        "Please wait a moment and try again."
                    ),
                }) + "\n\n"

            return _timeout_gen()

        except SuspiciousOperation as exc:
            logger.error("Disallowed host blocked during stream setup: %s", exc)

            def _host_error_gen():
                yield json.dumps({
                    "type": "error",
                    "content": "Request blocked: disallowed host.",
                }) + "\n\n"

            return _host_error_gen()

        def stream_generator():
            try:
                def process_stream(current_stream, depth: int = 0):
                    """Recursively process a stream, handling tool calls and handoffs.

                    depth cap:
                      0 -> initial run
                      1 -> tool-output re-stream
                      2 -> handoff agent stream
                      3 -> safety cap (return immediately)
                    """
                    if depth > 3:
                        return

                    run_id = None
                    tool_calls_seen = []

                    for event_item in current_stream:
                        event_type = getattr(event_item, "event", getattr(event_item, "type", type(event_item).__name__))
                        event_data = getattr(event_item, "data", event_item)

                        if event_type == "thread.run.created" or "RunCreated" in type(event_data).__name__:
                            run_id = getattr(event_data, "id", None)

                        elif event_type == "thread.message.delta" or "MessageDelta" in type(event_data).__name__:
                            delta_obj = getattr(event_data, "delta", event_data)
                            for block in getattr(delta_obj, "content", []):
                                if hasattr(block, 'text') and hasattr(block.text, 'value'):
                                    text_val = block.text.value
                                    yield json.dumps({"type": "chunk", "content": text_val}) + "\n\n"
                                elif hasattr(block, 'type') and getattr(block, 'type') == 'text' and hasattr(block, 'text'):
                                    text_val = block.text.value if hasattr(block.text, 'value') else getattr(block.text, 'value', str(block.text))
                                    yield json.dumps({"type": "chunk", "content": text_val}) + "\n\n"
                                elif isinstance(block, dict):
                                    text_val = block.get('text', {}).get('value', '') if isinstance(block.get('text'), dict) else block.get('text', '')
                                    if text_val:
                                        yield json.dumps({"type": "chunk", "content": text_val}) + "\n\n"
                                else:
                                    logger.debug("Unknown block type in delta: %s", block)

                        elif event_type == "thread.run.requires_action" or "RequiresAction" in type(event_data).__name__:
                            if hasattr(event_data, "id"):
                                run_id = event_data.id
                            if hasattr(event_data, "required_action") and hasattr(event_data.required_action, "submit_tool_outputs"):
                                tool_calls_seen = list(event_data.required_action.submit_tool_outputs.tool_calls)

                    # ---- Post-stream: execute tools ----
                    if tool_calls_seen and run_id:
                        tool_outputs = self._run_tools_parallel(tool_calls_seen)

                        if tool_outputs:
                            with self.client.agents.submit_tool_outputs_to_stream(
                                thread_id=thread_id,
                                run_id=run_id,
                                tool_outputs=tool_outputs,
                            ) as resubmit_stream:
                                yield from process_stream(resubmit_stream, depth=depth + 1)

                        # ---- Handoff (only at depth 0 to avoid double-trigger) ----
                        if depth == 0:
                            for tc in tool_calls_seen:
                                if tc.function.name == "handoff_to_agent":
                                    try:
                                        args = json.loads(tc.function.arguments)
                                        target_role = args.get("target_role")
                                        if target_role:
                                            new_agent_id = self.get_agent_id(target_role)
                                            if new_agent_id:
                                                yield json.dumps({
                                                    "type": "chunk",
                                                    "content": (
                                                        f"\n\n*[Transferring you to the "
                                                        f"{target_role} specialist...]*\n\n"
                                                    ),
                                                }) + "\n\n"

                                                self.client.agents.create_message(
                                                    thread_id=thread_id,
                                                    role="user",
                                                    content=(
                                                        f"[System: User transferred to {target_role}. "
                                                        "Introduce yourself and continue.]"
                                                    ),
                                                )
                                                with self.client.agents.create_stream(
                                                    thread_id=thread_id,
                                                    assistant_id=new_agent_id,
                                                    additional_instructions=(
                                                        "You ARE talking to the user. "
                                                        "THEY ARE ALREADY LOGGED IN. "
                                                        "Do NOT greet the user, they have been "
                                                        "transferred to you. Continue smoothly."
                                                    ),
                                                    max_completion_tokens=10000,
                                                    truncation_strategy={
                                                        "type": "last_messages",
                                                        "last_messages": 10,
                                                    },
                                                ) as handoff_stream:
                                                    yield from process_stream(
                                                        handoff_stream, depth=depth + 1
                                                    )
                                    except (json.JSONDecodeError, KeyError) as exc:
                                        logger.warning("Handoff parse error: %s", exc)
                                    break  # Only handle the first handoff per run

                with self.client.agents.create_stream(
                    thread_id=thread_id,
                    assistant_id=agent_id,
                    additional_instructions=additional_instructions,
                    max_completion_tokens=10000,
                    truncation_strategy={"type": "last_messages", "last_messages": 10},
                ) as initial_stream:
                    yield from process_stream(initial_stream, depth=0)

                # Emit done exactly once after everything finishes
                yield json.dumps({"type": "done", "run_status": "completed"}) + "\n\n"

            except SuspiciousOperation as exc:
                logger.error("Disallowed host in stream: %s", exc)
                yield json.dumps({"type": "error", "content": "Request blocked: disallowed host."}) + "\n\n"
            except Exception as exc:
                logger.exception("Failed to execute stream for thread %s", thread_id)
                yield json.dumps({"type": "error", "content": str(exc)}) + "\n\n"

        return stream_generator()


# ---------------------------------------------------------------------------
# Module-level API (thread-safe singleton)
# ---------------------------------------------------------------------------

def get_project_client() -> AzureAgentClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:  # double-checked locking
                _client = AzureAgentClient()
    return _client


def create_thread() -> str:
    """Create a new agent thread and return its ID."""
    try:
        return get_project_client().create_thread()
    except Exception:
        logger.exception("Failed to create Azure AI thread")
        raise


def send_message(
    thread_id: str,
    message: str,
    role: str = "intake",
    user_data: dict | None = None,
) -> dict:
    """Send a message, run the agent, and return the response dict."""
    return get_project_client().send_message(thread_id, message, role=role, user_data=user_data)


def send_message_stream(
    thread_id: str,
    message: str,
    role: str = "intake",
    user_data: dict | None = None,
) -> Generator:
    """Send a message via the streaming API and return a generator of SSE chunks."""
    return get_project_client().send_message_stream(
        thread_id, message, role=role, user_data=user_data
    )