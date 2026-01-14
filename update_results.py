import requests
from extensions import db  # <- import db from extensions
from zoneinfo import ZoneInfo
from datetime import datetime
import os
from dotenv import load_dotenv
from models import Match

load_dotenv()


API_TOKEN = os.getenv("FOOTBALL_API_KEY")


def update_matches():
    leagues = ["PL"]    #Add other league codes if needed
    headers = {"X-Auth-Token": API_TOKEN}

    for league in leagues:
        url = f"https://api.football-data.org/v4/competitions/{league}/matches"
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"Error fetching {league}: {response.text}")
            continue

        matches = response.json().get("matches", [])

        for m in matches:
            match = Match.query.filter_by(
                utc_date=m["utcDate"],
                home=m["homeTeam"]["name"],
                away=m["awayTeam"]["name"]
            ).first()

            if not match:
                continue

            match.status = m["status"]

            if m["status"] == "FINISHED":
                match.home_score = m["score"]["fullTime"]["home"]
                match.away_score = m["score"]["fullTime"]["away"]

            elif m["status"] in ["LIVE", "IN_PLAY"]:
                match.home_score = m["score"]["fullTime"]["home"]
                match.away_score = m["score"]["fullTime"]["away"]

    # Save updated matches TO DB 
    db.session.commit()
    
    print("✅ Matches updated successfully!")
