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


# ──────────────────────────────────────────────
# Patient Intake — Conversational UI
# ──────────────────────────────────────────────

def patient_intake(request):
    """Render the conversational triage intake page."""
    return render(request, 'triage/patient_intake.html')


@csrf_exempt
@require_POST
def patient_intake_submit(request):
    """Receive the completed intake data and create a TriageSession."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name_parts = data.get('name', 'Unknown').split(' ', 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ''

    symptoms = data.get('symptoms', '')
    duration = data.get('duration', '')
    severity = int(data.get('severity', 3))
    urgency_score = int(data.get('urgency_score', 1))

    # Create or find patient
    patient, _ = Patient.objects.get_or_create(
        first_name=first_name,
        last_name=last_name,
        defaults={'email': f"{first_name.lower()}.{last_name.lower()}@patient.uzima.mesh"}
    )

    # Build AI summary (mock)
    if urgency_score >= 4:
        ai_summary = (
            f"• Symptom: {symptoms}\n"
            f"• Duration: {duration}, self-reported severity {severity}/10\n"
            f"• AI Recommendation: Immediate medical attention required"
        )
        recommended_action = "Immediate review — potential acute condition"
    elif urgency_score >= 3:
        ai_summary = (
            f"• Symptom: {symptoms}\n"
            f"• Duration: {duration}, self-reported severity {severity}/10\n"
            f"• AI Recommendation: Priority consultation within 15 minutes"
        )
        recommended_action = "Urgent review — schedule priority consultation"
    else:
        ai_summary = (
            f"• Symptom: {symptoms}\n"
            f"• Duration: {duration}, self-reported severity {severity}/10\n"
            f"• AI Recommendation: Routine appointment scheduling"
        )
        recommended_action = "Routine care — schedule appointment"

    full_symptoms = f"{symptoms} (Duration: {duration}, Severity: {severity}/10)"

    session = TriageSession.objects.create(
        patient=patient,
        symptoms=full_symptoms,
        urgency_score=urgency_score,
        status='PENDING',
        ai_summary=ai_summary,
        recommended_action=recommended_action,
        agent_logs=(
            f"[Intake Agent] Session created via conversational intake\n"
            f"[Intake Agent] Patient: {patient}\n"
            f"[Intake Agent] Urgency score computed: {urgency_score}\n"
            f"[Intake Agent] Recommended: {recommended_action}"
        ),
    )

    # Save chat messages
    ChatMessage.objects.create(session=session, role='agent', content='Greeting and intake interview')
    ChatMessage.objects.create(session=session, role='patient', content=full_symptoms)

    return JsonResponse({
        'status': 'success',
        'session_id': session.id,
        'urgency_score': urgency_score,
    })


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

class PatientViewSet(viewsets.ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer


class DoctorViewSet(viewsets.ModelViewSet):
    queryset = Doctor.objects.all()
    serializer_class = DoctorSerializer


class TriageSessionViewSet(viewsets.ModelViewSet):
    queryset = TriageSession.objects.all()
    serializer_class = TriageSessionSerializer
