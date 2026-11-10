"""Quick check that the Gemini API key in .env works.

Run:  python check_setup.py
It sends one tiny request and lists the models your key can use.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parent / ".env")

api_key = os.getenv("GEMINI_API_KEY", "")
model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

if not api_key or api_key == "your_api_key_here":
    sys.exit("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")

client = genai.Client(api_key=api_key)

try:
    reply = client.models.generate_content(model=model, contents="Reply with the single word: ready")
    print(f"OK - model '{model}' answered: {reply.text.strip()}")
except Exception as error:  # show the reason instead of a long traceback
    print(f"The model '{model}' could not be used: {error}")
    print("\nModels available to your key (set one as GEMINI_MODEL in .env):")
    for available in client.models.list():
        if "flash" in available.name:
            print("  ", available.name.replace("models/", ""))
