import os
import requests
import sqlite3
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

BOT_TOKEN = "8416599811:AAG3WvG-3Pd7hqSUvIMw7r4Gzfg5sz3-MC4"
RENDER_URL = "https://gbh-wallet.onrender.com"

# የእርስዎን ዋና የTON ዋሌት አድራሻ እዚህ ያስገቡ (Deposit የሚደረገው ገንዘብ የሚሰበሰብበት)
MASTER_TON_ADDRESS = "EQD________________________________________"

def init_db():
    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            ton_balance REAL DEFAULT 0.0,
            memo_id TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def auto_setup_webhook():
    try:
        webhook_url = f"{RENDER_URL}/webhook"
        set_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
        requests.get(set_url, timeout=5)
    except Exception as e:
        print("Webhook error:", e)

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json() or {}
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
        username = update["message"]["chat"].get("username", "")
        first_name = update["message"]["chat"].get("first_name", "User")

        if text == "/start":
            # አዲስ ተጠቃሚ ሲመጣ አውቶማቲክ ዋሌት እና Memo ID መክፈት
            conn = sqlite3.connect('wallet.db')
            cursor = conn.cursor()
            cursor.execute('SELECT memo_id FROM users WHERE telegram_id = ?', (chat_id,))
            user = cursor.fetchone()

            if not user:
                memo_id = f"GBH{chat_id}"
                cursor.execute(
                    'INSERT INTO users (telegram_id, username, first_name, ton_balance, memo_id) VALUES (?, ?, ?, ?, ?)',
                    (chat_id, username, first_name, 0.0, memo_id)
                )
                conn.commit()
            conn.close()

            welcome_msg = f"ሰላም **{first_name}**👋\n\nእንኳን ወደ **GBH Wallet** በሰላም መጡ! ዋሌትዎ በስኬት ተከፍቷል።\n\nከታች ያለውን **Open Wallet** በተን በመጫን ሂሳብዎን ማየትና ገንዘብ ማስገባት ይችላሉ።"
            
            payload = {
                "chat_id": chat_id,
                "text": welcome_msg,
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [[
                        {
                            "text": "📲 Open GBH Wallet",
                            "web_app": {"url": RENDER_URL}
                        }
                    ]]
                }
            }
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)

    return "OK", 200

@app.route('/')
def home():
    return render_template('index.html')

# የተጠቃሚውን የመለያ መረጃ እና የDeposit መመሪያ ማቅረቢያ API
@app.route('/api/user_info', methods=['POST'])
def get_user_info():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    username = data.get('username', '')
    first_name = data.get('first_name', 'User')

    if not telegram_id:
        return jsonify({"error": "Invalid user ID"}), 400

    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('SELECT ton_balance, memo_id FROM users WHERE telegram_id = ?', (telegram_id,))
    user = cursor.fetchone()

    if not user:
        memo_id = f"GBH{telegram_id}"
        cursor.execute(
            'INSERT INTO users (telegram_id, username, first_name, ton_balance, memo_id) VALUES (?, ?, ?, ?, ?)',
            (telegram_id, username, first_name, 0.0, memo_id)
        )
        conn.commit()
        balance = 0.0
    else:
        balance, memo_id = user[0], user[1]

    conn.close()

    return jsonify({
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "balance": balance,
        "master_address": MASTER_TON_ADDRESS,
        "memo_id": memo_id
    })

auto_setup_webhook()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
