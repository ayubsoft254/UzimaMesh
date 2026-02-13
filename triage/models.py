from django.db import models
from django.conf import settings
from django.contrib.auth.models import User

class Patient(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    medical_history = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class Doctor(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='doctor_profile')
    specialty = models.CharField(max_length=100)
    is_available = models.BooleanField(default=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return f"Dr. {self.user.last_name} ({self.specialty})"

class TriageSession(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='triage_sessions')
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True, related_name='triage_sessions')
    symptoms = models.TextField()
    urgency_score = models.IntegerField(choices=[(i, i) for i in range(1, 6)], default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    agent_logs = models.TextField(blank=True, help_text="Log entries for agent activity")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-urgency_score', 'created_at']

    def __str__(self):
        return f"Session: {self.patient} - {self.status}"
