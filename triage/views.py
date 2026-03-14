from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from asgiref.sync import sync_to_async
from rest_framework import viewsets, permissions
from .models import Patient, Doctor, TriageSession, ChatMessage
from .serializers import PatientSerializer, DoctorSerializer, TriageSessionSerializer
import json


# ──────────────────────────────────────────────
# Landing Page & Dashboard Router
# ──────────────────────────────────────────────

def landing_page(request):
    """Render the public landing page."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'triage/landing_page.html')


@login_required
def dashboard(request):
    """
    Role-based router for the main dashboard.
    Redirects users based on their profile type or superuser status.
    """
    if request.user.is_superuser:
        return redirect('admin_dashboard')
    elif hasattr(request.user, 'doctor_profile'):
        return redirect('doctor_dashboard')
    elif hasattr(request.user, 'patient_profile'):
        return redirect('patient_dashboard')
    
    # Default fallback to intake if no profile is found
    return redirect('patient_intake')


@login_required
def patient_dashboard(request):
    """Render the patient-specific portal."""
    patient = getattr(request.user, 'patient_profile', None)
    sessions = []
    if patient:
        sessions = TriageSession.objects.filter(patient=patient).order_by('-created_at')
    
    return render(request, 'triage/patient_dashboard.html', {
        'patient': patient,
        'sessions': sessions,
    })


@login_required
def admin_dashboard(request):
    """Render the high-level system administrator dashboard."""
    if not request.user.is_superuser:
        return redirect('dashboard')
        
    stats = {
        'total_patients': Patient.objects.count(),
        'active_doctors': Doctor.objects.filter(is_available=True).count(),
        'total_sessions': TriageSession.objects.count(),
        'pending_triage': TriageSession.objects.filter(status='PENDING').count(),
    }
    
    recent_sessions = TriageSession.objects.select_related('patient', 'doctor').all()[:15]
    
    return render(request, 'triage/admin_dashboard.html', {
        'stats': stats,
        'recent_sessions': recent_sessions,
    })


@login_required
def mcp_server_info(request):
    """Render basic info about the MCP server (Admin only)."""
    if not request.user.is_superuser:
        return redirect('dashboard')
        
    return render(request, 'triage/mcp_info.html')


def triage_updates(request):
    sessions = TriageSession.objects.select_related(
        'patient', 'doctor'
    ).all()[:10]
    return render(request, 'triage/partials/triage_rows.html', {
        'sessions': sessions,
    })


import logging
import threading

try:
    from .services import create_thread, send_message, send_message_stream, get_project_client
except ImportError:
    # Fallback/mock if azure-ai-projects isn't ready
    def create_thread(): return "mock_thread_id"
    def send_message(tid, msg, role="intake"): return {"content": "Azure AI SDK not fully loaded. I am a mock agent.", "run_status": "completed"}
    def send_message_stream(tid, msg, role="intake"):
        yield '{"type": "chunk", "content": "Azure AI SDK not fully loaded."}\n\n'
        yield '{"type": "done", "run_status": "completed"}\n\n'
    def get_project_client(): return None

logger = logging.getLogger(__name__)


def _is_stale_thread_error(error_text: str) -> bool:
    """Return True only for thread-lifecycle errors that can be fixed by creating a new thread."""
    lowered = (error_text or "").lower()
    stale_markers = [
        "no thread found",
        "no thread found with id",
        "thread not found",
        "thread is active",
        "already has an active run",
        "cannot add messages to thread",
        "(none)",
    ]
    return any(marker in lowered for marker in stale_markers)


def _update_rolling_summary(session_id, thread_id):
    """Fetch a concise AI summary and persist it on the TriageSession.

    Intended to be called from a background daemon thread so it never blocks
    the request/response cycle.
    """
    try:
        sess = TriageSession.objects.get(id=session_id)
        client = get_project_client()
        if client is None:
            return
        summary_prompt = (
            "Please provide a concise medical summary of the patient's symptoms "
            "and state so far, ignoring pleasantries."
        )
        resp = client.send_message(thread_id, summary_prompt, role="analysis")
        if resp and resp.get("content"):
            sess.ai_summary = resp["content"]
            sess.save()
    except Exception:
        logger.exception("Failed to auto-update rolling summary")

# ──────────────────────────────────────────────
# Patient Intake — Conversational UI
# ──────────────────────────────────────────────

@login_required
def patient_intake(request):
    """Render the conversational triage intake page with persistence support."""
    thread_id = None
    
    # 1. Try to get thread_id from database if user is authenticated
    if request.user.is_authenticated:
        patient = getattr(request.user, 'patient_profile', None)
        if patient:
            # Check for most recent incomplete session
            latest_session = TriageSession.objects.filter(
                patient=patient,
                status__in=['PENDING', 'IN_PROGRESS']
            ).order_by('-created_at').first()
            
            if latest_session:
                if latest_session.thread_id:
                    thread_id = latest_session.thread_id
                    request.session['triage_thread_id'] = thread_id
                else:
                    # Update existing session with new thread_id
                    try:
                        thread_id = create_thread()
                        latest_session.thread_id = thread_id
                        latest_session.save()
                        request.session['triage_thread_id'] = thread_id
                    except Exception as e:
                        logger.exception("Failed to create thread during session recovery")
                        thread_id = None
                        latest_session.thread_id = None
                        latest_session.save()
                        if 'triage_thread_id' in request.session:
                            del request.session['triage_thread_id']
    
    # Clean up any legacy mock values
    if thread_id in ("None", "local_mock_thread", "mock_thread_id"):
        thread_id = None

    # 2. Fallback to Django session if not found in DB
    if not thread_id:
        thread_id = request.session.get('triage_thread_id')
        if thread_id in ("None", "local_mock_thread", "mock_thread_id"):
            thread_id = None
    
    # 3. Create fresh thread and session if still not found
    if not thread_id:
        try:
            thread_id = create_thread()
        except Exception as e:
            logger.exception("Failed to create thread during patient intake")
            thread_id = None
            
        if thread_id:
            request.session['triage_thread_id'] = thread_id
        
        # Eagerly create a shell session if authenticated
        if request.user.is_authenticated:
            patient = getattr(request.user, 'patient_profile', None)
            if patient and thread_id:
                TriageSession.objects.get_or_create(
                    patient=patient,
                    status='PENDING',
                    thread_id=thread_id,
                    defaults={
                        'active_agent_role': 'intake'
                    }
                )

    return render(request, 'triage/patient_intake.html', {
        'thread_id': thread_id
    })


@csrf_exempt
@require_POST
def api_chat(request):
    """Receive a chat message from the patient and forward to Azure AI."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_message = data.get('message', '').strip()
    thread_id = data.get('thread_id')

    if not user_message or not thread_id:
        return JsonResponse({'error': 'Missing message or thread_id'}, status=400)

    # 1. Determine the active role for this thread
    role = "intake"
    session_id = None
    session = TriageSession.objects.filter(thread_id=thread_id).order_by('-created_at').first()
    if session:
        role = session.active_agent_role
        session_id = session.id

    # 2. Forward message to Azure Agent with current role and session context
    try:
        context_msg = f"[Context: session_id={session_id}]\n{user_message}" if session_id else user_message
        
        user_data = None
        if request.user.is_authenticated:
            patient = getattr(request.user, 'patient_profile', None)
            if patient:
                user_data = {
                    'first_name': patient.first_name or request.user.first_name,
                    'last_name': patient.last_name or request.user.last_name,
                    'email': patient.email or request.user.email
                }
            else:
                user_data = {
                    'first_name': request.user.first_name,
                    'last_name': request.user.last_name,
                    'email': request.user.email
                }
            
            if session and session.ai_summary:
                user_data['rolling_summary'] = session.ai_summary
        
        response_data = send_message(thread_id, context_msg, role=role, user_data=user_data)
        ai_response_text = response_data.get('content', "I'm sorry, I couldn't process that.")
        run_status = response_data.get('run_status', 'failed')

        if session:
            ChatMessage.objects.create(session=session, role='patient', content=user_message)
            ChatMessage.objects.create(session=session, role='agent', content=ai_response_text)
                
        if session:
            session.refresh_from_db()
            new_role = session.active_agent_role
            if new_role != role:
                role = new_role
                
        if session:
            msg_count = ChatMessage.objects.filter(session=session).count()
            if msg_count > 0 and msg_count % 5 == 0:
                threading.Thread(
                    target=_update_rolling_summary, args=(session.id, thread_id), daemon=True
                ).start()
                
    except Exception as e:
        error_str = str(e)
        if _is_stale_thread_error(error_str):
            try:
                logger.warning("Stale or locked thread detected. Creating a new thread session...")
                new_thread_id = create_thread()
                request.session['triage_thread_id'] = new_thread_id
                
                response_data = send_message(new_thread_id, context_msg, role="intake", user_data=user_data)
                ai_response_text = response_data.get('content', "I'm sorry, I couldn't process that.")
                run_status = response_data.get('run_status', 'failed')
            except Exception as retry_e:
                logger.exception("Failed to retry sending message to Azure Agent")
                ai_response_text = f"An error occurred connecting to the AI Agent (Retry failed): {str(retry_e)}"
                run_status = 'error'
        else:
            logger.exception("Error occurred connecting to the AI Agent")
            ai_response_text = f"An error occurred connecting to the AI Agent: {error_str}"
            run_status = 'error'

    return JsonResponse({
        'status': 'success',
        'message': ai_response_text,
        'run_status': run_status
    })


