import requests
import json
import os
from datetime import datetime

# Replace with your actual Perplexity API key
API_KEY = 'your_api_key_here'

PROMPT = f"""Give me a structured, short summary for a weekly market update in 5 sections:
1. Market Update
2. Current Developments
3. Market Reactions
4. Portfolio Strategy
5. Looking Ahead

Today is {datetime.today().strftime('%B %d, %Y')}.
Write each section with a short title and 1-2 sentence comment, suitable for a financial blog.
Return the result as JSON like:
{{"updates": [{{"title": "...", "content": "..."}}]}}.
"""

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}

data = {
    "model": "pplx-7b-chat",
    "messages": [
        {"role": "user", "content": PROMPT}
    ]
}

def backup_existing_file():
    if os.path.exists("market-updates.json"):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"backups/market-updates-{timestamp}.json"
        os.makedirs("backups", exist_ok=True)
        os.rename("market-updates.json", backup_filename)
        print(f"Backed up previous update to {backup_filename}")

response = requests.post('https://api.perplexity.ai/chat/completions', headers=headers, json=data)

if response.ok:
    try:
        output = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(output)

        backup_existing_file()

        with open("market-updates.json", "w") as f:
            json.dump(parsed, f, indent=2)
        print("Market updates saved to market-updates.json")
    except Exception as e:
        print("Error parsing response or saving file:", e)
else:
    print("API call failed:", response.text)
