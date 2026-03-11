from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from triage.models import Patient, Doctor

class Command(BaseCommand):
    help = 'Seed core users and doctors for Uzima Mesh'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- Seeding Core Users ---")
        
        # 1. Create a superuser if not exists
        admin, created = User.objects.get_or_create(username='admin_uzima', defaults={
            'email': 'admin@uzimamesh.com',
            'is_staff': True,
            'is_superuser': True
        })
        if created:
            admin.set_password('uzima123')
            admin.save()
            self.stdout.write(self.style.SUCCESS('- Superuser created: admin_uzima / uzima123'))
        else:
            self.stdout.write('- Admin already exists')

        # 2. Create the first test doctor (Dr. Smith) if not exists
        user_smith, created = User.objects.get_or_create(username='dr_smith', defaults={
            'first_name': 'Alice',
            'last_name': 'Smith',
            'email': 'smith@uzima.com'
        })
        if created:
            user_smith.set_password('password123')
            user_smith.save()
            self.stdout.write(self.style.SUCCESS('- Doctor User created: dr_smith / password123'))
        else:
            self.stdout.write('- Doctor dr_smith already exists')

        doctor_smith, d_created = Doctor.objects.get_or_create(user=user_smith, defaults={
            'specialty': 'Cardiology',
            'bio': 'Experienced cardiologist with a focus on triage.'
        })
        if d_created:
            self.stdout.write(self.style.SUCCESS('- Doctor Profile for dr_smith created'))

        # 3. Create the second test doctor (Dr. Jones) if not exists
        user_jones, created = User.objects.get_or_create(username='dr_jones', defaults={
            'first_name': 'Robert',
            'last_name': 'Jones',
            'email': 'jones@uzima.com'
        })
        if created:
            user_jones.set_password('password123')
            user_jones.save()
            self.stdout.write(self.style.SUCCESS('- Doctor User created: dr_jones / password123'))
        else:
            self.stdout.write('- Doctor dr_jones already exists')

        doctor_jones, d_created = Doctor.objects.get_or_create(user=user_jones, defaults={
            'specialty': 'General Practice',
            'bio': 'General practitioner specializing in rapid medical assessment and routing.'
        })
        if d_created:
            self.stdout.write(self.style.SUCCESS('- Doctor Profile for dr_jones created'))


        # 4. Create a test patient user if not exists
        p_user, created = User.objects.get_or_create(username='patient_jane', defaults={
            'first_name': 'Jane',
            'last_name': 'Doe',
            'email': 'jane@example.com'
        })
        if created:
            p_user.set_password('uzima123')
            p_user.save()
            self.stdout.write(self.style.SUCCESS('- Patient User created: patient_jane / uzima123'))
        else:
            self.stdout.write('- Patient patient_jane already exists')

        patient_profile, p_created = Patient.objects.get_or_create(
            user=p_user,
            defaults={
                'first_name': 'Jane',
                'last_name': 'Doe',
                'email': 'jane@example.com',
                'medical_history': 'Asthma, Type 2 Diabetes',
                'current_prescriptions': 'Albuterol, Metformin'
            }
        )
        if p_created:
            self.stdout.write(self.style.SUCCESS('- Patient Profile for patient_jane created'))

        self.stdout.write(self.style.SUCCESS('Successfully seeded core data!'))
