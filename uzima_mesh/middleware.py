class AllowHealthProbeMiddleware:
    """
    Azure App Service sends health probes using a link-local (169.254.x.x) IP
    as the HTTP Host header. That IP changes, so we can't hard-code it in
    ALLOWED_HOSTS. This middleware rewrites such Host headers to '127.0.0.1'
    before Django's SecurityMiddleware validates them — it must be listed
    first in MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get('HTTP_HOST', '')
        # Strip port if present
        host_only = host.split(':')[0]
        parts = host_only.split('.')
        if len(parts) == 4 and parts[0] == '169' and parts[1] == '254':
            request.META['HTTP_HOST'] = '127.0.0.1'
        return self.get_response(request)


class SessionRefreshMiddleware:
    """
    Middleware to ensure the session timeout is refreshed on every request,
    but only for authenticated users, to avoid filling the database with
    anonymous sessions.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Only modify the session to force a save if the user is authenticated
        if hasattr(request, 'user') and request.user.is_authenticated:
            request.session.modified = True
            
        return response
