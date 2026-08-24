import sqlite3
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
BOT_TOKEN = "8416599811:AAG3WvG-3Pd7hqSUvIMw7r4Gzfg5sz3-MC4"

# Database initialization
def init_db():
    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            ton_balance REAL DEFAULT 10.0,
            ton_address TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/user_info', methods=['POST'])
def get_user_info():
    data = request.json
    telegram_id = data.get('telegram_id')
    username = data.get('username', 'User')

    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('SELECT ton_balance, ton_address FROM users WHERE telegram_id = ?', (telegram_id,))
    user = cursor.fetchone()

    if not user:
        # Generate dummy deposit address for MVP
        mock_address = f"EQD{telegram_id}MockTonAddressForDemo"
        cursor.execute('INSERT INTO users (telegram_id, username, ton_balance, ton_address) VALUES (?, ?, ?, ?)',
                       (telegram_id, username, 10.0, mock_address))
        conn.commit()
        balance, address = 10.0, mock_address
    else:
        balance, address = user[0], user[1]

    conn.close()
    return jsonify({
        "telegram_id": telegram_id,
        "username": username,
        "balance": balance,
        "address": address
    })

@app.route('/api/transfer', methods=['POST'])
def transfer():
    data = request.json
    sender_id = data.get('sender_id')
    recipient_username = data.get('recipient_username').replace('@', '').strip()
    amount = float(data.get('amount', 0))

    if amount <= 0:
        return jsonify({"success": False, "message": "ትክክለኛ የገንዘብ መጠን ያስገቡ"}), 400

    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()

    # Check sender balance
    cursor.execute('SELECT ton_balance FROM users WHERE telegram_id = ?', (sender_id,))
    sender = cursor.fetchone()

    if not sender or sender[0] < amount:
        conn.close()
        return jsonify({"success": False, "message": "በቂ የገንዘብ መጠን የለዎትም!"}), 400

    # Find recipient
    cursor.execute('SELECT telegram_id, ton_balance FROM users WHERE username = ?', (recipient_username,))
    recipient = cursor.fetchone()

    if not recipient:
        conn.close()
        return jsonify({"success": False, "message": "ተቀባዩ በሲስተሙ ውስጥ አልተገኘም!"}), 404

    recipient_id, recipient_balance = recipient[0], recipient[1]

    # Execute transfer
    cursor.execute('UPDATE users SET ton_balance = ton_balance - ? WHERE telegram_id = ?', (amount, sender_id))
    cursor.execute('UPDATE users SET ton_balance = ton_balance + ? WHERE telegram_id = ?', (amount, recipient_id))

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": f"{amount} TON ለ @{recipient_username} በፍጥነት ተልኳል!"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
