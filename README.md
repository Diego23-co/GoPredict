\# GoPredict ⚽



GoPredict is a football match prediction web application built with Flask.  

Users can predict daily football match scores, earn points for correct predictions, track their prediction history, and compete on a leaderboard.



---



\## 🚀 Features



\- User registration and login system

\- Daily football match predictions (maximum 10 predictions per day)

\- Automatic fetching of matches from Football-Data.org API

\- Live match score updates

\- Automatic result updates and point calculation

\- User profile with prediction history by date

\- Global leaderboard ranking users by total points

\- Secure password hashing

\- Automatic background updates using a scheduler



---



\## 🛠 Tech Stack



\### Backend

\- Python

\- Flask

\- APScheduler



\### Frontend

\- HTML

\- CSS

\- Jinja2 Templates



\### API

\- Football-Data.org API



\### Storage

\- JSON files (users, matches, predictions)



---



\## ⚙️ How It Works



1\. The app fetches daily football matches from the Football-Data.org API.

2\. Matches are stored locally in a JSON file.

3\. Users register and log in securely.

4\. Logged-in users submit score predictions for matches.

5\. Live and finished match results are automatically updated in the background.

6\. Points are awarded for correct score predictions.

7\. Users can view their performance and history on their profile page.

8\. A leaderboard ranks all users based on total points.



---



\## ▶️ Run Locally



\### 1. Clone the repository

```bash

git clone https://github.com/YOUR\_USERNAME/GoPredict.git

cd GoPredict