# ──────────────────────────────────────────────
# Async helpers
# ──────────────────────────────────────────────

def _get_session_by_thread(thread_id):
    """Sync ORM helper: fetch most recent TriageSession for a thread."""
    return TriageSession.objects.filter(
        thread_id=thread_id
    ).order_by('-created_at').first()


def _get_user_data(user):
    """
    Sync helper: resolve a concrete auth user + patient profile into a plain dict.
    Must be called via sync_to_async because it touches the ORM.
    Returns (is_authenticated, user_data_dict_or_None).
    """
    if not user.is_authenticated:
        return False, None

    patient = getattr(user, 'patient_profile', None)
    if patient:
        return True, {
            'first_name': patient.first_name or user.first_name,
            'last_name': patient.last_name or user.last_name,
            'email': patient.email or user.email,
        }
    return True, {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
    }


def _set_session_key(django_session, key, value):
    """Sync helper: write a key into the Django session (DB-backed, sync only)."""
    django_session[key] = value


@csrf_exempt
@require_POST
async def api_chat_stream(request):
    """Receive a chat message and return a StreamingHttpResponse with SSE chunked data."""
    import asyncio
    from django.http import StreamingHttpResponse

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_message = data.get('message', '').strip()
    thread_id = data.get('thread_id')

    if not user_message or not thread_id:
        return JsonResponse({'error': 'Missing message or thread_id'}, status=400)

    user = await request.auser()
    is_authenticated, user_data = await sync_to_async(_get_user_data)(user)
    session = await sync_to_async(_get_session_by_thread)(thread_id)

    role = "intake"
    session_id = None
    if session:
        role = session.active_agent_role
        session_id = session.id
        if is_authenticated and user_data and session.ai_summary:
            user_data['rolling_summary'] = session.ai_summary

    context_msg = f"[Context: session_id={session_id}]\n{user_message}" if session_id else user_message

    async def _async_stream(sync_gen, sess):
        """
        Consume a sync generator on one worker thread and yield SSE chunks
        without blocking the event loop.
        """
        import queue as queue_module

        chunk_queue = queue_module.Queue()
        done_marker = object()
        error_marker = object()

        def _drain_generator():
            try:
                for chunk in sync_gen:
                    chunk_queue.put(chunk)
            except Exception as exc:
                chunk_queue.put((error_marker, exc))
            finally:
                chunk_queue.put(done_marker)

        loop = asyncio.get_running_loop()
        drain_future = loop.run_in_executor(None, _drain_generator)

        full_content = ""

        while True:
            try:
                item = chunk_queue.get_nowait()
            except queue_module.Empty:
                await asyncio.sleep(0.01)
                continue

            if item is done_marker:
                break

            if isinstance(item, tuple) and len(item) == 2 and item[0] is error_marker:
                _, exc = item
                logger.exception("Error reading stream chunk: %s", exc)
                yield json.dumps({"type": "error", "content": str(exc)}) + "\n\n"
                break

            chunk = item
            try:
                parsed = json.loads(chunk.strip())
                if parsed.get('type') == 'chunk':
                    full_content += parsed.get('content', '')
            except Exception:
                pass

            yield chunk

        await drain_future

        if sess and full_content:
            try:
                await sync_to_async(ChatMessage.objects.create)(
                    session=sess, role='agent', content=full_content
                )
                msg_count = await sync_to_async(
                    lambda: ChatMessage.objects.filter(session=sess).count()
                )()
                if msg_count > 0 and msg_count % 5 == 0:
                    threading.Thread(
                        target=_update_rolling_summary, args=(sess.id, thread_id), daemon=True
                    ).start()
            except Exception:
                logger.exception("Failed to persist agent stream response")

    def _make_sse_response(gen, sess=None):
        response = StreamingHttpResponse(
            _async_stream(gen, sess),
            content_type='text/event-stream',
        )
        response['X-Accel-Buffering'] = 'no'
        response['Cache-Control'] = 'no-cache'
        return response

    def _single_error_event(message):
        yield json.dumps({"type": "error", "content": message}) + "\n\n"

    try:
        if session:
            await sync_to_async(ChatMessage.objects.create)(
                session=session, role='patient', content=user_message
            )

        generator = send_message_stream(thread_id, context_msg, role=role, user_data=user_data)
        return _make_sse_response(generator, session)

    except Exception as e:
        error_str = str(e)
        stale_thread = _is_stale_thread_error(error_str)
        if stale_thread:
            try:
                logger.warning("Stale/locked thread detected. Creating a new thread.")
                new_thread_id = await asyncio.to_thread(create_thread)
                await sync_to_async(_set_session_key)(
                    request.session, 'triage_thread_id', new_thread_id
                )
                generator = send_message_stream(
                    new_thread_id, context_msg, role="intake", user_data=user_data
                )
                return _make_sse_response(generator, session)
            except Exception as retry_e:
                logger.exception("Failed to retry sending message stream to Azure Agent")
                return _make_sse_response(
                    _single_error_event(f"Retry failed: {str(retry_e)}"), session
                )

        logger.exception("Error occurred connecting stream to the AI Agent")
        return _make_sse_response(
            _single_error_event(f"Error: {error_str}"), session
        )


