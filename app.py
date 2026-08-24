import os
import requests
import sqlite3
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

BOT_TOKEN = "8416599811:AAG3WvG-3Pd7hqSUvIMw7r4Gzfg5sz3-MC4"
RENDER_URL = "https://gbh-wallet.onrender.com"

# TON CENTER API (ለብሎክቼይን መረጃዎች ማረጋገጫ)
TONCENTER_API_KEY = "" # አስፈላጊ ከሆነ ከ @toncenter_bot የራሶትን API Key መውሰድ ይችላሉ
TONCENTER_BASE_URL = "https://toncenter.com/api/v2/jsonRPC"

# የMaster Wallet አድራሻ (የተጠቃሚዎች ገቢ TON የሚሰበሰብበት ማዕከላዊ ዋሌት)
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            tx_hash TEXT UNIQUE,
            amount REAL,
            type TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ----------------------------------------------------
# REAL TON BLOCKCHAIN CHECKER (FETCH DEPOSITS)
# ----------------------------------------------------
def check_blockchain_deposits(telegram_id, memo_id):
    """
    ከTONCENTER API ላይ የMaster Wallet የትራንዛክሽን ታሪክ በመፈተሽ
    በተጠቃሚው Memo ID የተላከ ገቢ TON ካለ ባላንስ ያዘምናል
    """
    try:
        url = f"https://toncenter.com/api/v2/getTransactions?address={MASTER_WALLET_ADDRESS}&limit=20"
        headers = {"X-API-Key": TONCENTER_API_KEY} if TONCENTER_API_KEY else {}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            txs = response.json().get('result', [])
            conn = sqlite3.connect('wallet.db')
            cursor = conn.cursor()
            
            for tx in txs:
                in_msg = tx.get('in_msg', {})
                comment = in_msg.get('message', '')
                value_nanoton = int(in_msg.get('value', 0))
                tx_hash = tx.get('transaction_id', {}).get('hash', '')
                
                # የተጠቃሚውን Unique Memo ID ካገኘ እና አዲስ ትራንዛክሽን ከሆነ
                if comment == str(memo_id) and value_nanoton > 0:
                    amount_ton = value_nanoton / 1e9  # Convert NanoTON to TON
                    
                    # አዲስ ትራንዛክሽን መሆኑን ማረጋገጥ
                    cursor.execute("SELECT id FROM transactions WHERE tx_hash = ?", (tx_hash,))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO transactions (telegram_id, tx_hash, amount, type, status) VALUES (?, ?, ?, 'deposit', 'completed')", 
                                       (telegram_id, tx_hash, amount_ton))
                        cursor.execute("UPDATE users SET ton_balance = ton_balance + ? WHERE telegram_id = ?", 
                                       (amount_ton, telegram_id))
                        conn.commit()
            conn.close()
    except Exception as e:
        print(f"Blockchain check error: {e}")

# ----------------------------------------------------
# API ENDPOINTS
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
        # ለተጠቃሚው ለይቶ ማወቂያ Unique Memo ID መስጠት
        memo_id = f"GBH{telegram_id}"
        cursor.execute('INSERT INTO users (telegram_id, username, ton_balance, memo_id) VALUES (?, ?, ?, ?)',
                       (telegram_id, username, 0.0, memo_id))
        conn.commit()
        balance = 0.0
    else:
        balance, memo_id = user[0], user[1]

    conn.close()

    # የብሎክቼይን ገቢ ክፍያዎችን በራስ-ሰር መፈተሽ
    check_blockchain_deposits(telegram_id, memo_id)

    return jsonify({
        "telegram_id": telegram_id,
        "username": username,
        "balance": balance,
        "master_address": MASTER_WALLET_ADDRESS,
        "memo_id": memo_id
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
