from flask import Flask, render_template, request, redirect, url_for, session, flash
import json
import os
import requests
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # Timezone support
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env


app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change this in production

# Temporary dictionary to store OTPs for testing
otp_storage = {}

def generate_otp():
    return str(random.randint(100000, 999999))

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
    (2015, "Ligue 1")          # France
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
    now = datetime.now(ZoneInfo(LOCAL_TZ))
    today = now.date()

    today_matches = []

    for i, match in enumerate(matches):
        match_dt = datetime.fromisoformat(
            match["utcDate"].replace("Z", "+00:00")
        ).astimezone(ZoneInfo(LOCAL_TZ))

        status = match.get("status", "TIMED")

        is_today = match_dt.date() == today
        is_live = status in ["IN_PLAY", "PAUSED"]
        is_finished = status in ["FT", "FINISHED", "AWARDED"]

        # ❌ NEVER show yesterday or finished matches
        if match_dt.date() < today or is_finished:
            continue

        # ✅ Show only today matches or live matches
        if is_today or is_live:
            match["predictions_count"] = sum(
                1 for user in predictions.values() if str(i) in user
            )
            match["localDate"] = match_dt.isoformat()
            match["global_index"] = i

            # 🔒 Lock if live
            match["locked"] = is_live

            today_matches.append(match)

    # Group by league
    leagues_dict = {}
    for match in today_matches:
        league = match.get("league_name", "Other")
        leagues_dict.setdefault(league, []).append(match)

    league_order = [
        "Premier League",
        "La Liga",
        "Serie A",
        "Bundesliga",
        "Ligue 1"
    ]

    ordered_matches = []
    for league in league_order:
        if league in leagues_dict:
            ordered_matches.extend(leagues_dict[league])

    return render_template("index.html", matches=ordered_matches)


import random
from datetime import datetime, timedelta

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        contact = request.form["contact"].strip()  # Email or phone
        password = request.form["password"]

        users = load_users()

        # Ensure username is unique
        if username in users:
            error = "Username already exists."
        else:
            hashed = generate_password_hash(password)

            # Detect email or phone number
            if "@" in contact and "." in contact:
                users[username] = {"password": hashed, "email": contact, "verified": False}
            else:
                users[username] = {"password": hashed, "phone": contact, "verified": False}

            save_users(users)

            # Store username in session temporarily for OTP verification
            session["otp_user"] = username

            flash("✅ Registration successful! Enter OTP to verify your account.")
            return redirect(url_for("verify_otp"))

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

        # Check if login_id matches email or phone
        for u, info in users.items():
            if login_id == info.get("email") or login_id == info.get("phone"):
                user = info
                username = u
                break

        if not user or not check_password_hash(user["password"], password):
            error = "Invalid email or phone number or password."
        elif not user.get("verified", False):
            # Store username temporarily to verify OTP
            session["otp_user"] = username
            flash("⚠️ Account not verified. Enter OTP to verify.")
            return redirect(url_for("verify_otp"))
        else:
            session["username"] = username
            flash(f"✅ Logged in as {username}")
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

    # 🔒 Prevent predicting live matches
    match_dt = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00")).astimezone(ZoneInfo(LOCAL_TZ))
    status = match.get("status", "UPCOMING")
    locked = status in ["IN_PLAY", "PAUSED"]

    if request.method == "POST":
        if locked:
            flash("⚠️ You cannot predict a match that is currently live.")
            return redirect(url_for("index"))

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
            if pred.get("date") == today.isoformat():
                today_predictions_count += 1
                continue
            try:
                idx = int(match_key)
                match_dt2 = datetime.fromisoformat(
                    matches[idx]["utcDate"].replace("Z", "+00:00")
                ).astimezone(ZoneInfo(LOCAL_TZ))
                if match_dt2.date() == today:
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

    return render_template("match.html", match=match, submitted=submitted, locked=locked)


@app.route("/leaderboard")
@login_required
def leaderboard():
    leaderboard_data = calculate_points()
    return render_template("leaderboard.html", leaderboard=leaderboard_data)

from datetime import datetime, timezone

