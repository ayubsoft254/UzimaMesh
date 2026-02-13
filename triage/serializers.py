from rest_framework import serializers
from .models import Patient, Doctor, TriageSession

class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = '__all__'

class DoctorSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = Doctor
        fields = ['id', 'user', 'user_name', 'specialty', 'is_available', 'bio']

class TriageSessionSerializer(serializers.ModelSerializer):
    patient_name = serializers.CharField(source='patient.__str__', read_only=True)
    doctor_name = serializers.CharField(source='doctor.__str__', read_only=True)

    class Meta:
        model = TriageSession
        fields = '__all__'
