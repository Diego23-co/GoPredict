# GoPredict
---

### Predict • Compete • Win 
---
## Description
---

GoPredict is a football match prediction web application built with Flask and SQLAlchemy.
Users can predict match scores, compete on daily leaderboards, and track their performance over time.

## Features
---

### User Authentication

- Register, login, logout

-Secure session handling

### Match Predictions

- Predict scores for upcoming matches

- One prediction per match per user

### Daily Limits

- Maximum of 10 predictions per day

### Live Match Protection

- Predictions automatically lock once a match goes live

### Points System

- Earn points for correct predictions

### Leaderboard

- Rank users based on total points

### Profile Dashboard

- View predictions, results, and stats

### Automated Match Updates

- Match data synced from the Football-Data API

### Responsive UI

- Clean, modern interface using HTML, CSS, and Jinja2

## 🛠 Tech Stack
---

- **Backend**: Python, Flask

- **Database**: SQLAlchemy (SQLite by default)

- **Frontend**: HTML, CSS, Jinja2

- **Authentication**: Flask-Login

- **Migrations**: Flask-Migrate

- **External API**: Football-Data.org

## Installation & Setup
---

1. Clone the repository:
```bash
git clone https://github.com/<your-username>/GoPredict.git
cd GoPredict
```

2. Create and activate a virtual environment:
```bash
    python -m venv venv
```
**Windows**
```bash
venv\Scripts\activate
```
**Linux/MacOs**
```bash
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Environment variables:
```bash
SECRET_KEY=your_secure_random_string
FOOTBALL_API_KEY=your_football_data_api_key
LOCAL_TZ=Africa/Johannesburg
```

5. Run database migrations:
```bash
flask db upgrade
```

6. Run the application:
```bash
flask run
```
Open your browser at:
http://127.0.0.1:5000

## Security Best Practice
---

- **Secrets are stored in** .env

- **Database files are not committed**

- **API keys are never pushed to GitHub**

- Uses **Flask-Login** for secure authentication

## Deployment
---

**GoPredict can be deployed on platforms such as**:

- Render

- Heroku

- Railway

- Any Linux VPS

**Steps**:

1. Set environment variables on the platform

2. Run database migrations

3. Start the app using Gunicorn

## Future Improvements
---

- Email notifications

- Multi-league support

- Match history analytics

- Social leaderboards

- Admin dashboard

## License
---

This project is open-source and free to use for educational and personal projects.

## Author
---

**GoPredict** — Built with passion for football and software engineering ⚽💻








