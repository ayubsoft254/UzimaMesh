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
            
            if latest_session and latest_session.thread_id:
                thread_id = latest_session.thread_id
                # Also sync to session
                request.session['triage_thread_id'] = thread_id
    
    # 2. Fallback to Django session if not found in DB
    if not thread_id:
        thread_id = request.session.get('triage_thread_id')
    
    # 3. Create fresh thread and session if still not found
    if not thread_id:
        try:
            thread_id = create_thread()
            request.session['triage_thread_id'] = thread_id
            
            # Eagerly create a shell session if authenticated
            if request.user.is_authenticated:
                patient = getattr(request.user, 'patient_profile', None)
                if patient:
                    TriageSession.objects.create(
                        patient=patient,
                        thread_id=thread_id,
                        status='PENDING',
                        active_agent_role='intake'
                    )
        except Exception as e:
            thread_id = "local_mock_thread"

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
                    'first_name': patient.first_name,
                    'last_name': patient.last_name,
                    'email': patient.email
                }
            else:
                # Fallback to User model
                user_data = {
                    'first_name': request.user.first_name,
                    'last_name': request.user.last_name,
                    'email': request.user.email
                }
            print(f"DEBUG VIEWS: Found user_data for {request.user.username}: {user_data}")
        else:
            print("DEBUG VIEWS: User not authenticated.")
        
        response_data = send_message(thread_id, context_msg, role=role, user_data=user_data)
        ai_response_text = response_data.get('content', "I'm sorry, I couldn't process that.")
        run_status = response_data.get('run_status', 'failed')

        # 3. Log messages to database for persistence
        if session:
            ChatMessage.objects.create(session=session, sender='patient', message=user_message)
            ChatMessage.objects.create(session=session, sender='agent', message=ai_response_text)
                
        # 4. Check if the role changed during the run (via tool call)
        if session:
            session.refresh_from_db()
            new_role = session.active_agent_role
            if new_role != role:
                role = new_role
                
    except Exception as e:
        error_str = str(e)
        # Handle expired/invalid threads by automatically creating a new one
        if "no thread found with id" in error_str.lower() or "not found" in error_str.lower() or "(none)" in error_str.lower():
            try:
                print("Stale thread detected. Creating a new thread session...")
                new_thread_id = create_thread()
                request.session['triage_thread_id'] = new_thread_id
                
                # Retry sending the message with the new thread ID
                response_data = send_message(new_thread_id, context_msg, role="intake")
                ai_response_text = response_data.get('content', "I'm sorry, I couldn't process that.")
                run_status = response_data.get('run_status', 'failed')
                
                # We do not return an error here; we gracefully handled it.
            except Exception as retry_e:
                ai_response_text = f"An error occurred connecting to the AI Agent (Retry failed): {str(retry_e)}"
                run_status = 'error'
        else:
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
    
    # Strategy: Personalization - Fetch patient data
    user_data = None
    if request.user.is_authenticated:
        patient = getattr(request.user, 'patient_profile', None)
        if patient:
            user_data = {
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'email': patient.email
            }
        else:
            # Fallback to User model
            user_data = {
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
                'email': request.user.email
            }
        print(f"DEBUG VIEWS STREAM: Found user_data for {request.user.username}: {user_data}")
    else:
        print("DEBUG VIEWS STREAM: User not authenticated.")

    # Try sending message
    try:
        # Log user message immediately
        if session:
            ChatMessage.objects.create(session=session, sender='patient', message=user_message)

        generator = send_message_stream(thread_id, context_msg, role=role, user_data=user_data)
        
        # Wrap generator to log the final agent response
        def logging_generator(gen, sess):
            full_content = ""
            for chunk in gen:
                try:
                    data = json.loads(chunk.strip())
                    if data.get('type') == 'chunk':
                        full_content += data.get('content', '')
                except:
                    pass
                yield chunk
            
            if sess and full_content:
                ChatMessage.objects.create(session=sess, sender='agent', message=full_content)

        return StreamingHttpResponse(logging_generator(generator, session), content_type='text/event-stream')
    except Exception as e:
        error_str = str(e)
        if "no thread found with id" in error_str.lower() or "not found" in error_str.lower() or "(none)" in error_str.lower():
            try:
                print("Stale thread detected. Creating a new thread session...")
                new_thread_id = create_thread()
                request.session['triage_thread_id'] = new_thread_id
                
                generator = send_message_stream(new_thread_id, context_msg, role="intake")
                return StreamingHttpResponse(generator, content_type='text/event-stream')
            except Exception as retry_e:
                def err_gen():
                    yield json.dumps({"type": "error", "content": f"Retry failed: {str(retry_e)}"}) + "\n\n"
                return StreamingHttpResponse(err_gen(), content_type='text/event-stream')
        else:
            def err_gen():
                yield json.dumps({"type": "error", "content": f"Error: {error_str}"}) + "\n\n"
            return StreamingHttpResponse(err_gen(), content_type='text/event-stream')


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
    """Fetch all previous messages for a specific thread."""
    session = TriageSession.objects.filter(thread_id=thread_id).order_by('-created_at').first()
    if not session:
        return JsonResponse({'messages': []})
    
    messages = []
    for msg in session.chat_messages.all().order_by('created_at'):
        messages.append({
            'role': msg.sender,
            'content': msg.message,
            'timestamp': msg.created_at.isoformat()
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
