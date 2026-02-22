import os
import django
from django.conf import settings
from django.apps import apps

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
    phone: str = "",
    thread_id: str = None
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
        status='PENDING',
        thread_id=thread_id
    )
    
    return {
        "status": "success",
        "session_id": session.id,
        "patient": str(patient),
        "urgency": urgency_score
    }

@mcp_app.tool()
def handoff_to_agent(session_id: int, target_role: str):
    """
    Hand off the patient to another specialized agent.
    Use this when the current agent has completed its collection or safety check.
    target_role can be: analysis, guardian, scheduler, orchestrator.
    """
    try:
        session = TriageSession.objects.get(id=session_id)
        old_role = session.active_agent_role
        session.active_agent_role = target_role
        session.agent_logs += f"\n[System] Handoff: {old_role} -> {target_role}"
        session.save()
        
        return {
            "status": "success",
            "message": f"Successfully handed off to {target_role}. The user's next message will be handled by {target_role}.",
            "handoff_signal": True,
            "target_role": target_role
        }
    except TriageSession.DoesNotExist:
        return {"status": "error", "message": f"Session {session_id} not found."}

@mcp_app.tool()
def consult_agent(thread_id: str, query: str, target_role: str):
    """
    Synchronously consult another specialized agent without handing off.
    Use this to get an expert opinion (e.g., Intake asking Analysis for urgency).
    """
    from triage.services import send_message
    
    try:
        # Prevent infinite loops by restricting consultation
        if target_role == "intake":
            return {"status": "error", "message": "Cannot consult the intake agent."}
            
        print(f"--- Consult: {target_role} with query '{query}' ---")
        # Use a fresh thread for consultation to avoid locking the main triage thread
        from triage.services import create_thread, send_message
        consult_thread_id = create_thread()
        response = send_message(consult_thread_id, query, role=target_role)
        
        return {
            "status": "success",
            "agent": target_role,
            "consultation_response": response.get("content", ""),
            "run_status": response.get("run_status")
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Standalone execution is no longer the primary way to run this,
# but we keep it for local testing if needed.
if __name__ == "__main__":
    mcp_app.run()
