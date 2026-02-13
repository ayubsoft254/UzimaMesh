from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'patients', views.PatientViewSet)
router.register(r'doctors', views.DoctorViewSet)
router.register(r'sessions', views.TriageSessionViewSet)

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/triage/updates/', views.triage_updates, name='triage_updates'),
    path('api/', include(router.urls)),
]
