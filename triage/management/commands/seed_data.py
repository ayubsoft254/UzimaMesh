from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from triage.models import Patient, Doctor, TriageSession, ChatMessage
import random


class Command(BaseCommand):
    help = 'Seed data for Uzima Mesh'

    def handle(self, *args, **kwargs):
        # Create a test user/doctor if not exists
        user, created = User.objects.get_or_create(username='dr_smith', defaults={
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'smith@uzima.com'
        })
        if created:
            user.set_password('password123')
            user.save()

        doctor, _ = Doctor.objects.get_or_create(user=user, defaults={
            'specialty': 'Cardiology',
            'bio': 'Experienced cardiologist with a focus on triage.'
        })

        # Realistic patient data with AI summaries
        patients_data = [
            {
                'first_name': 'John',
                'last_name': 'Doe',
                'email': 'john@example.com',
                'medical_history': 'High blood pressure, Type 2 Diabetes',
                'current_prescriptions': 'Lisinopril 10mg daily, Metformin 500mg twice daily',
                'symptoms': 'Sharp chest pain, radiating to left arm. Onset 2 hours ago.',
                'urgency_score': 5,
                'status': 'PENDING',
                'ai_summary': (
                    '• Symptom: Sharp chest pain radiating to left arm, onset 2h ago\n'
                    '• Vitals: Heart rate elevated (110 bpm), history of hypertension\n'
                    '• AI Recommendation: Immediate ECG required; potential cardiac event'
                ),
                'recommended_action': 'Immediate ECG and cardiology consult',
            },
            {
                'first_name': 'Jane',
                'last_name': 'Wilson',
                'email': 'jane@example.com',
                'medical_history': 'Asthma, seasonal allergies',
                'current_prescriptions': 'Albuterol inhaler PRN',
                'symptoms': 'Persistent cough for 5 days, mild fever 37.8°C, difficulty breathing.',
                'urgency_score': 4,
                'status': 'IN_PROGRESS',
                'ai_summary': (
                    '• Symptom: Persistent cough (5 days), mild fever, dyspnea\n'
                    '• History: Asthma — potential exacerbation or secondary infection\n'
                    '• AI Recommendation: Chest X-ray and spirometry; consider antibiotics'
                ),
                'recommended_action': 'Chest X-ray, assess for pneumonia',
            },
            {
                'first_name': 'Bob',
                'last_name': 'Brown',
                'email': 'bob@example.com',
                'medical_history': 'No significant history',
                'current_prescriptions': '',
                'symptoms': 'Twisted ankle playing basketball. Swelling and bruising present.',
                'urgency_score': 2,
                'status': 'PENDING',
                'ai_summary': (
                    '• Symptom: Right ankle sprain, swelling and ecchymosis present\n'
                    '• Mechanism: Sports injury — low risk for fracture\n'
                    '• AI Recommendation: X-ray to rule out fracture; RICE protocol'
                ),
                'recommended_action': 'X-ray ankle, prescribe RICE protocol',
            },
            {
                'first_name': 'Alice',
                'last_name': 'Green',
                'email': 'alice@example.com',
                'medical_history': 'Migraine history',
                'current_prescriptions': 'Sumatriptan 50mg PRN',
                'symptoms': 'Severe headache for 3 days, nausea, sensitivity to light.',
                'urgency_score': 3,
                'status': 'PENDING',
                'ai_summary': (
                    '• Symptom: Severe headache (3 days), photophobia, nausea\n'
                    '• History: Chronic migraines — current episode prolonged\n'
                    '• AI Recommendation: Neurological assessment; consider CT if no improvement'
                ),
                'recommended_action': 'Neurology consult if no relief in 24h',
            },
            {
                'first_name': 'Maria',
                'last_name': 'Santos',
                'email': 'maria@example.com',
                'medical_history': 'Pregnancy (32 weeks)',
                'current_prescriptions': 'Prenatal vitamins, Iron supplements',
                'symptoms': 'Abdominal cramping, mild spotting. No fever.',
                'urgency_score': 5,
                'status': 'PENDING',
                'ai_summary': (
                    '• Symptom: Abdominal cramping with mild vaginal spotting at 32 weeks\n'
                    '• Risk: Preterm labor indicators — immediate obstetric evaluation needed\n'
                    '• AI Recommendation: NST and transvaginal ultrasound STAT'
                ),
                'recommended_action': 'Immediate OB/GYN consult, fetal monitoring',
            },
        ]

        for data in patients_data:
            patient, _ = Patient.objects.get_or_create(
                email=data['email'],
                defaults={
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'medical_history': data['medical_history'],
                    'current_prescriptions': data.get('current_prescriptions', ''),
                }
            )

            session = TriageSession.objects.create(
                patient=patient,
                doctor=doctor if data['status'] == 'IN_PROGRESS' else None,
                symptoms=data['symptoms'],
                urgency_score=data['urgency_score'],
                status=data['status'],
                ai_summary=data['ai_summary'],
                recommended_action=data['recommended_action'],
                agent_logs=(
                    f"[Intake Agent] Session created via conversational intake\n"
                    f"[Intake Agent] Patient: {patient}\n"
                    f"[Intake Agent] Urgency score computed: {data['urgency_score']}\n"
                    f"[MCP:Azure SQL] Verified patient history — {data['medical_history']}\n"
                    f"[MCP:Azure SQL] Cross-referenced prescriptions\n"
                    f"[Intake Agent] Recommended: {data['recommended_action']}"
                ),
            )

            # Create mock chat messages
            ChatMessage.objects.create(
                session=session, role='agent',
                content="Hello, I'm your Uzima Mesh Intake Coordinator. Can you describe your symptoms?"
            )
            ChatMessage.objects.create(
                session=session, role='patient',
                content=data['symptoms']
            )
            ChatMessage.objects.create(
                session=session, role='agent',
                content="Thank you. I've completed your assessment and your case has been prioritized."
            )

        self.stdout.write(self.style.SUCCESS(
            f'Successfully seeded {len(patients_data)} patients with AI summaries and chat messages'
        ))
