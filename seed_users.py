import os
import django
from dotenv import load_dotenv

# Bootstrap Django
load_dotenv()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')
django.setup()

from django.contrib.auth.models import User
from triage.models import Patient, Doctor

def create_test_users():
    print("--- Seeding Test Users ---")
    
    # 1. Admin/Superuser
    admin_user, created = User.objects.get_or_create(
        username='admin_uzima',
        defaults={'email': 'admin@uzimamesh.com', 'is_staff': True, 'is_superuser': True}
    )
    if created:
        admin_user.set_password('uzima123')
        admin_user.save()
        print("- Admin created: admin_uzima / uzima123")
    else:
        print("- Admin already exists")

    # 2. Doctor
    doctor_user, created = User.objects.get_or_create(
        username='dr_smith',
        defaults={'email': 'smith@uzimamesh.com', 'first_name': 'John', 'last_name': 'Smith'}
    )
    if created:
        doctor_user.set_password('uzima123')
        doctor_user.save()
        print("- Doctor User created: dr_smith / uzima123")
    
    doctor_profile, created = Doctor.objects.get_or_create(
        user=doctor_user,
        defaults={'specialty': 'Cardiology', 'bio': 'Senior Cardiologist specializing in acute incidents.'}
    )
    if created:
        print("- Doctor Profile created")
    else:
        print("- Doctor Profile already exists")

    # 3. Patient
    patient_user, created = User.objects.get_or_create(
        username='patient_jane',
        defaults={'email': 'jane@patient.mesh', 'first_name': 'Jane', 'last_name': 'Doe'}
    )
    if created:
        patient_user.set_password('uzima123')
        patient_user.save()
        print("- Patient User created: patient_jane / uzima123")
    
    patient_profile, created = Patient.objects.get_or_create(
        user=patient_user,
        defaults={
            'first_name': 'Jane', 
            'last_name': 'Doe', 
            'email': 'jane@patient.mesh',
            'medical_history': 'Asthma, Type 2 Diabetes.',
            'current_prescriptions': 'Albuterol, Metformin.'
        }
    )
    if created:
        print("- Patient Profile created")
    else:
        print("- Patient Profile already exists")

if __name__ == "__main__":
    create_test_users()
