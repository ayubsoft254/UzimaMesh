"""
Integration layer for AI agents to interact with the MCP server.
This module provides utilities for the agent to access triage functions.
"""

import json
import logging
from typing import Optional, Dict, Any
from triage.models import TriageSession, Patient, Doctor
from django.utils import timezone

logger = logging.getLogger(__name__)


class AgentIntegration:
    """Handles agent-to-system interactions for triage."""

    @staticmethod
    def create_triage_session(
        first_name: str,
        last_name: str,
        email: str,
        phone: str,
        symptoms: str,
        urgency_score: int
    ) -> Dict[str, Any]:
        """
        Create a new triage session with patient information.
        
        Args:
            first_name: Patient's first name
            last_name: Patient's last name
            email: Patient's email address
            phone: Patient's phone number
            symptoms: Description of symptoms
            urgency_score: Urgency level (1-5)
            
        Returns:
            Dictionary with session details
        """
        try:
            # Get or create patient
            patient, created = Patient.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'phone': phone
                }
            )
            
            # Create triage session
            session = TriageSession.objects.create(
                patient=patient,
                symptoms=symptoms,
                urgency_score=urgency_score,
                status='new'
            )
            
            logger.info(f"Created triage session {session.id} for {email}")
            
            return {
                'success': True,
                'session_id': str(session.id),
                'patient_id': str(patient.id),
                'patient_name': f"{patient.first_name} {patient.last_name}",
                'urgency_score': urgency_score,
                'timestamp': session.created_at.isoformat()
            }
        except Exception as e:
            logger.error(f"Error creating triage session: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    @staticmethod
    def get_available_doctors(specialty: Optional[str] = None) -> Dict[str, Any]:
        """
        Get list of available doctors.
        
        Args:
            specialty: Optional specialty filter
            
        Returns:
            Dictionary with available doctors list
        """
        try:
            query = Doctor.objects.filter(is_available=True)
            if specialty:
                query = query.filter(specialty__icontains=specialty)
            
            doctors = []
            for doc in query:
                doctors.append({
                    'id': str(doc.id),
                    'name': f"Dr. {doc.user.last_name}",
                    'specialty': doc.specialty,
                    'bio': doc.bio or 'No bio available',
                    'available': doc.is_available
                })
            
            return {
                'success': True,
                'doctors': doctors,
                'count': len(doctors)
            }
        except Exception as e:
            logger.error(f"Error fetching doctors: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'doctors': []
            }

    @staticmethod
    def assign_doctor_to_session(session_id: str, doctor_id: str) -> Dict[str, Any]:
        """
        Assign a doctor to a triage session.
        
        Args:
            session_id: ID of the triage session
            doctor_id: ID of the doctor to assign
            
        Returns:
            Dictionary with assignment result
        """
        try:
            session = TriageSession.objects.get(id=session_id)
            doctor = Doctor.objects.get(id=doctor_id)
            
            session.assigned_doctor = doctor
            session.status = 'assigned'
            session.save()
            
            logger.info(f"Assigned doctor {doctor_id} to session {session_id}")
            
            return {
                'success': True,
                'session_id': str(session.id),
                'doctor_name': f"Dr. {doctor.user.last_name}",
                'specialty': doctor.specialty
            }
        except TriageSession.DoesNotExist:
            return {'success': False, 'error': f'Session {session_id} not found'}
        except Doctor.DoesNotExist:
            return {'success': False, 'error': f'Doctor {doctor_id} not found'}
        except Exception as e:
            logger.error(f"Error assigning doctor: {str(e)}")
            return {'success': False, 'error': str(e)}
