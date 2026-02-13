from django.shortcuts import render
from django.http import HttpResponse
from rest_framework import viewsets, permissions
from .models import Patient, Doctor, TriageSession
from .serializers import PatientSerializer, DoctorSerializer, TriageSessionSerializer

def dashboard(request):
    # Get stats for dashboard
    stats = {
        'active_sessions': TriageSession.objects.filter(status='IN_PROGRESS').count(),
        'critical_cases': TriageSession.objects.filter(urgency_score=5, status__in=['PENDING', 'IN_PROGRESS']).count(),
        'avg_wait_time': 15,  # Placeholder
    }
    sessions = TriageSession.objects.all()[:10]
    return render(request, 'triage/dashboard.html', {'stats': stats, 'sessions': sessions})

def triage_updates(request):
    # Partial update for HTMX - render only rows
    sessions = TriageSession.objects.all()[:10]
    return render(request, 'triage/partials/triage_rows.html', {'sessions': sessions})

class PatientViewSet(viewsets.ModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer

class DoctorViewSet(viewsets.ModelViewSet):
    queryset = Doctor.objects.all()
    serializer_class = DoctorSerializer

class TriageSessionViewSet(viewsets.ModelViewSet):
    queryset = TriageSession.objects.all()
    serializer_class = TriageSessionSerializer
