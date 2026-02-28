import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')

# Get the standard Django ASGI application
django_asgi_app = get_asgi_application()

# IMPORTANT: Import mcp_server AFTER get_asgi_application() so Django apps are
# initialized, but BEFORE mount_mcp_server so tools are registered on mcp_app.
import mcp_server.server  # noqa: F401, E402 — registers MCP tools (side-effect import)

try:
    from django_mcp.asgi import mount_mcp_server
    # Mount the MCP server at /mcp — exposes /mcp/sse and /mcp/messages/
    application = mount_mcp_server(django_asgi_app, mcp_base_path='/mcp')
except ImportError:
    import warnings
    warnings.warn("django_mcp is not installed. MCP over SSE is disabled.")
    application = django_asgi_app