# ──────────────────────────────────────────────
# Doctor Command Center
# ──────────────────────────────────────────────

from django.db.models import Case, When, Value, IntegerField

def get_ordered_doctor_queue():
    """Helper to return ordered triage sessions."""
    return TriageSession.objects.select_related('patient', 'doctor').annotate(
        status_order=Case(
            When(status='IN_PROGRESS', then=Value(1)),
            When(status='PENDING', then=Value(2)),
            When(status='COMPLETED', then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
    ).order_by('status_order', '-urgency_score', '-created_at')[:20]

def get_doctor_stats():
    """Helper to return doctor dashboard statistics."""
    return {
        'active_sessions': TriageSession.objects.filter(
            status='IN_PROGRESS'
        ).count(),
        'critical_cases': TriageSession.objects.filter(
            urgency_score__gte=4,
            status__in=['PENDING', 'IN_PROGRESS'],
        ).count(),
        'pending_cases': TriageSession.objects.filter(
            status='PENDING'
        ).count(),
        'avg_wait_time': 15,
    }


def doctor_dashboard(request):
    """Render the doctor command center."""
    doctor = getattr(request.user, 'doctor_profile', None)
    stats = get_doctor_stats()
    sessions = get_ordered_doctor_queue()
    return render(request, 'triage/doctor_dashboard.html', {
        'doctor': doctor,
        'stats': stats,
        'sessions': sessions,
    })


def doctor_queue_updates(request):
    """HTMX partial: refresh the priority-sorted queue."""
    sessions = get_ordered_doctor_queue()
    stats = get_doctor_stats()
    return render(request, 'triage/partials/doctor_queue_rows.html', {
        'sessions': sessions,
        'stats': stats,
    })


@require_POST
def doctor_action(request, session_id):
    """Handle doctor actions: accept, escalate, request vitals, complete."""
    
    session = get_object_or_404(TriageSession, id=session_id)
    action = request.POST.get('action', '')

    if action == 'accept':
        session.status = 'IN_PROGRESS'
        if hasattr(request.user, 'doctor_profile'):
            session.doctor = request.user.doctor_profile
        session.agent_logs += f"\n[Doctor] Case accepted by {request.user}"
        session.save()

    elif action == 'escalate':
        session.status = 'ESCALATED'
        session.urgency_score = min(session.urgency_score + 1, 5)
        session.agent_logs += f"\n[Doctor] Case escalated"
        session.save()

    elif action == 'complete':
        session.status = 'COMPLETED'
        session.agent_logs += f"\n[Doctor] Case completed"
        session.save()

    elif action == 'request_vitals':
        session.agent_logs += f"\n[Doctor] Requested vitals"
        session.save()

    sessions = get_ordered_doctor_queue()
    stats = get_doctor_stats()

    return render(
        request,
        'triage/partials/doctor_queue_rows.html',
        {'sessions': sessions, 'stats': stats}
    )
    
@require_POST
def toggle_availability(request):
    doctor = request.user.doctor_profile
    doctor.is_available = not doctor.is_available
    doctor.save()
    return render(
        request,
        "triage/partials/doctor_availability.html",
        {"doctor": doctor}
    )
    
def reassign_session(request, session_id):
    """Open the reassign modal"""
    session = get_object_or_404(TriageSession, id=session_id)
    doctors = Doctor.objects.filter(is_available=True)
    return render(
        request,
        "triage/partials/reassign_modal.html",
        {"session": session, "doctors": doctors}
    )


@require_POST
def confirm_reassign(request, session_id):
    """Handle reassignment"""
    session = get_object_or_404(TriageSession, id=session_id)
    doctor_id = request.POST.get("doctor")
    doctor = get_object_or_404(Doctor, id=doctor_id)
    session.doctor = doctor
    session.agent_logs += f"\n[System] Case reassigned to {doctor.user}"
    session.save()
    sessions = get_ordered_doctor_queue()
    stats = get_doctor_stats()
    return render(
        request,
        "triage/partials/doctor_queue_rows.html",
        {"sessions": sessions, "stats": stats}
    )
    
def doctor_notifications(request):
    pending = TriageSession.objects.filter(status='PENDING').count()
    return render(
        request,
        "triage/partials/notification_badge.html",
        {"count": pending}
    )


# ──────────────────────────────────────────────
# REST API ViewSets
# ──────────────────────────────────────────────

@login_required
def api_chat_history(request, thread_id):
    """Fetch all previous messages for a specific thread, potentially across sessions."""
    chat_messages = ChatMessage.objects.filter(
        session__thread_id=thread_id
    ).select_related('session').order_by('timestamp')
    
    messages = []
    for msg in chat_messages:
        messages.append({
            'role': msg.role,
            'content': msg.content,
            'timestamp': msg.timestamp.isoformat()
        })
    
    return JsonResponse({'messages': messages})


class PatientViewSet(viewsets.ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer


class DoctorViewSet(viewsets.ModelViewSet):
    queryset = Doctor.objects.all()
    serializer_class = DoctorSerializer


class TriageSessionViewSet(viewsets.ModelViewSet):
    queryset = TriageSession.objects.all()
    serializer_class = TriageSessionSerializer