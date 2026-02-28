from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
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


try:
    from .services import create_thread, send_message, send_message_stream
except ImportError:
    # Fallback/mock if azure-ai-projects isn't ready
    def create_thread(): return "mock_thread_id"
    def send_message(tid, msg, role="intake"): return {"content": "Azure AI SDK not fully loaded. I am a mock agent.", "run_status": "completed"}
    def send_message_stream(tid, msg, role="intake"):
        yield '{"type": "chunk", "content": "Azure AI SDK not fully loaded."}\n\n'
        yield '{"type": "done", "run_status": "completed"}\n\n'

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
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.exception("Failed to create thread during session recovery")
                        thread_id = "local_mock_thread"
                        latest_session.thread_id = thread_id
                        latest_session.save()
                        request.session['triage_thread_id'] = thread_id
    
    # Clean up any legacy string "None" values
    if thread_id == "None":
        thread_id = None

    # 2. Fallback to Django session if not found in DB
    if not thread_id:
        thread_id = request.session.get('triage_thread_id')
        if thread_id == "None":
            thread_id = None
    
    # 3. Create fresh thread and session if still not found
    if not thread_id:
        try:
            thread_id = create_thread()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Failed to create thread during patient intake")
            thread_id = "local_mock_thread"
            
        request.session['triage_thread_id'] = thread_id
        
        # Eagerly create a shell session if authenticated
        if request.user.is_authenticated:
            patient = getattr(request.user, 'patient_profile', None)
            if patient:
                # Use get_or_create to avoid duplicates if user refreshes before chat starts
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
        # Prepend session info so tools like handoff_to_agent have the ID
        context_msg = f"[Context: session_id={session_id}]\n{user_message}" if session_id else user_message
        
        # Strategy: Personalization - Fetch patient data
        user_data = None
        if request.user.is_authenticated:
            patient = getattr(request.user, 'patient_profile', None)
            if patient:
                user_data = {
                    # Read from Patient model fields first (populated at signup)
                    'first_name': patient.first_name or request.user.first_name,
                    'last_name': patient.last_name or request.user.last_name,
                    'email': patient.email or request.user.email
                }
            else:
                # Fallback to User model
                user_data = {
                    'first_name': request.user.first_name,
                    'last_name': request.user.last_name,
                    'email': request.user.email
                }
            
            # Inject the rolling AI summary to maintain diagnostic context
            # while truncating raw history messages.
            if session and session.ai_summary:
                user_data['rolling_summary'] = session.ai_summary
        
        response_data = send_message(thread_id, context_msg, role=role, user_data=user_data)
        ai_response_text = response_data.get('content', "I'm sorry, I couldn't process that.")
        run_status = response_data.get('run_status', 'failed')

        # 3. Log messages to database for persistence
        if session:
            ChatMessage.objects.create(session=session, role='patient', content=user_message)
            ChatMessage.objects.create(session=session, role='agent', content=ai_response_text)
                
        # 4. Check if the role changed during the run (via tool call)
        if session:
            session.refresh_from_db()
            new_role = session.active_agent_role
            if new_role != role:
                role = new_role
                
        # 5. Trigger automatic rolling summary if message count is a multiple of 5
        if session:
            msg_count = ChatMessage.objects.filter(session=session).count()
            # We trigger a background summarize every 5 messages to ensure truncation 
            # (which removes the last 10) never loses context.
            if msg_count > 0 and msg_count % 5 == 0:
                import threading
                from .services import get_project_client
                def update_summary(session_id, tid):
                    try:
                        sess = TriageSession.objects.get(id=session_id)
                        client = get_project_client()
                        # Use analysis or default agent to summarize
                        summary_prompt = "Please provide a concise medical summary of the patient's symptoms and state so far, ignoring pleasantries."
                        resp = client.send_message(tid, summary_prompt, role="analysis")
                        if resp and resp.get("content"):
                            sess.ai_summary = resp["content"]
                            sess.save()
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception("Failed to auto-update rolling summary")
                        
                threading.Thread(target=update_summary, args=(session.id, thread_id)).start()
                
    except Exception as e:
        error_str = str(e)
        # Handle expired/invalid threads by automatically creating a new one
        if "no thread found with id" in error_str.lower() or "not found" in error_str.lower() or "(none)" in error_str.lower() or "active" in error_str.lower():
            try:
                print("Stale or locked thread detected. Creating a new thread session...")
                new_thread_id = create_thread()
                request.session['triage_thread_id'] = new_thread_id
                
                # Retry sending the message with the new thread ID
                response_data = send_message(new_thread_id, context_msg, role="intake", user_data=user_data)
                ai_response_text = response_data.get('content', "I'm sorry, I couldn't process that.")
                run_status = response_data.get('run_status', 'failed')
                
                # We do not return an error here; we gracefully handled it.
            except Exception as retry_e:
                import logging
                logger = logging.getLogger(__name__)
                logger.exception("Failed to retry sending message to Azure Agent")
                ai_response_text = f"An error occurred connecting to the AI Agent (Retry failed): {str(retry_e)}"
                run_status = 'error'
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Error occurred connecting to the AI Agent")
            ai_response_text = f"An error occurred connecting to the AI Agent: {error_str}"
            run_status = 'error'

    # (Logic to check if agent called the `create_triage_record` tool internally 
    # would ideally belong here to formally end the chat session, but for now 
    # we just act as a pass-through proxy.)

    return JsonResponse({
        'status': 'success',
        'message': ai_response_text,
        'run_status': run_status
    })

