import subprocess
import json
import requests

def get_recent_logs():
    try:
        # Pulling logs from the last 2 hours to ensure sufficient context
        return subprocess.check_output(["journalctl", "--since", "2 hours ago", "-n", "200", "--no-pager"], text=True)
    except Exception as e:
        return f"Log capture failed: {str(e)}"

def analyze_with_ollama(logs):
    prompt = f"""You are the Quantum Flex Sentinel. Analyze these system logs for security vulnerabilities, configuration drifts, or performance bottlenecks.
Return ONLY strict JSON. No conversational text.
Schema: {{"findings": ["list", "of", "issues"], "severity": "low|medium|high", "action": "specific_remediation_step"}}

Logs:
{logs[-2500:]}"""

    try:
        r = requests.post("http://127.0.0.1:11434/api/chat", json={
            "model": "gemma2:2b", # Using gemma2:2b for fast sensory analysis to prevent timeouts
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }, timeout=120)
        
        content = r.json()["message"]["content"]
        # Strip potential markdown fences if returned
        clean_json = content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        return {"findings": [f"Analysis Error: {str(e)}"], "severity": "high", "action": "Manual Log Review"}

if __name__ == "__main__":
    logs = get_recent_logs()
    analysis = analyze_with_ollama(logs)
    print(json.dumps(analysis, indent=2))
