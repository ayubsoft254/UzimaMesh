from django.contrib import admin
from django.urls import path, include
import mcp_server.server  # Ensure MCP tools are registered

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),    
    path('', include('triage.urls')),
]
