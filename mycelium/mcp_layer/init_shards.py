import secrets
import random

# We use the 12th Mersenne Prime (2^127 - 1) as our finite field.
# This requires the integer representation of the secret to be < PRIME.
PRIME = 2**127 - 1

def _evaluate_polynomial(poly, x, prime):
    """
    Evaluates the polynomial at a given x coordinate, modulo the prime.
    poly: list of coefficients [a_0, a_1, ..., a_{k-1}]
    """
    accum = 0
    # Horner's method for efficient polynomial evaluation
    for coeff in reversed(poly):
        accum = (accum * x + coeff) % prime
    return accum

def generate_shares(secret_int, n, k):
    """
    Splits a secret into n shares, requiring k to reconstruct.
    Returns a list of (x, y) tuples.
    """
    if k > n:
        raise ValueError("Threshold k cannot be greater than the total number of shares n.")
    if secret_int >= PRIME:
        raise ValueError("Secret is too large for the current prime field.")

    # a_0 is the secret; the rest are securely generated random coefficients
    poly = [secret_int] + [secrets.randbelow(PRIME) for _ in range(k - 1)]
    
    # Generate n shares: evaluate the polynomial at x = 1, 2, ..., n
    shares = []
    for x in range(1, n + 1):
        y = _evaluate_polynomial(poly, x, PRIME)
        shares.append((x, y))
        
    return shares

def reconstruct_secret(shares, prime):
    """
    Reconstructs the secret from a list of k (or more) shares using Lagrange interpolation.
    shares: list of (x, y) tuples
    prime: the prime modulus used during generation
    """
    secret = 0
    
    for i in range(len(shares)):
        x_i, y_i = shares[i]
        numerator = 1
        denominator = 1
        
        for j in range(len(shares)):
            if i == j:
                continue
            
            x_j, _ = shares[j]
            
            # Compute the Lagrange basis polynomial evaluated at x = 0
            numerator = (numerator * x_j) % prime
            # Denominator calculates (x_j - x_i)
            denominator = (denominator * (x_j - x_i)) % prime
        
        # Calculate the modular inverse of the denominator
        inv_denominator = pow(denominator, -1, prime)
        
        # Multiply y_i by the Lagrange basis polynomial and add to the secret
        term = (y_i * numerator * inv_denominator) % prime
        secret = (secret + term) % prime
        
    return secret

if __name__ == "__main__":
    # Test execution for the pod
    TEST_SECRET = 8675309  
    TOTAL_SHARDS = 5
    THRESHOLD = 3
    
    print(f"[*] Initializing pod shards...")
    print(f"[*] Target Secret: {TEST_SECRET} | Shards: {TOTAL_SHARDS} | Threshold: {THRESHOLD}\n")
    
    # 1. Generate all shares
    all_shards = generate_shares(TEST_SECRET, TOTAL_SHARDS, THRESHOLD)
    for shard in all_shards:
        print(f"    -> Generated Shard {shard[0]}: {shard[1]}")
        
    # 2. Pick a random subset of exactly THRESHOLD (k) shards
    subset_shards = random.sample(all_shards, THRESHOLD)
    print(f"\n[*] Attempting reconstruction with {THRESHOLD} random shards:")
    for shard in subset_shards:
        print(f"    -> Using Shard {shard[0]}")
        
    # 3. Reconstruct the secret
    recovered_secret = reconstruct_secret(subset_shards, PRIME)
    print(f"\n[*] Recovered Secret: {recovered_secret}")
    
    if recovered_secret == TEST_SECRET:
        print("[+] SUCCESS: The shards have been accurately reassembled.")
    else:
        print("[-] FAILURE: The reconstructed secret does not match.")
