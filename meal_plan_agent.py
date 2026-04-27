"""
Meal Plan Agent - Sunday Auto-Mailer (GitHub Actions version)
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

# Read config from environment (set as GitHub Secrets)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")

# Fail fast if any secret is missing
required = {
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
    "GMAIL_ADDRESS": GMAIL_ADDRESS,
    "GMAIL_APP_PASSWORD": GMAIL_APP_PASSWORD,
    "RECIPIENT_EMAIL": RECIPIENT_EMAIL,
}
missing = [k for k, v in required.items() if not v]
if missing:
    print("ERROR: Missing GitHub Secrets: " + ", ".join(missing), file=sys.stderr)
    sys.exit(1)

# User preferences (edit anytime, then commit and push)
PREFERENCES = """
- Mostly vegetarian: eggs daily, chicken ONLY on Thursday (ordered out, not cooked at home)
- North Indian cuisine: curries, dal, sabzi, chapati, rice
- Daily target: about 1,400 kcal, about 70g protein from meals (weight loss goal)
- Protein sources: dal, rajma, chana, paneer, eggs, tofu, soya chunks, curd
- Dairy allowed: paneer, curd, milk - all fine
- Chapati limit: 1-2 per meal
- Avoid: Karela (bitter gourd), Parval (pointed gourd)
- 3 meals per day: breakfast, lunch, dinner
"""


def generate_meal_plan(client):
    print("Generating weekly meal plan...")
    prompt = (
        "Generate a 7-day North Indian meal plan for next week with these requirements:\n"
        + PREFERENCES
        + "\nReturn ONLY valid JSON (no markdown, no backticks) with this exact structure:\n"
        + '{"Monday": {"tip": "one short daily tip", "meals": ['
        + '{"type": "breakfast", "name": "Dish Name", "desc": "brief description", "kcal": 350, "pro": 20},'
        + '{"type": "lunch", "name": "Dish Name", "desc": "brief description", "kcal": 560, "pro": 22},'
        + '{"type": "dinner", "name": "Dish Name", "desc": "brief description", "kcal": 480, "pro": 18}'
        + "]}, ... same for Tuesday through Sunday}"
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    match = re.search(r"\{[\s\S]+\}", text)
    if not match:
        raise ValueError("Could not parse meal plan JSON from response")
    return json.loads(match.group(0))


def find_recipe(client, dish_name):
    print("  Finding recipe for: " + dish_name)
    prompt = (
        'Search YouTube for the best recipe video for "' + dish_name + '" '
        "(North Indian home cooking style). Return ONLY the top 1 result with:\n"
        "- Video title\n- YouTube URL\n- Channel name\n"
        "- 3-sentence summary: method, key ingredients, and one tip"
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in response.content if b.type == "text")


def build_email_html(plan, recipes_by_meal, week_label):
    meal_colors = {"breakfast": "#D4AC0D", "lunch": "#2E86C1", "dinner": "#8E44AD"}
    meal_bg = {"breakfast": "#FEF9E7", "lunch": "#EBF5FB", "dinner": "#F4ECF7"}

    days_html = ""
    for day, data in plan.items():
        is_chicken = day == "Thursday"
        day_header_bg = "#F39C12" if is_chicken else "#1A5276"
        chicken_note = " (Chicken Day)" if is_chicken else ""

        meals_html = ""
        for meal in data["meals"]:
            mtype = meal["type"]
            recipe_text = recipes_by_meal.get(day + "-" + mtype, "")
            url_match = re.search(
                r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+",
                recipe_text,
            )
            yt_link = ""
            if url_match:
                yt_link = (
                    '<a href="' + url_match.group(0)
                    + '" style="color:#185FA5;">Watch on YouTube</a>'
                )
            clean_recipe = re.sub(r"https?://\S+", "", recipe_text).strip()
            recipe_block = ""
            if clean_recipe:
                truncated = clean_recipe[:300]
                if len(clean_recipe) > 300:
                    truncated += "..."
                recipe_block = (
                    '<div style="margin-top:8px;font-size:11px;color:#555;line-height:1.5">'
                    + truncated + "</div>"
                )
            link_block = ""
            if yt_link:
                link_block = '<div style="margin-top:6px">' + yt_link + "</div>"

            meals_html += (
                '<tr><td style="padding:12px 16px;background:' + meal_bg[mtype]
                + ';border-bottom:1px solid #eee;vertical-align:top">'
                + '<div style="font-size:10px;font-weight:700;text-transform:uppercase;color:'
                + meal_colors[mtype] + ';margin-bottom:4px">' + mtype + "</div>"
                + '<div style="font-size:14px;font-weight:600;color:#1C2833;margin-bottom:3px">'
                + meal["name"] + "</div>"
                + '<div style="font-size:12px;color:#666;margin-bottom:6px">'
                + meal["desc"] + "</div>"
                + '<span style="font-size:11px;padding:2px 7px;background:#FEF5E7;color:#7E5109;border-radius:10px">'
                + str(meal["kcal"]) + " kcal</span>"
                + '<span style="font-size:11px;padding:2px 7px;background:#EEEDFE;color:#4A235A;border-radius:10px;margin-left:4px">'
                + str(meal["pro"]) + "g protein</span>"
                + recipe_block + link_block
                + "</td></tr>"
            )

        days_html += (
            '<table width="100%" cellpadding="0" cellspacing="0" '
            'style="margin-bottom:20px;border-radius:8px;overflow:hidden;border:1px solid #ddd">'
            + '<tr><td style="padding:10px 16px;background:' + day_header_bg + '">'
            + '<span style="color:#fff;font-size:15px;font-weight:600">'
            + day + chicken_note + "</span>"
            + '<span style="color:rgba(255,255,255,0.75);font-size:12px;margin-left:10px">'
            + data.get("tip", "") + "</span></td></tr>"
            + meals_html
            + "</table>"
        )

    return (
        '<html><body style="margin:0;padding:0;background:#f5f5f0;font-family:Arial,sans-serif">'
        '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f0;padding:20px 0">'
        '<tr><td align="center">'
        '<table width="620" cellpadding="0" cellspacing="0" '
        'style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08)">'
        '<tr><td style="padding:28px 32px;background:#1A5276;text-align:center">'
        '<div style="font-size:22px;font-weight:700;color:#fff">Weekly Meal Plan</div>'
        '<div style="font-size:13px;color:rgba(255,255,255,0.75);margin-top:4px">'
        + week_label + "</div></td></tr>"
        '<tr><td style="padding:14px 32px;background:#EBF5FB;border-bottom:1px solid #D6EAF8">'
        '<span style="font-size:12px;color:#1A5276">Target: </span>'
        '<span style="font-size:12px;color:#555">'
        '~1,400 kcal/day | ~70g protein from meals | Weight loss plan | '
        'Chicken only Thursday (ordered)</span></td></tr>'
        '<tr><td style="padding:24px 32px">' + days_html + "</td></tr>"
        '<tr><td style="padding:16px 32px;background:#f9f9f7;border-top:1px solid #eee;text-align:center">'
        '<div style="font-size:11px;color:#999">Generated by your Meal Plan Agent - North Indian Vegetarian - Sent every Sunday at 2 PM</div>'
        "</td></tr></table></td></tr></table></body></html>"
    )


def send_email(subject, html_body):
    print("Sending email to " + RECIPIENT_EMAIL)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
    print("Email sent successfully!")


def main():
    print("=" * 50)
    print("Meal Plan Agent - " + datetime.now().strftime("%A, %d %B %Y %H:%M UTC"))
    print("=" * 50)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    today = datetime.now()
    next_mon = today + timedelta(days=(7 - today.weekday()))
    next_sun = next_mon + timedelta(days=6)
    if os.name == "nt":
        fmt = lambda d: d.strftime("%#d %b")
    else:
        fmt = lambda d: d.strftime("%-d %b")
    week_label = "Week of " + fmt(next_mon) + " - " + fmt(next_sun) + ", " + str(next_mon.year)

    plan = generate_meal_plan(client)
    print("Plan generated for " + str(len(plan)) + " days.")

    recipes_by_meal = {}
    for day, data in plan.items():
        for meal in data["meals"]:
            key = day + "-" + meal["type"]
            try:
                recipes_by_meal[key] = find_recipe(client, meal["name"])
            except Exception as e:
                print("  Could not fetch recipe for " + meal["name"] + ": " + str(e))
                recipes_by_meal[key] = ""

    html = build_email_html(plan, recipes_by_meal, week_label)
    send_email("Your Meal Plan for " + week_label, html)

    print("Done!")


if __name__ == "__main__":
    main()
