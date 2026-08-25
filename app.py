import os
import sqlite3
import requests
from flask import Flask, render_template, request, jsonify
from config import BOT_TOKEN, CHAPA_SECRET_KEY, BASE_URL
from bot_telegram import send_kyc_to_admin, generate_and_send_otp

app = Flask(__name__)

# 1. የፊት ገጽ (Main WebApp View)
@app.route('/')
def home():
    return render_template('index.html')

# 2. የተጠቃሚ መረጃ ማቅረቢያ API
@app.route('/api/user_info', methods=['POST'])
def get_user_info():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    
    if not telegram_id:
        return jsonify({"status": "error", "message": "የቴሌግራም መለያ (ID) አልተገኘም"}), 400

    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('SELECT first_name, ton_balance, etb_balance, memo_id, kyc_status FROM users WHERE telegram_id = ?', (telegram_id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        return jsonify({
            "status": "success",
            "first_name": user[0],
            "ton_balance": user[1],
            "etb_balance": user[2],
            "memo_id": user[3],
            "kyc_status": user[4]
        })
    return jsonify({"status": "error", "message": "ተጠቃሚው አልተመዘገበም"}), 444

# 3. የ KYC መረጃ እና የመታወቂያ ፎቶ መቀበያ Endpoint
@app.route('/api/submit_kyc', methods=['POST'])
def submit_kyc():
    telegram_id = request.form.get('telegram_id')
    full_name = request.form.get('full_name')
    doc_type = request.form.get('doc_type')
    photo_file = request.files.get('document_photo')

    if not photo_file or not telegram_id:
        return jsonify({"status": "error", "message": "እባክዎን ሁሉንም መረጃዎች ይሙሉ"}), 400

    # ፎቶውን ወደ ቴሌግራም ሰርቨር መላክ
    files = {'photo': (photo_file.filename, photo_file.stream, photo_file.mimetype)}
    res = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", 
                        data={'chat_id': telegram_id, 'caption': 'KYC Upload'}, files=files).json()

    if res.get('ok'):
        file_id = res['result']['photo'][-1]['file_id']
        # መረጃውን ለአድሚን በቴሌግራም መላክ
        send_kyc_to_admin(telegram_id, full_name, doc_type, file_id)
        
        # የ KYC ሁኔታን PENDING ማድረግ
        conn = sqlite3.connect('wallet.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET kyc_status='PENDING', kyc_doc_type=? WHERE telegram_id=?", (doc_type, telegram_id))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "message": "የ KYC መረጃዎ ለአድሚን ተልኳል"}), 200

    return jsonify({"status": "error", "message": "ፎቶውን መላክ አልተቻለም"}), 500

# 4. የ OTP ጥያቄ መላኪያ (Forgot Password / Reset)
@app.route('/api/request_otp', methods=['POST'])
def request_otp():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    
    if not telegram_id:
        return jsonify({"status": "error", "message": "የቴሌግራም ID ያስፈልጋል"}), 400

    otp = generate_and_send_otp(telegram_id)
    return jsonify({"status": "success", "message": "OTP በቴሌግራም ተልኮልዎታል"}), 200

# 5. የ OTP ማረጋገጫ እና አዲስ ፓስወርድ መመዝገቢያ
@app.route('/api/verify_otp', methods=['POST'])
def verify_otp():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    user_otp = data.get('otp')
    new_password = data.get('new_password')

    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('SELECT otp_code FROM users WHERE telegram_id = ?', (telegram_id,))
    row = cursor.fetchone()

    if row and row[0] == user_otp:
        cursor.execute('UPDATE users SET password = ?, otp_code = NULL WHERE telegram_id = ?', (new_password, telegram_id))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "ፓስወርድዎ በስኬት ተቀይሯል"}), 200

    conn.close()
    return jsonify({"status": "error", "message": "የተሳሳተ OTP ኮድ"}), 400

# 6. የ Chapa ክፍያ ማስጀመሪያ (Deposit ETB)
@app.route('/api/deposit_chapa', methods=['POST'])
def deposit_chapa():
    data = request.json or {}
    telegram_id = data.get('telegram_id')
    amount = data.get('amount')
    email = data.get('email', 'user@gbhwallet.com')

    tx_ref = f"GBH_TX_{telegram_id}_{os.urandom(4).hex()}"
    
    headers = {
        'Authorization': f'Bearer {CHAPA_SECRET_KEY}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        "amount": str(amount),
        "currency": "ETB",
        "email": email,
        "first_name": f"User_{telegram_id}",
        "tx_ref": tx_ref,
        "callback_url": f"{BASE_URL}/api/chapa_webhook",
        "return_url": BASE_URL,
        "customization": {
            "title": "GBH Wallet Deposit",
            "description": "የብሬ ሂሳብ መሙያ"
        }
    }

    res = requests.post("https://api.chapa.co/v1/transaction/initialize", json=payload, headers=headers).json()
    
    if res.get('status') == 'success':
        # ትራንዛክሽኑን PENDING ብሎ መመዝገብ
        conn = sqlite3.connect('wallet.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO transactions (telegram_id, type, amount, currency, status, reference_id) VALUES (?, ?, ?, ?, ?, ?)',
                       (telegram_id, 'DEPOSIT_ETB', amount, 'ETB', 'PENDING', tx_ref))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "checkout_url": res['data']['checkout_url']})
    
    return jsonify({"status": "error", "message": "የ Chapa ክፍያ መደወያ አልተሳካም"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