@app.route("/profile")
@login_required
def profile():
    username = session["username"]
    matches = load_matches()

    # Filter out specific matches manually
    matches = [
        m for m in matches
        if not (
            (m["home"] == "Fulham FC" and m["away"] == "Nottingham Forest FC") or
            (m["home"] == "Athletic Club" and m["away"] == "RCD Espanyol de Barcelona")
        )
    ]
    
    # 🔄 FORCE score refresh BEFORE using data
    update_scores(matches)

    predictions = load_predictions()
    user_preds = predictions.get(username, {})

    today = datetime.now(timezone.utc).date()

    filtered_matches = []
    for match in matches:
        # parse match date safely
        match_date = datetime.fromisoformat(
            match["utcDate"].replace("Z", "+00:00")
        ).date()

        # keep upcoming, live, or finished today only
        if match.get("status") != "FINISHED" or match_date == today:
            filtered_matches.append(match)

    matches = filtered_matches

    total_points = 0
    exact_scores = 0
    user_matches = []

    for i, match in enumerate(matches):
        pred = user_preds.get(str(i))
        if not pred:
            continue

        status = match.get("status", "SCHEDULED")
        home_score = match.get("home_score")
        away_score = match.get("away_score")

        points = 0
        outcome = "UPCOMING"

        # 🔴 LIVE MATCH
        if status in ["IN_PLAY", "PAUSED"]:
            outcome = "LIVE"

        # ✅ FINISHED MATCH
        elif status == "FINISHED":
            if home_score is not None and away_score is not None:
                if pred["home"] == home_score and pred["away"] == away_score:
                    points = 5
                    exact_scores += 1
                    outcome = "WIN"
                else:
                    outcome = "LOSE"

        # 🕒 UPCOMING
        else:
            outcome = "UPCOMING"


        total_points += points

        user_matches.append({
            "home": match["home"],
            "away": match["away"],
            "home_logo": match.get("home_logo", "https://via.placeholder.com/64"),
            "away_logo": match.get("away_logo", "https://via.placeholder.com/64"),
            "pred_home": pred["home"],
            "pred_away": pred["away"],
            "home_score": home_score,
            "away_score": away_score,
            "points": points,
            "outcome": outcome
        })

    stats = {
        "total_points": total_points,
        "exact_scores": exact_scores,
        "predictions_count": len(user_matches)
    }

    #print(match["home"], match["away"], home_score, away_score, status)

    return render_template(
        "profile.html",
        username=username,
        stats=stats,
        user_matches=user_matches
    )

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    username = session["username"]
    users = load_users()
    user = users.get(username)

    # Ensure bank object exists
    if "bank" not in user:
        user["bank"] = {
            "account_holder": "",
            "bank_name": "",
            "account_number": "",
            "branch_code": "",
            "account_type": ""
        }

    if request.method == "POST":
        form_type = request.form.get("form_type")

        # 🔐 PASSWORD UPDATE
        if form_type == "password":
            current_password = request.form["current_password"]
            new_password = request.form["new_password"]
            confirm_password = request.form["confirm_password"]

            if not check_password_hash(user["password"], current_password):
                flash("❌ Current password is incorrect.")
            elif new_password != confirm_password:
                flash("❌ New password and confirmation do not match.")
            else:
                user["password"] = generate_password_hash(new_password)
                users[username] = user
                save_users(users)
                flash("✅ Password updated successfully!")

        # 🏦 BANKING DETAILS UPDATE
        elif form_type == "bank":
            bank_holder = request.form.get("bank_holder", "").strip()
            bank_name = request.form.get("bank_name", "").strip()
            account_number = request.form.get("account_number", "").strip()
            branch_code = request.form.get("branch_code", "").strip()
            account_type = request.form.get("account_type", "").strip()

            # Validate all fields are filled
            if not all([bank_holder, bank_name, account_number, branch_code, account_type]):
                flash("❌ Please complete all banking details before saving.")
            else:
                user["bank"]["account_holder"] = bank_holder
                user["bank"]["bank_name"] = bank_name
                user["bank"]["account_number"] = account_number
                user["bank"]["branch_code"] = branch_code
                user["bank"]["account_type"] = account_type

                users[username] = user
                save_users(users)
                flash("🏦 Banking details saved successfully!")

    return render_template("settings.html", user=user)

@app.route("/deactivate_account", methods=["POST"])
@login_required
def deactivate_account():
    username = session["username"]
    users = load_users()
    if username in users:
        users[username]["active"] = False
        save_users(users)
        session.pop("username", None)
        flash("⚠️ Your account has been deactivated.")
    return redirect(url_for("login"))

