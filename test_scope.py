import threading

class AzureAgentClient:
    def __init__(self):
        _token_cache = None
        _token_expires_at = 0
        _token_lock = threading.Lock()
        
        class CachedCredential:
            def get_token(self):
                global _token_cache, _token_expires_at, _token_lock
                if _token_cache:
                    return _token_cache
                with _token_lock:
                    return _token_cache
                
        self.cred = CachedCredential()

client = AzureAgentClient()
print("Initialized")
try:
    client.cred.get_token()
except Exception as e:
    print(f"Exception: {type(e).__name__} - {e}")
