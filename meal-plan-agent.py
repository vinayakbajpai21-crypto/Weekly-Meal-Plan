"""
Meal Plan Agent — Sunday Auto-Mailer (GitHub Actions version)
Reads config from environment variables (set in GitHub Secrets).

Triggered by .github/workflows/meal-plan.yml every Sunday at 2 PM IST.
"""

import anthropic
import smtplib
import json
import re
import os
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

# ── Read config from environment (set as GitHub Secrets) ──────────────────────
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY")
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL    = os.environ.get("RECIPIENT_EMAIL")

# Fail fast if any secret is missing
missing = [k for k, v in {
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    "GMAIL_ADDRESS":     GMAIL_ADDRESS,
    "GMAIL_APP_PASSWORD":GMAIL_APP_PASSWORD,
    "RECIPIENT_EMAIL":   RECIPIENT_EMAIL,
}.items() if not v]
if missing:
    print(f"ERROR: Missing GitHub Secrets: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)

# ── User preferences (edit anytime, then commit & push) ───────────────────────
PREFERENCES = """
- Mostly vegetarian: eggs daily, chicken ONLY on Thursday (ordered out, not cooked at home)
- North Indian cuisine: curries, dal, sabzi, chapati, rice
- Daily target: ~1,400 kcal, ~70g protein from meals (weight loss goal)
- Protein sources: dal, rajma, chana, paneer, eggs, tofu, soya chunks, curd
- Dairy allowed: paneer, curd, milk — all fine
- Chapati limit: 1–2 per meal
- Avoid: Karela (bitter gourd), Parval (pointed gourd)
- 3 meals per day: breakfast, lunch, dinner
"""

# ── STEP 1: Generate meal plan ────────────────────────────────────────────────
def generate_meal_plan(client):
    print("Generating weekly meal plan...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""Generate a 7-day North Indian meal plan for next week with these requirements:
{PREFERENCES}

Return ONLY valid JSON (no markdown, no backticks) with this exact structure:
{{
  "Monday": {{
    "tip": "one short daily tip",
    "meals": [
      {{"type": "breakfast", "name": "Dish Name", "desc": "brief description + portion", "kcal": 350, "pro": 20}},
      {{"type": "lunch",     "name": "Dish Name", "desc": "brief description + portion", "kcal": 560, "pro": 22}},
      {{"type": "dinner",    "name": "Dish Name", "desc": "brief description + portion", "kcal": 480, "pro": 18}}
    ]
  }},
  ... (same for Tuesday through Sunday)
}}"""
        }]
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    match = re.search(r'\{[\s\S]+\}', text)
    if not match:
        raise ValueError("Could not parse meal plan JSON from response")
    return json.loads(match.group(0))


# ── STEP 2: Find YouTube recipe for a dish ────────────────────────────────────
def find_recipe(client, dish_name):
    print(f"  Finding
