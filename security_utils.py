import re

def mask_pii(text: str) -> str:
    """Scrub sensitive client data before passing to the AI."""
    if not text:
        return ""
        
    # 1. Mask Emails
    text = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '[REDACTED_EMAIL]', text)
    
    # 2. Mask Credit Cards (Standard 13-16 digit formats)
    text = re.sub(r'\b(?:\d[ -]*?){13,16}\b', '[REDACTED_CARD]', text)
    
    # 3. Mask Passwords, Secrets, and Tokens in JSON structures
    text = re.sub(r'(?i)("password"|"secret"|"api_key"|"token"|"client_secret")\s*:\s*"[^"]+"', 
                     r'\1: "[REDACTED_SECRET]"', text)
    
    # 4. Mask IP Addresses
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[REDACTED_IP]', text)
    
    return text