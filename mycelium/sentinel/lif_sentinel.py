#!/usr/bin/env python3
"""
Quantum Flex: Leaky Integrate-and-Fire (LIF) Sentinel Node
Simulates a spiking neuron analyzing network logs, applying 
the $Y=f(x-h)+k$ bias filter logic.
"""
import sys
import math
import json
import time
import re
import urllib.request
from datetime import datetime

# SNN / LIF Threshold Parameters
V_THRESHOLD = 1500.0   # Action potential threshold
V_REST = 0.0           # Resting potential
TAU_MS = 5000.0        # Membrane decay time constant (milliseconds)
SPIKE_WEIGHT = 400.0   # Voltage added per failed login event (anomaly 'k')

class LIFNeuron:
    def __init__(self, ip):
        self.ip = ip
        self.v = V_REST
        self.last_t = None
        self.total_spikes_fired = 0

    def update(self, current_time_ms, event_is_threat):
        # Apply temporal decay (leak) if time has passed
        if self.last_t is not None:
            dt = current_time_ms - self.last_t
            if dt > 0:
                # Exponential decay formula: V(t) = V_prev * e^(-dt/tau)
                decay_factor = math.exp(-dt / TAU_MS)
                self.v = self.v * decay_factor
        
        # Integrate (accumulate charge) if event is a threat
        if event_is_threat:
            self.v += SPIKE_WEIGHT
            
        self.last_t = current_time_ms
        
        # Fire Action Potential (Spike)
        if self.v >= V_THRESHOLD:
            self.fire()
            
        return self.v

    def fire(self):
        # The neuron has crossed the threshold. Execute alert and reset.
        print(f"\n[!] ACTION POTENTIAL FIRED for IP {self.ip}! Critical Threshold ({V_THRESHOLD}) Breached.")
        print(f"[!] TRUTH VERIFICATION REQUIRED: Temporal buildup confirms malicious bias (k).")
        self.total_spikes_fired += 1
        # Reset voltage after spiking
        self.v = V_REST
        
        # Transmit payload to Athena
        payload = {
            "alert": "BRUTE_FORCE_DETECTED",
            "ip_address": self.ip,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "threshold": V_THRESHOLD
        }
        try:
            req = urllib.request.Request(
                "http://localhost:9999/athena/alert", 
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=2)
            print("[+] Successfully transmitted alert payload to Athena node.")
        except Exception as e:
            print(f"[-] Could not reach Athena node: {e}")

def tail_f(file_path):
    with open(file_path, "r") as f:
        # Move to the end of the file to simulate live tailing
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            yield line

def process_logs(log_file):
    neurons = {}
    
    print(f"--- SNN Sentinel Node Online (Live Mode) ---")
    print(f"Parameters: V_th={V_THRESHOLD}, Tau={TAU_MS}ms, SpikeWeight={SPIKE_WEIGHT}")
    print(f"Monitoring live log stream {log_file} for structural anomalies...\n")
    
    FAILED_LOGIN_RE = re.compile(r'Failed password for (?:invalid user )?\S+ from (\S+)')
    
    for line in tail_f(log_file):
        match = FAILED_LOGIN_RE.search(line)
        if match:
            ip = match.group(1)
            if ip not in neurons:
                neurons[ip] = LIFNeuron(ip)
            
            current_time_ms = time.time() * 1000.0
            v_current = neurons[ip].update(current_time_ms, True)
            print(f"[*] Threat Event (k) from {ip} | Membrane Potential: {v_current:.2f}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python lif_sentinel.py <log_file>")
        sys.exit(1)
    process_logs(sys.argv[1])
