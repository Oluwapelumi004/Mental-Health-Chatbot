from flask import Flask, request, jsonify, render_template
from groq import Groq

app = Flask(__name__)

# Paste your Groq API key here
client = Groq(api_key="paste-your-groq-key-here")

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


def is_crisis_message(message):
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in CRISIS_KEYWORDS)


def get_groq_response(user_message, conversation_history):
    """Call Groq API with full conversation history for context."""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add the new user message
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=messages,
        max_tokens=300,
        temperature=0.7
    )

    return response.choices[0].message.content


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/resources")
def resources():
    return render_template("resources.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "")
    conversation_history = data.get("history", [])

    if not user_message.strip():
        return jsonify({"response": "Please type a message.", "crisis": False})

    # Check for crisis keywords first
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
        return jsonify({"response": bot_response, "crisis": False})

    except Exception as e:
        print(f"Groq API error: {e}")
        return jsonify({
            "response": "I'm having trouble connecting right now. Please try again in a moment.",
            "crisis": False
        })


if __name__ == "__main__":
    app.run(debug=True)
