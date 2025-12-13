from flask import Flask, render_template, request, redirect, url_for, session, flash
import json
import os
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # Timezone support
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change this in production

# ---------- File paths ----------
MATCHES_FILE = "matches.json"
PREDICTIONS_FILE = "predictions.json"
USERS_FILE = "users.json"

# ---------- Leagues to fetch ----------
# (league_id, league_name)
LEAGUES = [
    (2021, "Premier League"),   # English Premier League
    (2014, "La Liga"),          # Spain
    (2019, "Serie A"),          # Italy
    (2002, "Bundesliga"),       # Germany
    (2015, "Ligue 1")           # France
]

# ---------- Local timezone ----------
LOCAL_TZ = "Africa/Johannesburg"

# ---------- Helper functions ----------
def load_matches():
    if os.path.exists(MATCHES_FILE):
        with open(MATCHES_FILE, "r") as f:
            return json.load(f)
    return []

def load_predictions():
    if os.path.exists(PREDICTIONS_FILE):
        with open(PREDICTIONS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_predictions(predictions):
    with open(PREDICTIONS_FILE, "w") as f:
        json.dump(predictions, f, indent=4)

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

# ---------- Authentication decorator ----------
def login_required(func):
    from functools import wraps
    @wraps(func)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            flash("🔒 You need to login first!")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapped

# ---------- Calculate points ----------
def calculate_points():
    matches = load_matches()
    predictions = load_predictions()
    leaderboard = []

    for username, user_preds in predictions.items():
        total_points = 0
        for match_id_str, pred in user_preds.items():
            match_id = int(match_id_str)
            if match_id >= len(matches):
                continue
            actual = matches[match_id]
            if actual["home_score"] is None or actual["away_score"] is None:
                continue

            # Exact score = 5 points
            if pred["home"] == actual["home_score"] and pred["away"] == actual["away_score"]:
                total_points += 5

        badge = "🏆" if total_points >= 1000 else ""
        leaderboard.append({"username": username, "points": total_points, "badge": badge})

    leaderboard.sort(key=lambda x: x["points"], reverse=True)
    return leaderboard

# ---------- Routes ----------
@app.route("/")
def index():
    matches = load_matches()
    predictions = load_predictions()
    today = datetime.now(ZoneInfo(LOCAL_TZ)).date()

    # Keep only today's matches
    today_matches = []
    for i, match in enumerate(matches):
        match_dt = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00")).astimezone(ZoneInfo(LOCAL_TZ))
        if match_dt.date() == today:
            match["predictions_count"] = sum(1 for user in predictions.values() if str(i) in user)
            match["localDate"] = match_dt.isoformat()
            match["global_index"] = i  # <-- Add global index
            today_matches.append(match)

    # Group matches by league
    leagues_dict = {}
    for match in today_matches:
        league_name = match.get("league_name", "Other")
        if league_name not in leagues_dict:
            leagues_dict[league_name] = []
        leagues_dict[league_name].append(match)

    # Sort leagues according to desired order
    league_order = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"]
    ordered_matches = []
    for league in league_order:
        if league in leagues_dict:
            ordered_matches.extend(leagues_dict[league])

    return render_template("index.html", matches=ordered_matches)

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        users = load_users()
        if username in users:
            error = "Username already exists."
        else:
            hashed = generate_password_hash(password)
            users[username] = {"password": hashed, "email": email}
            save_users(users)
            session["username"] = username
            flash("✅ Registration successful! Logged in as " + username)
            return redirect(url_for("index"))

    return render_template("register.html", error=error)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        login_id = request.form["login_id"].strip()
        password = request.form["password"]

        users = load_users()
        user = None
        username = None
        for u, info in users.items():
            if login_id == u or login_id == info.get("email"):
                user = info
                username = u
                break

        if not user or not check_password_hash(user["password"], password):
            error = "Invalid username/email or password."
        else:
            session["username"] = username
            flash("✅ Logged in as " + username)
            return redirect(url_for("index"))

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    username = session.pop("username", None)
    if username:
        flash(f"👋 Logged out {username}")
    return redirect(url_for("login"))

@app.route("/match/<int:match_id>", methods=["GET", "POST"])
@login_required
def match(match_id):
    matches = load_matches()
    if match_id >= len(matches):
        return "Match not found", 404

    match = matches[match_id]
    predictions = load_predictions()
    username = session["username"]

    submitted = str(match_id) in predictions.get(username, {})

    if request.method == "POST":
        if submitted:
            flash("⚠️ You already submitted a prediction for this match.")
            return redirect(url_for("match", match_id=match_id))

        today = datetime.now(ZoneInfo(LOCAL_TZ)).date()

        # Ensure user predictions dict exists
        if username not in predictions:
            predictions[username] = {}

        # Count today's predictions
        today_predictions_count = 0
        for match_key, pred in predictions[username].items():

            # New predictions (with stored date)
            if pred.get("date") == today.isoformat():
                today_predictions_count += 1
                continue

            # Backward compatibility (old predictions)
            try:
                idx = int(match_key)
                match_dt = datetime.fromisoformat(
                    matches[idx]["utcDate"].replace("Z", "+00:00")
                ).astimezone(ZoneInfo(LOCAL_TZ))

                if match_dt.date() == today:
                    today_predictions_count += 1
            except:
                pass

        if today_predictions_count >= 10:
            flash("🚫 You can only predict 10 matches per day.")
            return redirect(url_for("index"))

        home_score = int(request.form["home_score"])
        away_score = int(request.form["away_score"])

        predictions[username][str(match_id)] = {
            "home": home_score,
            "away": away_score,
            "date": today.isoformat()
        }

        save_predictions(predictions)
        flash("✅ Prediction submitted successfully!")
        return redirect(url_for("index"))

    return render_template("match.html", match=match, submitted=submitted)



@app.route("/leaderboard")
@login_required
def leaderboard():
    leaderboard_data = calculate_points()
    return render_template("leaderboard.html", leaderboard=leaderboard_data)

@app.route("/profile")
@login_required
def profile():
    username = session["username"]
    matches = load_matches()
    predictions = load_predictions()
    user_preds = predictions.get(username, {})

    total_points = 0
    exact_scores = 0
    user_matches = []

    for i, match in enumerate(matches):
        pred = user_preds.get(str(i))
        if pred:
            points = 0
            outcome = "UPCOMING"  # default
            if match.get("home_score") is not None and match.get("away_score") is not None:
                if pred["home"] == match["home_score"] and pred["away"] == match["away_score"]:
                    points = 5
                    outcome = "WIN"
                else:
                    outcome = "LOSE"
            elif match.get("status") == "LIVE":
                outcome = "LIVE"

            total_points += points

            user_matches.append({
                "home": match["home"],
                "away": match["away"],
                "home_logo": match.get("home_logo", "https://via.placeholder.com/64"),
                "away_logo": match.get("away_logo", "https://via.placeholder.com/64"),
                "pred_home": pred["home"],
                "pred_away": pred["away"],
                "home_score": match.get("home_score"),
                "away_score": match.get("away_score"),
                "points": points,
                "outcome": outcome
            })



    stats = {
        "total_points": total_points,
        "exact_scores": exact_scores,
        "predictions_count": len(user_matches)
    }

    return render_template("profile.html", username=username, stats=stats, user_matches=user_matches)

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    username = session["username"]
    users = load_users()
    user = users.get(username)
    message = None

    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if not check_password_hash(user["password"], current_password):
            message = "❌ Current password is incorrect."
        elif new_password != confirm_password:
            message = "❌ New password and confirmation do not match."
        else:
            user["password"] = generate_password_hash(new_password)
            users[username] = user
            save_users(users)
            message = "✅ Password updated successfully!"

    return render_template("settings.html", username=username, message=message)

# ---------- Fetch matches ----------
API_TOKEN = "6d6ce581dacf490db8f577c825c8b180"

def fetch_matches():
    all_matches = []
    headers = {"X-Auth-Token": API_TOKEN}
    today = datetime.now(ZoneInfo(LOCAL_TZ)).date()

    for league_id, league_name in LEAGUES:
        url = f"https://api.football-data.org/v4/competitions/{league_id}/matches?status=SCHEDULED"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Error fetching league {league_name}: {response.status_code}")
            continue

        data = response.json()
        for match in data.get("matches", []):
            match_dt = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00")).astimezone(ZoneInfo(LOCAL_TZ))
            match_date = match_dt.date()
            if match_date == today: 
                home_team = match["homeTeam"]
                away_team = match["awayTeam"]
                all_matches.append({
                    "home": home_team["name"],
                    "away": away_team["name"],
                    "utcDate": match["utcDate"],
                    "home_score": None,
                    "away_score": None,
                    "localDate": match_dt.isoformat(),
                    "home_logo": home_team.get("crest", "https://via.placeholder.com/64"),
                    "away_logo": away_team.get("crest", "https://via.placeholder.com/64"),
                    "league_name": league_name
                })

    with open(MATCHES_FILE, "w") as f:
        json.dump(all_matches, f, indent=4)
    print(f"{len(all_matches)} upcoming matches saved to {MATCHES_FILE}")
    return all_matches

# ---------- Auto-update matches ----------
def update_match_results():
    matches = load_matches()
    headers = {"X-Auth-Token": API_TOKEN}

    for league_id, _ in LEAGUES:
        # Fetch finished matches
        url_finished = f"https://api.football-data.org/v4/competitions/{league_id}/matches?status=FINISHED"
        response = requests.get(url_finished, headers=headers)
        if response.status_code == 200:
            data = response.json()
            for match_data in data.get("matches", []):
                utc_date = match_data["utcDate"]
                for match in matches:
                    if match["utcDate"] == utc_date:
                        match["home_score"] = match_data["score"]["fullTime"]["home"]
                        match["away_score"] = match_data["score"]["fullTime"]["away"]
                        match["outcome"] = "WIN" if match.get("pred_home") == match["home_score"] and match.get("pred_away") == match["away_score"] else "LOSE"

        # Fetch live matches
        url_live = f"https://api.football-data.org/v4/competitions/{league_id}/matches?status=LIVE"
        response = requests.get(url_live, headers=headers)
        if response.status_code == 200:
            data = response.json()
            for match_data in data.get("matches", []):
                utc_date = match_data["utcDate"]
                for match in matches:
                    if match["utcDate"] == utc_date:
                        match["home_score"] = match_data["score"]["live"]["home"]
                        match["away_score"] = match_data["score"]["live"]["away"]
                        match["outcome"] = "LIVE"

    with open(MATCHES_FILE, "w") as f:
        json.dump(matches, f, indent=4)

    print("✅ Match results updated automatically (including live matches).")

# ---------- Auto-reset leaderboard ----------
def reset_leaderboard():
    save_predictions({})
    print("🔄 Leaderboard has been reset automatically.")

# ---------- Scheduler ----------
scheduler = BackgroundScheduler()
scheduler.add_job(update_match_results, 'interval', minutes=5)
scheduler.add_job(reset_leaderboard, 'cron', day_of_week='mon', hour=0)
scheduler.start()

# ---------- Run ----------
if __name__ == "__main__":
    fetch_matches()
    app.run(debug=True)
