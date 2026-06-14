from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq
import sqlite3
import json
import os

if os.path.exists(".env"):
    from dotenv import load_dotenv
    load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "mindease-secret-key-2024")

# ── Groq Client ────────────────────────────────────────
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Flask-Login Setup ──────────────────────────────────
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"

# ── System Prompt ──────────────────────────────────────
SYSTEM_PROMPT = """You are a compassionate and supportive mental health chatbot called MindEase. 
Your role is to provide emotional support, active listening, and gentle guidance to users who may be 
experiencing stress, anxiety, sadness, or other emotional difficulties.

Guidelines:
- Always respond with empathy, warmth, and without judgment
- Ask thoughtful follow-up questions to help users explore their feelings
- Suggest healthy coping strategies when appropriate (deep breathing, journaling, exercise, talking to someone)
- Never diagnose or prescribe medication
- Keep responses concise — 2 to 4 sentences usually works best
- If a user seems to be in serious distress, gently encourage them to seek professional help
- You are not a replacement for professional mental health care — remind users of this if relevant

Remember: You are here to listen and support, not to solve or fix."""

CRISIS_KEYWORDS = [
    "suicide", "kill myself", "end my life", "want to die",
    "self harm", "self-harm", "cut myself", "hurt myself",
    "don't want to live", "no reason to live"
]

# ── Database Setup ─────────────────────────────────────
def get_db():
    db = sqlite3.connect("mindease.db")
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS mood_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            date TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    db.commit()
    db.close()

init_db()

# ── User Model ─────────────────────────────────────────
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    if user:
        return User(user["id"], user["username"])
    return None

# ── Helper Functions ───────────────────────────────────
def is_crisis_message(message):
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in CRISIS_KEYWORDS)

def get_groq_response(user_message, conversation_history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=300,
        temperature=0.7
    )
    return response.choices[0].message.content

# ── Auth Routes ────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        data = request.json
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        if not username or not password:
            return jsonify({"error": "Username and password are required."}), 400

        if len(username) < 3:
            return jsonify({"error": "Username must be at least 3 characters."}), 400

        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters."}), 400

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            db.close()
            return jsonify({"error": "Username already taken."}), 400

        hashed = generate_password_hash(password)
        db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed))
        db.commit()

        user_row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        db.close()

        user = User(user_row["id"], user_row["username"])
        login_user(user)
        return jsonify({"success": True}), 200

    return render_template("auth.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST":
        data = request.json
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        db = get_db()
        user_row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        db.close()

        if not user_row or not check_password_hash(user_row["password"], password):
            return jsonify({"error": "Invalid username or password."}), 401

        user = User(user_row["id"], user_row["username"])
        login_user(user)
        return jsonify({"success": True}), 200

    return render_template("auth.html", mode="login")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login_page"))


# ── Main Routes ────────────────────────────────────────
@app.route("/")
@login_required
def home():
    return render_template("index.html", username=current_user.username)


@app.route("/resources")
@login_required
def resources():
    return render_template("resources.html")


# ── Chat Route ─────────────────────────────────────────
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.json
    user_message = data.get("message", "")

    if not user_message.strip():
        return jsonify({"response": "Please type a message.", "crisis": False})

    # Load chat history from database
    db = get_db()
    rows = db.execute(
        "SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY timestamp ASC",
        (current_user.id,)
    ).fetchall()
    conversation_history = [{"role": r["role"], "content": r["content"]} for r in rows]
    conversation_history = conversation_history[-20:]  # last 20 messages

    if is_crisis_message(user_message):
        crisis_response = (
            "I'm really concerned about what you've shared. "
            "Please reach out to a crisis helpline immediately — "
            "you don't have to face this alone. "
            "🇳🇬 Nigeria: Mentally Aware Initiative — 0800-MENTALLY (0800-6368259). "
            "🌍 International: befrienders.org. "
            "I'm still here to talk, but please contact a professional right now."
        )
        return jsonify({"response": crisis_response, "crisis": True})

    try:
        bot_response = get_groq_response(user_message, conversation_history)

        # Save to database
        db.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (current_user.id, "user", user_message)
        )
        db.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (current_user.id, "assistant", bot_response)
        )
        db.commit()
        db.close()

        return jsonify({"response": bot_response, "crisis": False})

    except Exception as e:
        print(f"Groq API error: {e}")
        db.close()
        return jsonify({
            "response": "I'm having trouble connecting right now. Please try again in a moment.",
            "crisis": False
        })


# ── Mood Routes ────────────────────────────────────────
@app.route("/mood", methods=["POST"])
@login_required
def save_mood():
    data = request.json
    score = data.get("score")
    date = data.get("date")
    timestamp = data.get("timestamp")

    db = get_db()
    db.execute(
        "INSERT INTO mood_history (user_id, score, date, timestamp) VALUES (?, ?, ?, ?)",
        (current_user.id, score, date, timestamp)
    )
    db.commit()
    db.close()
    return jsonify({"success": True})


@app.route("/mood", methods=["GET"])
@login_required
def get_mood():
    db = get_db()
    rows = db.execute(
        "SELECT score, date, timestamp FROM mood_history WHERE user_id = ? ORDER BY timestamp ASC",
        (current_user.id,)
    ).fetchall()
    db.close()
    history = [{"score": r["score"], "date": r["date"], "timestamp": r["timestamp"]} for r in rows]
    history = history[-14:]  # last 14 entries
    return jsonify({"history": history})


@app.route("/chat-history", methods=["GET"])
@login_required
def get_chat_history():
    db = get_db()
    rows = db.execute(
        "SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY timestamp ASC",
        (current_user.id,)
    ).fetchall()
    db.close()
    history = [{"role": r["role"], "content": r["content"]} for r in rows]
    return jsonify({"history": history[-40:]})


@app.route("/clear-history", methods=["POST"])
@login_required
def clear_history():
    db = get_db()
    db.execute("DELETE FROM chat_history WHERE user_id = ?", (current_user.id,))
    db.commit()
    db.close()
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True)
