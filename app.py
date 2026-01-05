# =========================
# Standard library imports
# =========================
import os
import json
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# =========================
# Third-party libraries
# =========================
import requests
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask_migrate import Migrate

# Flask-Login
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)

# =========================
# Local application imports
# =========================
from extensions import db, migrate
from models import User, Match, Prediction



load_dotenv()  # Load environment variables from .env


app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'app.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions
db.init_app(app)
migrate.init_app(app, db)

app.secret_key = "supersecretkey"  # Change this in production

login_manager = LoginManager()
login_manager.login_view = "login"  # redirect users to this if not logged in
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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

# ---------- Authentication decorator ----------


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
            if (
                pred["home"] == actual["home_score"]
                and pred["away"] == actual["away_score"]
            ):
                total_points += 5

        leaderboard.append({
            "username": username,
            "points": total_points
        })

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

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None

    if request.method == "POST":
        username = request.form["username"].strip()
        contact = request.form["contact"].strip()
        password = request.form["password"]

        # Username uniqueness
        if User.query.filter_by(username=username).first():
            error = "Username already exists."

        else:
            # Decide email vs phone
            email = contact if "@" in contact and "." in contact else None
            phone = None if email else contact

            # Email / phone uniqueness
            if email and User.query.filter_by(email=email).first():
                error = "Email already registered."
            elif phone and User.query.filter_by(phone=phone).first():
                error = "Phone number already registered."
            else:
                hashed = generate_password_hash(password)

                user = User(
                    username=username,
                    password_hash=hashed,
                    email=email,
                    phone=phone,
                    verified=False
                )

                db.session.add(user)
                db.session.commit()

                session["otp_user"] = username
                flash("✅ Registration successful! Enter OTP to verify your account.")
                return redirect(url_for("verify_otp"))

    return render_template("register.html", error=error)

@app.route("/debug")
def debug():
    return f"Authenticated: {current_user.is_authenticated}"


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        login_id = request.form["login_id"].strip()
        password = request.form["password"]

        user = User.query.filter(
            (User.email == login_id) | (User.phone == login_id)
        ).first()

        if not user or not check_password_hash(user.password_hash, password):
            error = "Invalid email/phone or password."
        elif not user.verified:
            session["otp_user"] = user.username
            flash("⚠️ Account not verified. Enter OTP to verify.")
            return redirect(url_for("verify_otp"))
        elif not user.active:
            flash("⚠️ This account is deactivated. Reactivate first.")
            return redirect(url_for("reactivate"))
        else:
            login_user(user)
            print("LOGGED IN:", current_user.is_authenticated)
            flash(f"✅ Logged in as {user.username}")
            return redirect(url_for("index"))

    return render_template("login.html", error=error)



@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("👋 Logged out successfully")
    return redirect(url_for("login"))


@app.route("/match/<int:match_id>", methods=["GET", "POST"])
@login_required
def match(match_id):
    matches = load_matches()
    if match_id >= len(matches):
        return "Match not found", 404

    match = matches[match_id]
    predictions = load_predictions()
    username = current_user.username

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

