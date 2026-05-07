from flask import Flask, render_template, request, redirect, session, jsonify
from flask_session import Session
from pymongo import MongoClient
from dotenv import load_dotenv
import os, bcrypt, google.generativeai as genai, re
from datetime import datetime
from bson.objectid import ObjectId

# --- Load environment ---
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

app = Flask(__name__)

# --- MongoDB Connection ---
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["learning_tutor"]
users = db["users"]
chats = db["chats"]

# --- Flask Session Config ---
app.secret_key = os.urandom(24)
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# --- ROUTES ---
@app.route('/')
def home():
    if "user" in session:
        return render_template("index6.html", username=session["user"])
    return redirect("/login")


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].encode("utf-8")
        if users.find_one({"username": username}):
            return render_template("register.html", error="⚠️ Username already exists!")
        hashed = bcrypt.hashpw(password, bcrypt.gensalt())
        users.insert_one({"username": username, "password": hashed})
        return redirect("/login")
    return render_template("register.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].encode("utf-8")
        user = users.find_one({"username": username})
        if user and bcrypt.checkpw(password, user["password"]):
            session["user"] = username
            return redirect("/")
        return render_template("login.html", error="❌ Invalid username or password!")
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect("/login")

@app.route('/chat', methods=['POST'])
def chat():
    if "user" not in session:
        return jsonify({"reply": "Please login first!", "type": "text"})
    data = request.get_json()
    message = data.get("message")
    mode = data.get("mode", "normal")

    if mode == "step":
        prompt_mode = "Explain step-by-step with reasoning."
    elif mode == "quiz":
        prompt_mode = "Create a short quiz with answers."
    else:
        prompt_mode = "Explain clearly with examples."

    is_code_request = any(word in message.lower() for word in ["code","program","script","python","java","c++","javascript"])

    prompt = f"""
    You are a helpful AI tutor.
    The user message may be in English, Hindi, or Punjabi.
    Detect the language automatically and respond in the same language.
    Question: {message}
    {prompt_mode}
    {"Provide only code without explanation and maintain proper indentation." if is_code_request else "Provide clear explanation in plain text."}
    """

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        reply = response.text.strip()

        # --- Clean reply for normal text ---
        if not is_code_request:
            reply = re.sub(r"[#*_]", "", reply)

        chats.insert_one({
            "username": session["user"],
            "user": message,
            "bot": reply,
            "type": "code" if is_code_request else "text",
            "timestamp": datetime.utcnow()
        })

        return jsonify({"reply": reply, "type": "code" if is_code_request else "text"})
    except Exception as e:
        return jsonify({"reply": f"⚠️ Error: {str(e)}", "type": "text"})

@app.route('/history')
def get_history():
    if "user" not in session:
        return jsonify([])
    user_chats = list(chats.find({"username": session["user"]}).sort("timestamp", -1))
    for chat in user_chats:
        chat["_id"] = str(chat["_id"])
    return jsonify(user_chats)

# --- Delete a specific chat ---
@app.route('/delete/<chat_id>', methods=['DELETE'])
def delete_chat(chat_id):
    if "user" not in session:
        return jsonify({"success": False})
    try:
        chats.delete_one({"_id": ObjectId(chat_id), "username": session["user"]})
        return jsonify({"success": True})
    except:
        return jsonify({"success": False})

if __name__ == '__main__':
    app.run(debug=True)
