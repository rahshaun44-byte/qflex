import time
import json
import sqlite3
from pathlib import Path
from datetime import datetime
import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MEMORY_DB = Path("sentinel/intelligence/ollama_memory.db")

class OllamaAgent:
    def __init__(self):
        MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(MEMORY_DB)
        self.conn.execute('''CREATE TABLE IF NOT EXISTS conversations 
                            (timestamp TEXT, query TEXT, response TEXT)''')
    
    def chat(self, prompt):
        try:
            payload = {
                "model": "gemma3:12b",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }
            r = requests.post(OLLAMA_URL, json=payload, timeout=90)
            r.raise_for_status()
            data = r.json()
            
            # More robust parsing
            if "message" in data and "content" in data["message"]:
                response = data["message"]["content"]
            else:
                response = json.dumps(data, indent=2)  # Show full response for debugging
            
            self.conn.execute("INSERT INTO conversations VALUES (?, ?, ?)", 
                             (datetime.now().isoformat(), prompt, response))
            self.conn.commit()
            return response
        except Exception as e:
            return f"Error: {str(e)}"

def main():
    agent = OllamaAgent()
    print("Ollama Local Agent with Memory Ready (Fixed)")
    print("Type 'exit' to quit\n")
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            break
        response = agent.chat(user_input)
        print(f"Ollama: {response}\n")

if __name__ == "__main__":
    main()