@app.route("/delete_account", methods=["POST"])
@login_required
def delete_account():
    username = session["username"]
    users = load_users()
    if username in users:
        users.pop(username)
        save_users(users)
        session.pop("username", None)
        flash("🗑️ Your account has been permanently deleted.")
    return redirect(url_for("register"))


@app.route("/reactivate", methods=["GET", "POST"])
def reactivate():
    message = None
    if request.method == "POST":
        username = request.form["username"].strip()
        users = load_users()
        user = users.get(username)

        if not user:
            message = "❌ Username not found."
        elif user.get("active", True):
            message = "ℹ️ Account is already active."
        else:
            user["active"] = True
            save_users(users)
            flash("✅ Account reactivated! You can now log in.")
            return redirect(url_for("login"))

    return render_template("reactivate.html", message=message)

@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    if "otp_user" not in session:
        flash("⚠️ No user to verify. Please register or login first.")
        return redirect(url_for("register"))

    username = session["otp_user"]
    users = load_users()
    user = users.get(username)
    error = None

    # Generate OTP if not already generated
    if username not in otp_storage:
        otp_storage[username] = str(random.randint(100000, 999999))
        print(f"Generated OTP for {username}: {otp_storage[username]}")
        # In real production, send via email/SMS
        # For testing, we just print it in the console

    if request.method == "POST":
        entered_otp = request.form.get("otp").strip()
        correct_otp = otp_storage.get(username)

        if entered_otp == correct_otp:
            user["verified"] = True
            users[username] = user
            save_users(users)

            # Remove OTP from storage
            otp_storage.pop(username, None)
            session.pop("otp_user", None)

            # Auto-login after verification
            session["username"] = username
            flash("✅ Account verified successfully! Logged in.")
            return redirect(url_for("index"))
        else:
            error = "❌ Incorrect OTP. Please try again."

    return render_template("verify_otp.html", error=error)

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    error = None

    if request.method == "POST":
        contact = request.form["contact"].strip()
        users = load_users()

        for username, info in users.items():
            if contact == info.get("email") or contact == info.get("phone"):
                otp = generate_otp()

                # Save OTP temporarily
                info["reset_otp"] = otp
                users[username] = info
                save_users(users)

                session["reset_user"] = username

                # 🔥 OTP ONLY IN TERMINAL
                print(f"\n🔐 PASSWORD RESET OTP for {username}: {otp}\n")

                return redirect(url_for("reset_verify_otp"))

        error = "Account not found."

    return render_template("forgot_password.html", error=error)

@app.route("/reset_verify_otp", methods=["GET", "POST"])
def reset_verify_otp():
    error = None
    username = session.get("reset_user")

    if not username:
        return redirect(url_for("login"))

    users = load_users()
    user = users.get(username)

    if request.method == "POST":
        entered_otp = request.form["otp"].strip()

        if entered_otp != user.get("reset_otp"):
            error = "Invalid OTP."
        else:
            user.pop("reset_otp", None)
            users[username] = user
            save_users(users)

            session["reset_verified"] = True
            return redirect(url_for("reset_password"))

    return render_template("reset_verify_otp.html", error=error)

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if not session.get("reset_verified"):
        return redirect(url_for("login"))

    username = session.get("reset_user")
    users = load_users()
    user = users.get(username)
    error = None

    if request.method == "POST":
        password = request.form["password"]
        confirm = request.form["confirm"]

        if password != confirm:
            error = "Passwords do not match."
        else:
            user["password"] = generate_password_hash(password)
            user.pop("reset_otp", None)

            users[username] = user
            save_users(users)

            session.pop("reset_user", None)
            session.pop("reset_verified", None)

            flash("✅ Password reset successful. You can log in now.")
            return redirect(url_for("login"))

    return render_template("reset_password.html", error=error)


# ---------- Fetch matches ----------
API_TOKEN = os.getenv("FOOTBALL_API_KEY")

