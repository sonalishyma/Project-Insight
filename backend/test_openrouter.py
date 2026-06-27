from dotenv import load_dotenv
from openai import OpenAI
import os

load_dotenv()

print("API Key starts with:", os.getenv("OPENROUTER_API_KEY")[:12])

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

response = client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[
        {
            "role": "user",
            "content": "Say hello in one sentence."
        }
    ]
)

print(response.choices[0].message.content)