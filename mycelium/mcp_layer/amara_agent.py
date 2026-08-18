import time
import json
from pathlib import Path
from datetime import datetime
import sqlite3
import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MEMORY_DB = Path("sentinel/intelligence/memory.db")

class AMARAAgent:
    def __init__(self):
        MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(MEMORY_DB)
        self.conn.execute('''CREATE TABLE IF NOT EXISTS memory 
                            (timestamp TEXT, query TEXT, response TEXT)''')
    
    def remember(self, query, response):
        self.conn.execute("INSERT INTO memory VALUES (?, ?, ?)", 
                         (datetime.now().isoformat(), query, response))
        self.conn.commit()
    
    def query(self, prompt):
        try:
            payload = {
                "model": "gemma2:9b",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }
            r = requests.post(OLLAMA_URL, json=payload, timeout=60)
            response = r.json()["message"]["content"]
            self.remember(prompt, response)
            return response
        except Exception as e:
            return f"Error: {str(e)}"

def main():
    agent = AMARAAgent()
    print("A.M.A.R.A. Local Agent Ready (with memory)")
    while True:
        query = input("\nYou: ")
        if query.lower() in ["exit", "quit"]:
            break
        response = agent.query(query)
        print(f"A.M.A.R.A.: {response}")

if __name__ == "__main__":
    main()