def fetch_matches():
    headers = {"X-Auth-Token": API_TOKEN}
    today = datetime.now(ZoneInfo(LOCAL_TZ)).date()

    # Load existing matches
    if os.path.exists(MATCHES_FILE):
        with open(MATCHES_FILE, "r") as f:
            all_matches = json.load(f)
    else:
        all_matches = []

    existing_keys = {(m["home"], m["away"], m["utcDate"]) for m in all_matches}

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

            # Only today’s matches
            if match_date == today:
                home_team = match["homeTeam"]
                away_team = match["awayTeam"]

                key = (home_team["name"], away_team["name"], match["utcDate"])
                if key in existing_keys:
                    continue  # Skip if already in matches.json

                all_matches.append({
                    "home": home_team["name"],
                    "away": away_team["name"],
                    "utcDate": match["utcDate"],
                    "home_score": None,
                    "away_score": None,
                    "status": "UPCOMING",
                    "localDate": match_dt.isoformat(),
                    "home_logo": home_team.get("crest", "https://via.placeholder.com/64"),
                    "away_logo": away_team.get("crest", "https://via.placeholder.com/64"),
                    "league_name": league_name
                })

    with open(MATCHES_FILE, "w") as f:
        json.dump(all_matches, f, indent=4)
    print(f"✅ Matches fetched and updated: {len(all_matches)}")
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

def save_matches(matches):
    with open(MATCHES_FILE, "w") as f:
        json.dump(matches, f, indent=4)

def update_scores(matches):
    headers = {"X-Auth-Token": API_TOKEN}
    print("🔄 Updating all live & finished scores...")

    url = "https://api.football-data.org/v4/matches"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"⚠️ Failed to fetch matches: {response.status_code}")
        return

    data = response.json().get("matches", [])

    for match in matches:
        match_dt = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
        api_match = None

        # Find API match by home/away teams and date (ignore exact time)
        for m in data:
            api_dt = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
            if (
                m["homeTeam"]["name"].strip() == match["home"].strip()
                and m["awayTeam"]["name"].strip() == match["away"].strip()
                and api_dt.date() == match_dt.date()
            ):
                api_match = m
                break

        if not api_match:
            continue

        status = api_match.get("status", "UPCOMING")
        match["status"] = status
        score = api_match.get("score", {})

        if status in ["IN_PLAY", "PAUSED"]:
            rt = score.get("regularTime", {})
            match["home_score"] = rt.get("home")
            match["away_score"] = rt.get("away")
        elif status == "FINISHED":
            ft = score.get("fullTime", {})
            match["home_score"] = ft.get("home")
            match["away_score"] = ft.get("away")
        else:  # UPCOMING
            match["home_score"] = None
            match["away_score"] = None

        print(f"✅ {match['home']} vs {match['away']} → {status}, "
              f"scores: {match['home_score']}-{match['away_score']}")

    save_matches(matches)


def update_live_scores(matches):
    headers = {"X-Auth-Token": API_TOKEN}
    print("🔄 Updating live & finished scores...")

    url = "https://api.football-data.org/v4/matches"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"⚠️ Failed to fetch matches: {response.status_code}")
        return

    api_matches = response.json().get("matches", [])

    for match in matches:
        match_dt = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
        api_match = None

        # Match by teams and date
        for m in api_matches:
            api_dt = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
            if (
                m["homeTeam"]["name"].strip() == match["home"].strip()
                and m["awayTeam"]["name"].strip() == match["away"].strip()
                and api_dt.date() == match_dt.date()
            ):
                api_match = m
                break

        if not api_match:
            continue

        status = api_match.get("status", "UPCOMING")
        match["status"] = status
        score = api_match.get("score", {})

        if status in ["IN_PLAY", "PAUSED"]:
            rt = score.get("regularTime", {})
            match["home_score"] = rt.get("home")
            match["away_score"] = rt.get("away")
        elif status == "FINISHED":
            ft = score.get("fullTime", {})
            match["home_score"] = ft.get("home")
            match["away_score"] = ft.get("away")
        else:  # UPCOMING
            match["home_score"] = None
            match["away_score"] = None

        print(f"✅ {match['home']} vs {match['away']} → {status}, "
              f"scores: {match.get('home_score')}-{match.get('away_score')}")

    save_matches(matches)


# ---------- Auto-reset leaderboard ----------
def reset_leaderboard():
    save_predictions({})
    print("🔄 Leaderboard has been reset automatically.")

# ---------- Scheduler ----------
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: update_scores(load_matches()), 'interval', minutes=5)
scheduler.add_job(fetch_matches, 'interval', minutes=10)         # fetch new today matches every 10 min
scheduler.add_job(reset_leaderboard, 'cron', day_of_week='mon', hour=0)
scheduler.start()

# ---------- Fetch today matches immediately at startup ----------
fetch_matches()  # ensures homepage has data on app start


# ---------- Run ----------
if __name__ == "__main__":
    app.run(debug=True)


