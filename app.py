import os
import requests
import sqlite3
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

BOT_TOKEN = "8416599811:AAG3WvG-3Pd7hqSUvIMw7r4Gzfg5sz3-MC4"
RENDER_URL = "https://gbh-wallet.onrender.com"
MASTER_WALLET_ADDRESS = "EQD...YOUR_MASTER_TON_WALLET_ADDRESS_HERE..."

# ----------------------------------------------------
# DATABASE INITIALIZATION
# ----------------------------------------------------
def init_db():
    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            ton_balance REAL DEFAULT 0.0,
            memo_id TEXT UNIQUE
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ----------------------------------------------------
# AUTOMATIC WEBHOOK SETUP FUNCTION
# ----------------------------------------------------
def auto_setup_webhook():
    try:
        webhook_url = f"{RENDER_URL}/webhook"
        set_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
        res = requests.get(set_url, timeout=5)
        print("Webhook Status:", res.json())
    except Exception as e:
        print("Webhook setup error:", e)

# ----------------------------------------------------
# TELEGRAM BOT WEBHOOK HANDLER
# ----------------------------------------------------
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json() or {}
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        if text == "/start":
            welcome_msg = "እንኳን ወደ **GBH Wallet** በሰላም መጡ! 👋\n\nከታች ያለውን **Open GBH Wallet** የሚለውን በተን በመጫን ወደ አፕሊኬሽኑ መግባት ይችላሉ።"
            
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

# ----------------------------------------------------
# WEB APP ROUTES
# ----------------------------------------------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/user_info', methods=['POST'])
def get_user_info():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    username = data.get('username', 'User')

    if not telegram_id:
        return jsonify({"error": "Invalid user ID"}), 400

    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('SELECT ton_balance, memo_id FROM users WHERE telegram_id = ?', (telegram_id,))
    user = cursor.fetchone()

    if not user:
        memo_id = f"GBH{telegram_id}"
        cursor.execute('INSERT INTO users (telegram_id, username, ton_balance, memo_id) VALUES (?, ?, ?, ?)',
                       (telegram_id, username, 0.0, memo_id))
        conn.commit()
        balance = 0.0
    else:
        balance, memo_id = user[0], user[1]

    conn.close()

    return jsonify({
        "telegram_id": telegram_id,
        "username": username,
        "balance": balance,
        "master_address": MASTER_WALLET_ADDRESS,
        "memo_id": memo_id
    })

@app.route('/api/transfer', methods=['POST'])
def transfer():
    data = request.json or {}
    sender_id = data.get('sender_id')
    recipient_username = str(data.get('recipient_username', '')).replace('@', '').strip()
    
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "እባክዎን ትክክለኛ ቁጥር ያስገቡ"}), 400

    if amount <= 0:
        return jsonify({"success": False, "message": "ትክክለኛ የገንዘብ መጠን ያስገቡ"}), 400

    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()

    cursor.execute('SELECT ton_balance FROM users WHERE telegram_id = ?', (sender_id,))
    sender = cursor.fetchone()

    if not sender or sender[0] < amount:
        conn.close()
        return jsonify({"success": False, "message": "በቂ የገንዘብ መጠን የለዎትም!"}), 400

    cursor.execute('SELECT telegram_id, ton_balance FROM users WHERE username = ?', (recipient_username,))
    recipient = cursor.fetchone()

    if not recipient:
        conn.close()
        return jsonify({"success": False, "message": "ተቀባዩ በሲስተሙ ውስጥ አልተገኘም!"}), 404

    recipient_id = recipient[0]

    cursor.execute('UPDATE users SET ton_balance = ton_balance - ? WHERE telegram_id = ?', (amount, sender_id))
    cursor.execute('UPDATE users SET ton_balance = ton_balance + ? WHERE telegram_id = ?', (amount, recipient_id))

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": f"{amount} TON ለ @{recipient_username} በፍጥነት ተልኳል!"})

# አፑ ሲነሳ Webhook በራስ-ሰር እንዲያስተካክል
auto_setup_webhook()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
