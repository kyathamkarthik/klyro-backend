import re

def mask_pii(payload: str) -> str:
    """Scrub sensitive client data before passing to the AI."""
    
    # 1. Mask Emails
    payload = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '[REDACTED_EMAIL]', payload)
    
    # 2. Mask Credit Cards (Standard 13-16 digit formats)
    payload = re.sub(r'\b(?:\d[ -]*?){13,16}\b', '[REDACTED_CARD]', payload)
    
    # 3. Mask Passwords, Secrets, and Tokens in JSON structures
    payload = re.sub(r'(?i)("password"|"secret"|"api_key"|"token"|"client_secret")\s*:\s*"[^"]+"', 
                     r'\1: "[REDACTED_SECRET]"', payload)
    
    # 4. Mask IP Addresses
    payload = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[REDACTED_IP]', payload)
    
    return payload
