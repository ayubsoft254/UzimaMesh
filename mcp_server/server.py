import os
import django
from django.conf import settings

# Initialize Django (needed if running as a standalone script for testing, 
# but usually handled by asgi.py/wsgi.py in production)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')
if not apps.ready:
    django.setup()

from triage.models import Doctor, Patient, TriageSession
from django_mcp import mcp_app

@mcp_app.tool()
def get_doctor_availability(specialty: str = None):
    """Query available doctors, optionally filtering by specialty."""
    query = Doctor.objects.filter(is_available=True)
    if specialty:
        query = query.filter(specialty__icontains=specialty)
    
    doctors = []
    for doc in query:
        doctors.append({
            "id": doc.id,
            "name": f"Dr. {doc.user.last_name}",
            "specialty": doc.specialty,
            "bio": doc.bio
        })
    return doctors

@mcp_app.tool()
def create_triage_record(
    first_name: str, 
    last_name: str, 
    email: str, 
    symptoms: str, 
    urgency_score: int,
    phone: str = ""
):
    """Create a new patient record and a corresponding triage session."""
    patient, created = Patient.objects.get_or_create(
        email=email,
        defaults={
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone
        }
    )
    
    session = TriageSession.objects.create(
        patient=patient,
        symptoms=symptoms,
        urgency_score=urgency_score,
        status='PENDING'
    )
    
    return {
        "status": "success",
        "session_id": session.id,
        "patient": str(patient),
        "urgency": urgency_score
    }

# Standalone execution is no longer the primary way to run this,
# but we keep it for local testing if needed.
if __name__ == "__main__":
    mcp_app.run()