@app.route("/profile")
@login_required
def profile():
    user = current_user  # ✅ Use Flask-Login
    
    # Get all predictions for this user
    db_predictions = Prediction.query.filter_by(user_id=user.id).all()

    today = datetime.now(timezone.utc).date()

    user_matches = []
    total_points = 0
    exact_scores = 0

    for pred in db_predictions:
        match = Match.query.get(pred.match_id)
        if not match:
            continue

        # parse match date safely
        match_date = match.utc_date.date() if match.utc_date else None

        # Only include upcoming/live/today finished matches
        if match.status != "FINISHED" or match_date == today:
            points = 0
            outcome = "UPCOMING"

            if match.status in ["IN_PLAY", "PAUSED"]:
                outcome = "LIVE"

            elif match.status == "FINISHED":
                if match.home_score is not None and match.away_score is not None:
                    if pred.pred_home == match.home_score and pred.pred_away == match.away_score:
                        points = 5
                        exact_scores += 1
                        outcome = "WIN"
                    else:
                        outcome = "LOSE"

            total_points += points

            user_matches.append({
                "home": match.home,
                "away": match.away,
                "home_logo": match.home_logo,
                "away_logo": match.away_logo,
                "pred_home": pred.pred_home,
                "pred_away": pred.pred_away,
                "home_score": match.home_score,
                "away_score": match.away_score,
                "points": points,
                "outcome": outcome
            })

    stats = {
        "total_points": total_points,
        "exact_scores": exact_scores,
        "predictions_count": len(user_matches)
    }

    return render_template(
        "profile.html",
        username=user.username,
        stats=stats,
        user_matches=user_matches
    )

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    username = current_user.username
    user = User.query.filter_by(username=username).first()

    if not user:
        flash("User not found.")
        return redirect(url_for("login"))

    # Ensure bank attribute exists (we can store as JSON or separate columns)
    if not hasattr(user, "bank") or not user.bank:
        # Using a dict attribute on user (if your model supports JSON)
        user.bank = {
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

            if not check_password_hash(user.password_hash, current_password):
                flash("❌ Current password is incorrect.")
            elif new_password != confirm_password:
                flash("❌ New password and confirmation do not match.")
            else:
                user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                flash("✅ Password updated successfully!")

        # 🏦 BANKING DETAILS UPDATE
        elif form_type == "bank":
            bank_holder = request.form.get("bank_holder", "").strip()
            bank_name = request.form.get("bank_name", "").strip()
            account_number = request.form.get("account_number", "").strip()
            branch_code = request.form.get("branch_code", "").strip()
            account_type = request.form.get("account_type", "").strip()

            if not all([bank_holder, bank_name, account_number, branch_code, account_type]):
                flash("❌ Please complete all banking details before saving.")
            else:
                # Update bank info
                user.bank = {
                    "account_holder": bank_holder,
                    "bank_name": bank_name,
                    "account_number": account_number,
                    "branch_code": branch_code,
                    "account_type": account_type
                }
                db.session.commit()
                flash("🏦 Banking details saved successfully!")

    return render_template("settings.html", user=user)

@app.route("/deactivate_account", methods=["POST"])
@login_required
def deactivate_account():
    username = current_user.username

    user = User.query.filter_by(username=username).first()

    if user:
        user.active = False
        db.session.commit()

        session.pop("username", None)
        flash("⚠️ Your account has been deactivated.")

    return redirect(url_for("login"))

@app.route("/delete_account", methods=["POST"])
@login_required
def delete_account():
    username = current_user.username

    user = User.query.filter_by(username=username).first()

    if user:
        db.session.delete(user)
        db.session.commit()

        session.pop("username", None)
        flash("🗑️ Your account has been permanently deleted.")

    return redirect(url_for("register"))

@app.route("/reactivate", methods=["GET", "POST"])
def reactivate():
    message = None

    if request.method == "POST":
        username = request.form["username"].strip()

        user = User.query.filter_by(username=username).first()

        if not user:
            message = "❌ Username not found."
        elif user.active:
            message = "ℹ️ Account is already active."
        else:
            user.active = True
            db.session.commit()

            flash("✅ Account reactivated! You can now log in.")
            return redirect(url_for("login"))

    return render_template("reactivate.html", message=message)


@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    if "otp_user" not in session:
        flash("⚠️ No user to verify. Please register or login first.")
        return redirect(url_for("register"))

    username = session["otp_user"]
    user = User.query.filter_by(username=username).first()
    if not user:
        flash("⚠️ User not found. Please register first.")
        return redirect(url_for("register"))

    error = None

    # Generate OTP if not already generated
    if username not in otp_storage:
        otp_storage[username] = str(random.randint(100000, 999999))
        print(f"Generated OTP for {username}: {otp_storage[username]}")
        # In production, send via email/SMS

    if request.method == "POST":
        entered_otp = request.form.get("otp").strip()
        correct_otp = otp_storage.get(username)

        if entered_otp == correct_otp:
            user.verified = True
            db.session.commit()  # Save changes to the database

            # Remove OTP from storage
            otp_storage.pop(username, None)
            session.pop("otp_user", None)

            # Auto-login after verification
            login_user(user)
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

        # Try to find user by email or phone
        user = User.query.filter((User.email == contact) | (User.phone == contact)).first()

        if user:
            otp = generate_otp()

            # Save OTP temporarily in memory (or you could add a reset_otp column to User if persistent)
            otp_storage[user.username] = otp
            session["reset_user"] = user.username

            # 🔥 OTP ONLY IN TERMINAL
            print(f"\n🔐 PASSWORD RESET OTP for {user.username}: {otp}\n")

            return redirect(url_for("reset_verify_otp"))

        error = "Account not found."

    return render_template("forgot_password.html", error=error)

@app.route("/reset_verify_otp", methods=["GET", "POST"])
def reset_verify_otp():
    error = None
    username = session.get("reset_user")

    if not username:
        return redirect(url_for("login"))

    # Get user from the database
    user = User.query.filter_by(username=username).first()
    if not user:
        flash("User not found. Please try again.")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        entered_otp = request.form["otp"].strip()
        correct_otp = otp_storage.get(username)  # OTP stored in memory

        if entered_otp != correct_otp:
            error = "Invalid OTP."
        else:
            # Remove OTP from storage after successful verification
            otp_storage.pop(username, None)

            session["reset_verified"] = True
            return redirect(url_for("reset_password"))

    return render_template("reset_verify_otp.html", error=error)

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if not session.get("reset_verified"):
        return redirect(url_for("login"))

    username = session.get("reset_user")
    user = User.query.filter_by(username=username).first()
    error = None

    if not user:
        flash("User not found. Please try again.")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form["password"]
        confirm = request.form["confirm"]

        if password != confirm:
            error = "Passwords do not match."
        else:
            # Update password in the database
            user.password_hash = generate_password_hash(password)
            db.session.commit()

            # Clear reset session flags
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


