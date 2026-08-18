import sys
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
    
    def chat_stream(self, prompt):
        full_response = ""
        print("Ollama: ", end="", flush=True)
        try:
            payload = {
                "model": "gemma3:12b",
                "messages": [{"role": "user", "content": prompt}],
                "stream": True
            }
            with requests.post(OLLAMA_URL, json=payload, stream=True) as r:
                for line in r.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        if "message" in chunk and "content" in chunk["message"]:
                            delta = chunk["message"]["content"]
                            print(delta, end="", flush=True)
                            full_response += delta
        except Exception as e:
            full_response = f"Error: {str(e)}"
            print(full_response)
        print("\n")
        self.conn.execute("INSERT INTO conversations VALUES (?, ?, ?)", 
                         (datetime.now().isoformat(), prompt, full_response))
        self.conn.commit()
        return full_response

def main():
    agent = OllamaAgent()
    print("Ollama Agent with Memory & Streaming Ready")
    print("Type 'exit' to quit\n")
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            break
        agent.chat_stream(user_input)

if __name__ == "__main__":
    main()
