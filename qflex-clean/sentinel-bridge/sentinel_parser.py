from ip_analyzer import sanitize_ip_payload
import sys

def analyze_network_traffic(raw_input: str):
    """
    Phase 1 Ingestion: Primary entry point for network traffic analysis.
    Routes through the DPI scanner before downstream processing.
    """
    print(f"[*] Ingesting raw payload: {raw_input}")
    
    dpi_result = sanitize_ip_payload(raw_input)
    
    if dpi_result["status"] == "QUARANTINE":
        print("\n[!] THREAT DETECTED [!]")
        print(f"Action: Routing to Quarantine Chamber.")
        print(f"Reason: {dpi_result['reason']}")
        print(f"Isolated Payload: {dpi_result['original_payload']}")
        return
        
    print("\n[+] Payload verified clean. Proceeding to Phase 2 (Intelligence).")

if __name__ == "__main__":
    # Allows the script to accept payloads directly from the Node.js bridge
    if len(sys.argv) > 1:
        test_payload = sys.argv[1]
    else:
        test_payload = "192.168.1.50; rm -rf /"
        
    analyze_network_traffic(test_payload)