@csrf_exempt
@require_POST
def api_chat_stream(request):
    """Receive a chat message and return a StreamingHttpResponse with SSE chunked data."""
    import asyncio
    import logging
    logger = logging.getLogger(__name__)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_message = data.get('message', '').strip()
    thread_id = data.get('thread_id')

    if not user_message or not thread_id:
        return JsonResponse({'error': 'Missing message or thread_id'}, status=400)

    role = "intake"
    session_id = None
    session = TriageSession.objects.filter(thread_id=thread_id).order_by('-created_at').first()
    if session:
        role = session.active_agent_role
        session_id = session.id

    context_msg = f"[Context: session_id={session_id}]\n{user_message}" if session_id else user_message

    from django.http import StreamingHttpResponse

    # Personalization — fetch patient data
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

    def _make_async_stream(sync_gen, sess):
        """Wrap a synchronous generator in an async generator.

        Uvicorn (ASGI) requires StreamingHttpResponse to receive an async
        iterable. Feeding it a sync generator causes the
        'must consume synchronous iterators' warning and can result in
        premature stream termination. We run each next() call in a thread
        pool via asyncio.to_thread so the event loop stays unblocked.
        """
        async def _async_gen():
            full_content = ""
            loop = asyncio.get_event_loop()
            it = iter(sync_gen)
            while True:
                try:
                    chunk = await loop.run_in_executor(None, next, it)
                except StopIteration:
                    break
                except Exception as exc:
                    logger.exception("Error reading stream chunk")
                    yield json.dumps({"type": "error", "content": str(exc)}) + "\n\n"
                    break
                # Accumulate agent text for DB logging
                try:
                    parsed = json.loads(chunk.strip())
                    if parsed.get('type') == 'chunk':
                        full_content += parsed.get('content', '')
                except Exception:
                    pass
                yield chunk

            # Persist full agent response and trigger summary if needed
            if sess and full_content:
                try:
                    ChatMessage.objects.create(session=sess, role='agent', content=full_content)
                    msg_count = ChatMessage.objects.filter(session=sess).count()
                    if msg_count > 0 and msg_count % 5 == 0:
                        import threading
                        from .services import get_project_client
                        def update_summary(session_id, tid):
                            try:
                                s = TriageSession.objects.get(id=session_id)
                                client = get_project_client()
                                summary_prompt = "Please provide a concise medical summary of the patient's symptoms and state so far, ignoring pleasantries."
                                resp = client.send_message(tid, summary_prompt, role="analysis")
                                if resp and resp.get("content"):
                                    s.ai_summary = resp["content"]
                                    s.save()
                            except Exception:
                                logging.getLogger(__name__).exception("Failed to auto-update rolling summary in stream")
                        threading.Thread(target=update_summary, args=(sess.id, thread_id), daemon=True).start()
                except Exception:
                    logger.exception("Failed to persist agent stream response")

        return _async_gen()

    # Log user message immediately
    try:
        if session:
            ChatMessage.objects.create(session=session, role='patient', content=user_message)

        generator = send_message_stream(thread_id, context_msg, role=role, user_data=user_data)
        return StreamingHttpResponse(_make_async_stream(generator, session), content_type='text/event-stream')

    except Exception as e:
        error_str = str(e)
        stale_thread = any(k in error_str.lower() for k in ["no thread found", "not found", "(none)", "active"])
        if stale_thread:
            try:
                logger.warning("Stale/locked thread detected. Creating a new thread.")
                new_thread_id = create_thread()
                request.session['triage_thread_id'] = new_thread_id
                generator = send_message_stream(new_thread_id, context_msg, role="intake", user_data=user_data)
                return StreamingHttpResponse(_make_async_stream(generator, session), content_type='text/event-stream')
            except Exception as retry_e:
                logger.exception("Failed to retry sending message stream to Azure Agent")
                async def _err():
                    yield json.dumps({"type": "error", "content": f"Retry failed: {str(retry_e)}"}) + "\n\n"
                return StreamingHttpResponse(_err(), content_type='text/event-stream')
        else:
            logger.exception("Error occurred connecting stream to the AI Agent")
            async def _err():
                yield json.dumps({"type": "error", "content": f"Error: {error_str}"}) + "\n\n"
            return StreamingHttpResponse(_err(), content_type='text/event-stream')


