# sentinel/hardening/generate_keys.py
import os
import json
import base64
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("cryptography module not found. Run: pip install cryptography")
    exit(1)

def generate_amara_keys():
    """Generates Ed25519 keys for the AMARA Data Layer."""
    print("Generating AMARA Ed25519 Cryptographic Keys...")
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    )

    keys_dir = os.path.join(os.path.dirname(__file__), 'keys')
    os.makedirs(keys_dir, exist_ok=True)
    
    priv_path = os.path.join(keys_dir, 'amara_ed25519')
    pub_path = os.path.join(keys_dir, 'amara_ed25519.pub')
    
    with open(priv_path, 'wb') as f:
        f.write(priv_bytes)
        
    with open(pub_path, 'wb') as f:
        f.write(pub_bytes)
        
    # Set secure permissions
    os.chmod(priv_path, 0o600)
    
    print(f"Keys generated securely in {keys_dir}")
    print(f"Public Key: {pub_bytes.decode('utf-8').strip()}")

if __name__ == "__main__":
    generate_amara_keys()
