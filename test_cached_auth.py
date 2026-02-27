import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'uzima_mesh.settings')
django.setup()

from triage.services import CachedCredential

print("Testing CachedCredential directly...")
try:
    cred = CachedCredential()
    
    print("Fetching token 1...")
    token1 = cred.get_token("https://cognitiveservices.azure.com/.default")
    print(f"Token 1 fetched! Expires: {token1.expires_on}")
    
    print("Fetching token 2 (should be cached)...")
    token2 = cred.get_token("https://cognitiveservices.azure.com/.default")
    print(f"Token 2 fetched! Expires: {token2.expires_on}")
    
    if token1.token == token2.token:
        print("SUCCESS! Tokens match, meaning cache worked and no NameError was raised.")
    else:
        print("Tokens don't match or something went wrong.")
        
except Exception as e:
    import traceback
    traceback.print_exc()
