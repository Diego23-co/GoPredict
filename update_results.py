import requests
import json

API_TOKEN = "6d6ce581dacf490db8f577c825c8b180"
MATCHES_FILE = "matches.json"

def update_finished_matches():
    # Fetch matches from Premier League (code: PL)
    url = "https://api.football-data.org/v4/competitions/PL/matches"

    headers = {"X-Auth-Token": API_TOKEN}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print("Error fetching data:", response.text)
        return

    data = response.json()
    matches = data["matches"]

    # Load your saved matches.json
    with open(MATCHES_FILE, "r") as f:
        saved_matches = json.load(f)

    # Update scores for finished matches
    for m in matches:
        match_id = m["id"]
        status = m["status"]

        if match_id in saved_matches and status == "FINISHED":
            saved_matches[match_id]["home_score"] = m["score"]["fullTime"]["home"]
            saved_matches[match_id]["away_score"] = m["score"]["fullTime"]["away"]

    # Save back to file
    with open(MATCHES_FILE, "w") as f:
        json.dump(saved_matches, f, indent=4)

    print("Match results updated successfully!")
