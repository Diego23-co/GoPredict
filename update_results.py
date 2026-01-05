import requests
import json
from zoneinfo import ZoneInfo
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()


API_TOKEN = os.getenv("FOOTBALL_API_KEY")
MATCHES_FILE = "matches.json"

def update_matches():
    leagues = ["PL"]  # Add other league codes if needed
    headers = {"X-Auth-Token": API_TOKEN}

    # Load saved matches
    with open(MATCHES_FILE, "r") as f:
        saved_matches = json.load(f)

    for league in leagues:
        url = f"https://api.football-data.org/v4/competitions/{league}/matches"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Error fetching {league}: {response.text}")
            continue

        matches = response.json().get("matches", [])

        for m in matches:
            # Find the match in saved_matches by utcDate + teams
            for saved in saved_matches:
                if (saved["utcDate"] == m["utcDate"] and
                    saved["home"] == m["homeTeam"]["name"] and
                    saved["away"] == m["awayTeam"]["name"]):

                    status = m["status"]
                    saved["status"] = status

                    if status == "FINISHED":
                        saved["home_score"] = m["score"]["fullTime"]["home"]
                        saved["away_score"] = m["score"]["fullTime"]["away"]
                    elif status == "LIVE":
                        saved["home_score"] = m["score"]["live"]["home"]
                        saved["away_score"] = m["score"]["live"]["away"]

    # Save updated matches
    with open(MATCHES_FILE, "w") as f:
        json.dump(saved_matches, f, indent=4)

    print("✅ Matches updated successfully!")

# Run the update
update_matches()
