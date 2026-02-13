import os
from django.core.asgi import get_asgi_application
from django_mcp.asgi import get_mcp_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')

# Get the standard Django ASGI application
django_asgi_app = get_asgi_application()

# Wrap it with django-mcp for SSE transport
application = get_mcp_asgi_application(django_asgi_app)
