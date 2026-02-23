from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'patients', views.PatientViewSet)
router.register(r'doctors', views.DoctorViewSet)
router.register(r'sessions', views.TriageSessionViewSet)

urlpatterns = [
    # Public Landing Page
    path('', views.landing_page, name='landing_page'),

    # Role-based Dashboard Router
    path('dashboard/', views.dashboard, name='dashboard'),

    # Patient Portal
    path('patient/', views.patient_dashboard, name='patient_dashboard'),
    path('intake/', views.patient_intake, name='patient_intake'),
    path('api/chat/', views.api_chat, name='api_chat'),
    path('api/chat/stream/', views.api_chat_stream, name='api_chat_stream'),

    # Doctor Command Center
    path('doctor/', views.doctor_dashboard, name='doctor_dashboard'),
    path('doctor/queue/', views.doctor_queue_updates, name='doctor_queue_updates'),
    path('doctor/action/<int:session_id>/', views.doctor_action, name='doctor_action'),

    # Admin Dashboard
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/mcp-info/', views.mcp_server_info, name='mcp_server_info'),

    # HTMX partials
    path('api/triage/updates/', views.triage_updates, name='triage_updates'),

    # REST API
    path('api/', include(router.urls)),
]