# ──────────────────────────────────────────────
# Doctor Command Center
# ──────────────────────────────────────────────

def doctor_dashboard(request):
    """Render the doctor command center."""
    stats = {
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
    sessions = TriageSession.objects.select_related(
        'patient', 'doctor'
    ).all()[:20]
    return render(request, 'triage/doctor_dashboard.html', {
        'stats': stats,
        'sessions': sessions,
    })


def doctor_queue_updates(request):
    """HTMX partial: refresh the priority-sorted queue."""
    sessions = TriageSession.objects.select_related(
        'patient', 'doctor'
    ).all()[:20]
    return render(request, 'triage/partials/doctor_queue_rows.html', {
        'sessions': sessions,
    })


@require_POST
def doctor_action(request, session_id):
    """Handle doctor actions: accept, escalate, request vitals."""
    session = get_object_or_404(TriageSession, id=session_id)
    action = request.POST.get('action', '')

    if action == 'accept':
        session.status = 'IN_PROGRESS'
        if hasattr(request.user, 'doctor_profile'):
            session.doctor = request.user.doctor_profile
        session.agent_logs += f"\n[Doctor] Case accepted"
        session.save()
    elif action == 'escalate':
        session.urgency_score = min(session.urgency_score + 1, 5)
        session.agent_logs += f"\n[Doctor] Case escalated to specialist"
        session.save()
    elif action == 'request_vitals':
        session.agent_logs += f"\n[Doctor] Vitals request sent to nursing station"
        session.save()
    elif action == 'complete':
        session.status = 'COMPLETED'
        session.agent_logs += f"\n[Doctor] Case marked as completed"
        session.save()

    # Return updated row
    sessions = TriageSession.objects.select_related(
        'patient', 'doctor'
    ).all()[:20]
    return render(request, 'triage/partials/doctor_queue_rows.html', {
        'sessions': sessions,
    })


# ──────────────────────────────────────────────
# REST API ViewSets
# ──────────────────────────────────────────────

@login_required
def api_chat_history(request, thread_id):
    """Fetch all previous messages for a specific thread, potentially across sessions."""
    # Query messages by thread_id through the session association
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
