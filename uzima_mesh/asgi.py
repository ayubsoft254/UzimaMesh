import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')

# Get the standard Django ASGI application
django_asgi_app = get_asgi_application()

# IMPORTANT: Import mcp_server AFTER get_asgi_application() so Django apps are
# initialized, but BEFORE mount_mcp_server so tools are registered on mcp_app.
import mcp_server.server  # noqa: F401, E402 — registers MCP tools (side-effect import)

try:
    from django_mcp import asgi as django_mcp_asgi
    import django_mcp.asgi_patch_fastmcp as patch_module
    from starlette.responses import Response

    original_patch = patch_module.FastMCP_sse_app_patch

    def patched_FastMCP_sse_app_patch(*args, **kwargs):
        handle_sse, sse = original_patch(*args, **kwargs)

        async def wrapped_handle_sse(request):
            try:
                await handle_sse(request)
            except BaseException as e:
                if type(e).__name__ in ('ExceptionGroup', 'BaseExceptionGroup', 'EndOfStream'):
                    # Client disconnected or SSE closed prematurely
                    pass
                else:
                    raise
            return Response()  # Fix TypeError: 'NoneType' object is not callable

        return wrapped_handle_sse, sse

    django_mcp_asgi.FastMCP_sse_app_patch = patched_FastMCP_sse_app_patch
    patch_module.FastMCP_sse_app_patch = patched_FastMCP_sse_app_patch

    from django_mcp.asgi import mount_mcp_server
    # Mount the MCP server at /mcp — exposes /mcp/sse and /mcp/messages/
    application = mount_mcp_server(django_asgi_app, mcp_base_path='/mcp')
except ImportError:
    import warnings
    warnings.warn("django_mcp is not installed. MCP over SSE is disabled.")
    application = django_asgi_app
