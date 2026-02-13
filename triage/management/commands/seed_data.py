from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from triage.models import Patient, Doctor, TriageSession
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

        # Create some patients
        patients_data = [
            ('John', 'Doe', 'john@example.com', 'High blood pressure'),
            ('Jane', 'Wilson', 'jane@example.com', 'Chest pain'),
            ('Bob', 'Brown', 'bob@example.com', 'Sprained ankle'),
            ('Alice', 'Green', 'alice@example.com', 'Fever and cough'),
        ]

        for first_name, last_name, email, medical_history in patients_data:
            patient, _ = Patient.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'medical_history': medical_history
                }
            )

            # Create sessions
            status_list = ['PENDING', 'IN_PROGRESS', 'COMPLETED']
            TriageSession.objects.create(
                patient=patient,
                doctor=doctor if random.random() > 0.5 else None,
                symptoms=f"Patient reports {medical_history.lower()}.",
                urgency_score=random.randint(1, 5),
                status=random.choice(status_list)
            )

        self.stdout.write(self.style.SUCCESS('Successfully seeded data'))
