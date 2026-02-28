from django.db import models
from django.conf import settings
from django.contrib.auth.models import User


class Patient(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='patient_profile',
    )
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True, help_text="Cached email for quick access")
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    GENDER_CHOICES = (
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    medical_history = models.TextField(blank=True)
    current_prescriptions = models.TextField(
        blank=True,
        help_text="Current medications and prescriptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Doctor(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='doctor_profile',
    )
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

    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name='triage_sessions',
    )
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triage_sessions',
    )
    symptoms = models.TextField(blank=True, null=True)
    urgency_score = models.IntegerField(
        choices=[(i, i) for i in range(1, 6)],
        default=1,
        blank=True,
        null=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
    )
    ai_summary = models.TextField(
        blank=True,
        help_text="AI-generated 3-bullet CliffNotes summary",
    )
    recommended_action = models.CharField(
        max_length=255,
        blank=True,
        help_text="AI-recommended next step for the doctor",
    )
    agent_logs = models.TextField(
        blank=True,
        help_text="Log entries for agent activity",
    )
    thread_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Azure AI thread ID for persistence"
    )
    active_agent_role = models.CharField(
        max_length=50,
        default='intake',
        help_text="The role of the agent currently handling this session (e.g., intake, analysis, guardian)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-urgency_score', 'created_at']

    def __str__(self):
        return f"Session: {self.patient} - {self.status}"


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('agent', 'Agent'),
        ('patient', 'Patient'),
    ]

    session = models.ForeignKey(
        TriageSession,
        on_delete=models.CASCADE,
        related_name='chat_messages',
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.role}] {self.content[:50]}"
