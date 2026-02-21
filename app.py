import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
import uuid
from auth import token_required, hash_password, verify_password, generate_token
from database import Database
from agent import create_agent

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'bc7d099cb5eacb2ea27a1e97af963a90fc8df843912f64f3ef1d904614494994')

POSTGRES_URI = os.getenv("POSTGRES_URI")
connection_pool = ConnectionPool(POSTGRES_URI, min_size=1, max_size=10)
db = Database(connection_pool)
agent = create_agent(connection_pool)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not username or not email or not password:
        return jsonify({"error": "Username, email and password are required"}), 400

    try:
        password_hash = hash_password(password)
        user_id = db.create_user(username, email, password_hash)
        return jsonify({"message": "User created successfully", "user_id": user_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    try:
        user = db.get_user_by_username(username)

        if not user or not verify_password(password, user[1]):
            return jsonify({"error": "Invalid credentials"}), 401

        token = generate_token(user[0], app.config['SECRET_KEY'])
        return jsonify({"token": token}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/chat', methods=['POST'])
@token_required
def chat(current_user_id):
    data = request.json
    message = data.get('message')
    thread_id = data.get('thread_id', str(uuid.uuid4()))

    if not message:
        return jsonify({"error": "Message is required"}), 400

    try:
        config = {"configurable": {"thread_id": thread_id}}
        response = agent.invoke({"messages": [("user", message)]}, config)
        return jsonify({
            "response": response["messages"][-1].content,
            "thread_id": thread_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
