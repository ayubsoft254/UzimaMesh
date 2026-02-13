import os
import django
from fastmcp import FastMCP

# Initialize Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')
django.setup()

from triage.models import Doctor, Patient, TriageSession

# Create MCP server
mcp = FastMCP("UzimaMesh")

@mcp.tool()
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

@mcp.tool()
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

if __name__ == "__main__":
    mcp.run()
