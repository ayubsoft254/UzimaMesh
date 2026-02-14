from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'patients', views.PatientViewSet)
router.register(r'doctors', views.DoctorViewSet)
router.register(r'sessions', views.TriageSessionViewSet)

urlpatterns = [
    # Main dashboard (redirects to doctor view)
    path('', views.dashboard, name='dashboard'),

    # Patient Intake
    path('intake/', views.patient_intake, name='patient_intake'),
    path('intake/submit/', views.patient_intake_submit, name='patient_intake_submit'),

    # Doctor Command Center
    path('doctor/', views.doctor_dashboard, name='doctor_dashboard'),
    path('doctor/queue/', views.doctor_queue_updates, name='doctor_queue_updates'),
    path('doctor/action/<int:session_id>/', views.doctor_action, name='doctor_action'),

    # HTMX partials
    path('api/triage/updates/', views.triage_updates, name='triage_updates'),

    # REST API
    path('api/', include(router.urls)),
]
