import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("FIREWORKS_API_KEY")

if not API_KEY:
    exit()

print("🔍 Querying Fireworks AI for ALL accessible models...\n")

url = "https://api.fireworks.ai/inference/v1/models"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
    models = [m['id'] for m in data.get('data', [])]
    
    print(f"✅ SUCCESS! Found {len(models)} total models. Here they are:\n")
    for model in sorted(models):
        print(f"  - {model}")
else:
    print(f"❌ FAILED with status code: {response.status_code}")
    print(f"Error Details: {response.text}")