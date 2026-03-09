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
