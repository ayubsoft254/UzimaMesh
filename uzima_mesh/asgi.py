import os
from django.core.asgi import get_asgi_application
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')

# Get the standard Django ASGI application
django_asgi_app = get_asgi_application()

# IMPORTANT: Import mcp_server AFTER get_asgi_application() so Django apps are
# initialized, but BEFORE mount_mcp_server so tools are registered on mcp_app.
import mcp_server.server  # noqa: F401, E402 — registers MCP tools (side-effect import)

try:
    from django_mcp import asgi as django_mcp_asgi
    import django_mcp.asgi_patch_fastmcp as patch_module
    import mcp.server.sse as mcp_sse_module
    from starlette.responses import Response
    from starlette.middleware.cors import CORSMiddleware

    original_patch = patch_module.FastMCP_sse_app_patch
    original_event_source_response = mcp_sse_module.EventSourceResponse

    def event_source_response_with_ping(*args, **kwargs):
        # Ensure periodic keepalive events for strict MCP connectors.
        kwargs.setdefault(
            'ping',
            getattr(settings, 'MCP_SSE_PING_INTERVAL_SECONDS', 5),
        )
        return original_event_source_response(*args, **kwargs)

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
    mcp_sse_module.EventSourceResponse = event_source_response_with_ping

    from django_mcp.asgi import mount_mcp_server
    # Mount the MCP server at /mcp — exposes /mcp/sse and /mcp/messages/
    application = mount_mcp_server(django_asgi_app, mcp_base_path='/mcp')

    application = CORSMiddleware(
        app=application,
        allow_origins=getattr(settings, 'CORS_ALLOWED_ORIGINS', []),
        allow_origin_regex='|'.join(getattr(settings, 'CORS_ALLOWED_ORIGIN_REGEXES', [])) or None,
        allow_credentials=getattr(settings, 'CORS_ALLOW_CREDENTIALS', True),
        allow_methods=['*'],
        allow_headers=['*'],
    )
except ImportError:
    import warnings
    warnings.warn("django_mcp is not installed. MCP over SSE is disabled.")
    application = django_asgi_app
