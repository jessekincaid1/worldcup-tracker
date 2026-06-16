import anthropic
import requests
import json
import os
from datetime import datetime, timedelta, timezone


def get_games_for_date(date_str):
    """Fetch World Cup games for a specific date from ESPN's free API."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date_str}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching games for {date_str}: {e}")
        return None


def extract_game_info(data):
    """Pull clean, readable game info from the ESPN API response."""
    games = []
    if not data or "events" not in data:
        return games

    for event in data["events"]:
        game = {
            "name": event.get("name", "Unknown Match"),
            "status": event.get("status", {}).get("type", {}).get("description", ""),
            "competitions": [],
        }

        for comp in event.get("competitions", []):
            competition = {
                "venue": comp.get("venue", {}).get("fullName", "Unknown Venue"),
                "competitors": [],
            }
            for team in comp.get("competitors", []):
                competition["competitors"].append({
                    "team": team.get("team", {}).get("displayName", "Unknown"),
                    "score": team.get("score", "N/A"),
                    "winner": team.get("winner", False),
                })
            game["competitions"].append(competition)

        games.append(game)

    return games


def generate_recap(yesterday_games, today_games):
    """Use Claude to write the daily email recap."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    yesterday_str = json.dumps(yesterday_games, indent=2) if yesterday_games else "No games were played yesterday."
    today_str = json.dumps(today_games, indent=2) if today_games else "No games are scheduled for today."

    prompt = f"""You are writing a friendly morning World Cup 2026 recap email.

Yesterday's completed games:
{yesterday_str}

Today's upcoming games:
{today_str}

Write an engaging morning email with these sections:

1. A warm greeting that mentions today's date
2. "⚽ Yesterday's Results" — for each game: state the teams and final score, then write 3-5 sentences recapping the match (key moments, standout players, how the result affects standings)
3. "📅 Today's Matches" — list each upcoming game with team names and kickoff times
4. A short, enthusiastic sign-off

Keep the tone like a knowledgeable friend writing to a fellow fan. If there were no games yesterday, or none today, acknowledge that naturally."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text


def send_email(body_text):
    """Send the recap email via Resend."""
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": "World Cup Tracker <onboarding@resend.dev>",
        "to": [os.environ["TO_EMAIL"]],
        "subject": f"⚽ World Cup Daily Recap — {datetime.now().strftime('%B %d, %Y')}",
        "text": body_text,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    # GitHub Actions runs in UTC. Parker, CO is UTC-6 (MDT) in summer.
    today_utc = datetime.now(timezone.utc)
    yesterday_utc = today_utc - timedelta(days=1)

    yesterday_str = yesterday_utc.strftime("%Y%m%d")
    today_str = today_utc.strftime("%Y%m%d")

    print(f"Fetching games for yesterday ({yesterday_str}) and today ({today_str})...")

    yesterday_data = get_games_for_date(yesterday_str)
    today_data = get_games_for_date(today_str)

    yesterday_games = extract_game_info(yesterday_data)
    today_games = extract_game_info(today_data)

    print(f"Found {len(yesterday_games)} game(s) yesterday, {len(today_games)} game(s) today.")

    print("Generating recap with Claude...")
    recap = generate_recap(yesterday_games, today_games)
    print("Recap generated. Here's a preview:\n")
    print(recap[:300] + "...")

    print("\nSending email...")
    result = send_email(recap)
    print(f"✅ Email sent! ID: {result.get('id', 'unknown')}")
