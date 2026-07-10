import os
import requests
from dotenv import load_dotenv

# Force load the .env file
load_dotenv()

API_KEY = os.getenv("FIREWORKS_API_KEY")
URL = "https://api.fireworks.ai/inference/v1/chat/completions"

# The 2026 guaranteed active Serverless model!
MODEL_NAME = "accounts/fireworks/models/llama-v3p1-8b-instruct"

print(f"🔑 API Key loaded: {'YES' if API_KEY else 'NO (Check .env file)'}")
if not API_KEY:
    exit()

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": MODEL_NAME,
    "messages": [{"role": "user", "content": "Say hello!"}],
    "max_tokens": 15
}

print(f"🚀 Pinging Fireworks AI for model: {MODEL_NAME}...")

response = requests.post(URL, headers=headers, json=payload)

if response.status_code == 200:
    print("\n✅ SUCCESS! Your API Key is working perfectly.")
    print(f"🤖 Bot replied: {response.json()['choices'][0]['message']['content']}")
else:
    print(f"\n❌ FAILED with status code: {response.status_code}")
    print(f"Error Details: {response.text}")