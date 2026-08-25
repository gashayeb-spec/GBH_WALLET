import os
import requests
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "teramed_secret")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "5351353727")

# Dynamic Telegram API URL Generator (token ሲቀየር እንዳይበላሽ)
def get_telegram_url():
    token = os.getenv("BOT_TOKEN")
    return f"https://api.telegram.org/bot{token}/sendMessage" if token else None

# Temporary In-Memory Database for Teramed Sacco
members_db = []
savings_db = []

def send_telegram_notification(chat_id, message, reply_markup=None):
    url = get_telegram_url()
    if not url:
        print("Telegram Token አልተዋቀረም።")
        return None
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
        
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")
        return None

# በቴሌግራም ላይ የአዝራር ምላሾችን (Callback Query) ለማስተናገድ
def answer_callback_query(callback_query_id, text):
    token = os.getenv("BOT_TOKEN")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    requests.post(url, json={"callback_query_id": callback_query_id, "text": text})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

# --- ቴሌግራም ቦቱ መልእክት እና የአዝራር ጭነቶችን ሲቀበል የሚሰራው ክፍል (WebHook) ---
@app.route('/api/telegram_webhook', methods=['POST'])
def telegram_webhook():
    data = request.json or {}
    
    # 1. ተራ መልእክት ሲላክ (/start)
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            welcome_msg = (
                "👋 <b>እንኳን ወደ ተራመድ ብድርና ቁጠባ ማህበር በደህና መጡ!</b>\n\n"
                "አባል ለመሆን ወይም አገልግሎቶችን ለማግኘት ከታች ያለውን Button ይጫኑ።"
            )
            reply_markup = {
                "inline_keyboard": [[
                    {
                        "text": "📱 ተራመድ Sacco ክፈት",
                        "web_app": {"url": "https://gbh-wallet.onrender.com"}
                    }
                ]]
            }
            send_telegram_notification(chat_id, welcome_msg, reply_markup)

    # 2. አድሚኑ አዝራር ሲጫን (Approve / Cancel / Block)
    elif "callback_query" in data:
        callback = data["callback_query"]
        callback_id = callback["id"]
        action_data = callback.get("data", "")
        
        # Approve Action
        if action_data.startswith("approve_"):
            member_id = int(action_data.split("_")[1])
            for member in members_db:
                if member['id'] == member_id:
                    member['status'] = "Approved"
                    answer_callback_query(callback_id, "ምዝገባው ጸድቋል!")
                    send_telegram_notification(ADMIN_ID, f"✅ የ አባል <b>{member['full_name']}</b> ምዝገባ ጸድቋል።")
                    
                    if member.get('telegram_id') and member['telegram_id'] != 'N/A':
                        user_msg = "🎉 <b>እንኳን ደስ አለዎት!</b>\n\nበተራመድ ብድር እና ቁጠባ ማህበር የምዝገባ ጥያቄዎ ጸድቋል።"
                        send_telegram_notification(member['telegram_id'], user_msg)
                    break

        # Cancel Action
        elif action_data.startswith("cancel_"):
            member_id = int(action_data.split("_")[1])
            for member in members_db:
                if member['id'] == member_id:
                    member['status'] = "Cancelled"
                    answer_callback_query(callback_id, "ምዝገባው ተሰርዟል!")
                    send_telegram_notification(ADMIN_ID, f"❌ የ አባል <b>{member['full_name']}</b> ምዝገባ ውድቅ ተደርጓል።")
                    
                    if member.get('telegram_id') and member['telegram_id'] != 'N/A':
                        user_msg = "❌ <b>ይቅርታ!</b>\n\nበተራመድ ብድር እና ቁጠባ ማህበር የምዝገባ ጥያቄዎ ውድቅ ተደርጓል።"
                        send_telegram_notification(member['telegram_id'], user_msg)
                    break

        # Block Action
        elif action_data.startswith("block_"):
            user_id = action_data.split("_")[1]
            answer_callback_query(callback_id, "ተጠቃሚው ታግዷል!")
            send_telegram_notification(ADMIN_ID, f"🚫 ተጠቃሚ ID: <b>{user_id}</b> Block ተደርጓል።")

    return jsonify({"status": "ok"}), 200

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

    # ለአድሚን የሚላክ ማሳወቂያ ከ አዝራሮች (Approve, Cancel, Block) ጋር
    admin_msg = (
        f"<b>🔔 አዲስ የቁጠባ ምዝገባ ጥያቄ (Teramed Sacco)</b>\n\n"
        f"<b>ስም:</b> {full_name}\n"
        f"<b>ስልክ:</b> {phone}\n"
        f"<b>ወርሃዊ ቁጠባ:</b> {saving_amount} ብር\n"
        f"<b>Telegram ID:</b> {telegram_id}"
    )

    admin_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": f"approve_{member['id']}"},
                {"text": "❌ Cancel", "callback_data": f"cancel_{member['id']}"}
            ],
            [
                {"text": "🚫 Block User", "callback_data": f"block_{telegram_id}"}
            ]
        ]
    }

    send_telegram_notification(ADMIN_ID, admin_msg, admin_markup)

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
