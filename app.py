import os
import requests
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "teramed_secret")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "5351353727")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage" if BOT_TOKEN else None

# Temporary In-Memory Database for Teramed Sacco
members_db = []
savings_db = []

def send_telegram_notification(chat_id, message):
    if not TELEGRAM_API_URL:
        print("Telegram Token አልተዋቀረም።")
        return None
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(TELEGRAM_API_URL, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/api/register', methods=['POST'])
def register_member():
    data = request.json or {}
    full_name = data.get('full_name')
    phone = data.get('phone')
    saving_amount = data.get('saving_amount')
    telegram_id = data.get('telegram_id', 'N/A')

    if not full_name or not phone or not saving_amount:
        return jsonify({"status": "error", "message": "እባክዎ ሁሉንም መስኮች ይሙሉ!"}), 400

    member = {
        "id": len(members_db) + 1,
        "full_name": full_name,
        "phone": phone,
        "saving_amount": saving_amount,
        "telegram_id": telegram_id,
        "status": "Pending"
    }
    members_db.append(member)

    admin_msg = (
        f"<b>🔔 አዲስ የቁጠባ ምዝገባ ጥያቄ (Teramed Sacco)</b>\n\n"
        f"<b>ስም:</b> {full_name}\n"
        f"<b>ስልክ:</b> {phone}\n"
        f"<b>ወርሃዊ ቁጠባ:</b> {saving_amount} ብር\n"
        f"<b>Telegram ID:</b> {telegram_id}"
    )
    send_telegram_notification(ADMIN_ID, admin_msg)

    return jsonify({"status": "success", "message": "ምዝገባዎ በተሳካ ሁኔታ ተልኳል!"})

@app.route('/api/admin/members', methods=['GET'])
def get_members():
    return jsonify({"status": "success", "data": members_db})

@app.route('/api/admin/approve', methods=['POST'])
def approve_member():
    data = request.json or {}
    member_id = data.get('member_id')
    
    for member in members_db:
        if member['id'] == member_id:
            member['status'] = "Approved"
            if member.get('telegram_id') and member['telegram_id'] != 'N/A':
                user_msg = f"🎉 <b>እንኳን ደስ አለዎት!</b>\n\nበተራመድ ብድር እና ቁጠባ ማህበር የምዝገባ ጥያቄዎ ጸድቋል።"
                send_telegram_notification(member['telegram_id'], user_msg)
            return jsonify({"status": "success", "message": "አባሉ በተሳካ ሁኔታ ጸድቋል!"})
            
    return jsonify({"status": "error", "message": "አባሉ አልተገኘም!"}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)
