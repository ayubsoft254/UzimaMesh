import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')

# Get the standard Django ASGI application
django_asgi_app = get_asgi_application()

try:
    from django_mcp.asgi import mount_mcp_server
    # Mount the MCP server at /mcp
    application = mount_mcp_server(django_asgi_app, mcp_base_path='/mcp')
except ImportError:
    # Fallback to plain ASGI if django_mcp is not available for some reason
    import warnings
    warnings.warn("django_mcp is not installed or configured correctly. MCP over SSE is disabled.")
    application = django_asgi_app

