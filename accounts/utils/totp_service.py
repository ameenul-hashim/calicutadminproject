import hmac
import hashlib
import time
import base64
import struct

class EnterpriseTOTPService:
    """
    Standard-compliant TOTP implementation using only Python standard libraries.
    Follows RFC 6238.
    """
    
    def __init__(self, secret_key=None):
        self.secret_key = secret_key

    def generate_secret(self):
        """Generates a base32 encoded secret key."""
        import os
        random_bytes = os.urandom(20)
        return base64.b32encode(random_bytes).decode('utf-8')

    def get_totp(self, secret, interval=30):
        """Generates a 6-digit TOTP code for the given secret."""
        # Clean secret (remove whitespace)
        secret = secret.replace(' ', '').upper()
        # Decode base32 secret
        key = base64.b32decode(secret, casefold=True)
        # Calculate time step
        msg = struct.pack(">Q", int(time.time() // interval))
        # HMAC-SHA1
        h = hmac.new(key, msg, hashlib.sha1).digest()
        # Dynamic truncation
        offset = h[-1] & 0x0F
        code = (struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF) % 1000000
        return "{:06d}".format(code)

    def verify_totp(self, secret, code, window=1):
        """
        Verifies a TOTP code with a configurable drift window.
        - window=1 allows for 30s drift before/after.
        """
        try:
            code = str(code).strip()
            # Check current and adjacent intervals
            current_time = int(time.time() // 30)
            for i in range(-window, window + 1):
                # Recalculate for each interval in window
                secret_clean = secret.replace(' ', '').upper()
                key = base64.b32decode(secret_clean, casefold=True)
                msg = struct.pack(">Q", current_time + i)
                h = hmac.new(key, msg, hashlib.sha1).digest()
                offset = h[-1] & 0x0F
                valid_code = (struct.unpack(">I", h[offset:offset+4])[0] & 0x7FFFFFFF) % 1000000
                if "{:06d}".format(valid_code) == code:
                    return True
            return False
        except Exception:
            return False

# Global service instance
totp_service = EnterpriseTOTPService()
