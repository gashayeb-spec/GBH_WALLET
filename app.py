import os
import re
import math
import random
import telebot
from threading import Thread
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Env variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = [os.environ.get("ADMIN_ID", "5351353727")]
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://gbh-wallet.onrender.com")

admin_config = {
    "password": "admin123",
    "otp": None
}

# --- IN-MEMORY DATABASE ---
members_db = [
    {
        "id": 1, 
        "ref_no": "TS-001", 
        "first_name": "አበበ", 
        "father_name": "በቀለ", 
        "phone_number": "0911000000", 
        "share_count": 2, 
        "status": "pending", 
        "paid_amount": 2000, 
        "telegram_id": "5351353727",
        "loan_date": "2026-08-27"
    }
]
guarantors_db = []
settings_db = {
    "latest_draw_number": "ዙር 01",
    "winner_name": "-",
    "latest_draw_date": "የለም",
    "support_phone": "0916039015"
}

# --- TELEGRAM BOT SETUP ---
bot = None
if BOT_TOKEN:
    try:
        bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

        @bot.message_handler(commands=['start'])
        def send_welcome(message):
            keyboard = telebot.types.InlineKeyboardMarkup()
            web_app_info = telebot.types.WebAppInfo(url=WEB_APP_URL)
            button = telebot.types.InlineKeyboardButton(text="📱 ተራመድ ሳኮ መተግበሪያን ክፈት", web_app=web_app_info)
            keyboard.add(button)

            text = (
                "👋 **እንኳን ወደ ተራመድ የቁጠባና ብድር ህብረት ሥራ ማህበር በሰላም መጡ!**\n\n"
                "የቁጠባና የብድር አገልግሎቶችን በቀላሉ ለማግኘት ከታች ያለውን ቁልፍ ይጫኑ።"
            )
            bot.send_message(message.chat.id, text, reply_markup=keyboard)

        def start_bot():
            print(">>> TELEGRAM BOT RUNNING... <<<")
            try:
                bot.remove_webhook()
            except Exception as e:
                print("Webhook Removal Warning:", e)
            bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)

        if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or os.environ.get("SERVER_SOFTWARE", "").startswith("gunicorn"):
            Thread(target=start_bot, daemon=True).start()
        elif not os.environ.get("SERVER_SOFTWARE"):
            Thread(target=start_bot, daemon=True).start()

    except Exception as e:
        print("Bot Initialization Error:", e)

# --- WEB ROUTES ---

@app.route('/', methods=['GET', 'HEAD'])
def home():
    return render_template('index.html')

@app.route('/admin', methods=['GET', 'HEAD'])
def admin_page():
    return render_template('admin.html')

# --- ADMIN AUTH & OTP API ---

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    if data and data.get('password') == admin_config["password"]:
        return jsonify({"success": True, "token": "secret-admin-token"}), 200
    return jsonify({"success": False, "message": "የይለፍ ቃል የተሳሳተ ነው!"}), 401

@app.route('/api/admin/send_otp', methods=['POST'])
def send_otp():
    otp = str(random.randint(100000, 999999))
    admin_config["otp"] = otp
    if bot and ADMIN_IDS:
        try:
            bot.send_message(ADMIN_IDS[0], f"🔑 **የይለፍ ቃል ማደሻ ማረጋገጫ ኮድ (OTP)፦** `{otp}`")
            return jsonify({"success": True, "message": "OTP በቴሌግራም ተልኳል!"})
        except Exception as e:
            return jsonify({"success": False, "message": f"መልእክት መላክ አልተቻለም: {str(e)}"})
    return jsonify({"success": True, "message": f"Demo OTP: {otp}"})

@app.route('/api/admin/reset_password', methods=['POST'])
def reset_password():
    data = request.get_json()
    if data.get('otp') == admin_config["otp"] and data.get('new_password'):
        admin_config["password"] = data.get('new_password')
        admin_config["otp"] = None
        return jsonify({"success": True, "message": "የይለፍ ቃል በስኬት ተቀይሯል!"})
    return jsonify({"success": False, "message": "የተሳሳተ OTP ኮድ!"})

# --- MEMBER MANAGEMENT (Approve, Cancel, Block, Delete) ---

@app.route('/api/admin/member_action', methods=['POST'])
def member_action():
    data = request.get_json()
    member_id = int(data.get('member_id'))
    action = data.get('action')

    global members_db
    member = next((m for m in members_db if m['id'] == member_id), None)

    if action == 'delete':
        members_db = [m for m in members_db if m['id'] != member_id]
        return jsonify({"success": True, "message": "ተመዝጋቢው ተሰርዟል!"})

    if member:
        if action in ['approve', 'cancel', 'block']:
            status_map = {'approve': 'approved', 'cancel': 'cancelled', 'block': 'blocked'}
            member['status'] = status_map[action]
            
            # ለተጠቃሚው በቴሌግራም ማስታወቂያ መላክ
            if bot and member.get('telegram_id'):
                try:
                    msgs = {
                        "approve": "🎉 **ደስ ደስ ይበልዎት!** ምዝገባዎ በአድሚኑ ፀድቋል።",
                        "cancel": "⚠️ **ማሳሰቢያ፦** ምዝገባዎ አልተቀበለም።",
                        "block": "🚫 **ማሳሰቢያ፦** መለያዎ ታግዷል።"
                    }
                    bot.send_message(member['telegram_id'], msgs.get(action, ""))
                except Exception as e:
                    print("Telegram Notif Error:", e)

            return jsonify({"success": True, "message": f"የተመዝጋቢው ሁኔታ ተቀይሯል!"})

    return jsonify({"success": False, "message": "አባሉ አልተገኘም!"})

@app.route('/api/admin/send_direct_message', methods=['POST'])
def send_direct_message():
    data = request.get_json()
    tg_id = data.get('telegram_id')
    msg = data.get('message')
    if bot and tg_id and msg:
        try:
            bot.send_message(tg_id, f"💬 **ከአድሚን የተላከ መልእክት፦**\n\n{msg}")
            return jsonify({"success": True, "message": "መልእክቱ ለአባሉ ተልኳል!"})
        except Exception as e:
            return jsonify({"success": False, "message": f"መላክ አልተቻለም: {str(e)}"})
    return jsonify({"success": False, "message": "መረጃው አልተሟላም!"})

# --- BROADCAST & GUARANTOR API ---

@app.route('/api/admin/broadcast', methods=['POST'])
def broadcast():
    data = request.get_json()
    message = data.get('message')
    if not message:
        return jsonify({"success": False, "message": "መልእክት አልተፃፈም!"}), 400

    count = 0
    if bot:
        for m in members_db:
            tg_id = m.get('telegram_id')
            if tg_id:
                try:
                    bot.send_message(tg_id, f"📢 **የጋራ ማስታወቂያ፦**\n\n{message}")
                    count += 1
                except Exception as e:
                    print(f"Broadcast Error to {tg_id}:", e)

    return jsonify({"success": True, "message": f"ማስታወቂያው ለ {count} አባላት ተልኳል!"})

@app.route('/api/admin/register_guarantor', methods=['POST'])
def register_guarantor():
    data = request.get_json()
    guarantors_db.append(data)
    return jsonify({"success": True, "message": "የዋስ መረጃ በስኬት ተመዝግቧል!"})

@app.route('/api/admin/add_admin', methods=['POST'])
def add_admin():
    data = request.get_json()
    new_admin_id = str(data.get('admin_id'))
    if new_admin_id and new_admin_id not in ADMIN_IDS:
        ADMIN_IDS.append(new_admin_id)
        return jsonify({"success": True, "message": "አዲስ አድሚን ተሾሟል!"})
    return jsonify({"success": False, "message": "አድሚኑ ቀደም ሲል አለ ወይም የተሳሳተ ID ነው!"})

@app.route('/api/admin/data', methods=['GET'])
def get_admin_data():
    return jsonify({
        "settings": settings_db,
        "members": members_db,
        "guarantors": guarantors_db
    })

# --- PUBLIC USER REGISTER API ---

@app.route('/api/register', methods=['POST'])
def register_member():
    data = request.get_json()
    new_id = len(members_db) + 1
    ref_no = f"TS-{new_id:03d}"
    
    member = {
        "id": new_id,
        "ref_no": ref_no,
        "first_name": data.get("first_name", ""),
        "father_name": data.get("father_name", ""),
        "phone_number": data.get("phone_number", ""),
        "share_count": int(data.get("share_count", 1)),
        "status": "pending",
        "paid_amount": 0,
        "telegram_id": data.get("telegram_id", "")
    }
    members_db.append(member)
    
    # Notify Admins
    if bot:
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    admin_id,
                    f"🆕 **አዲስ ተመዝጋቢ አባል!**\n\n"
                    f"👤 ስም፦ {member['first_name']} {member['father_name']}\n"
                    f"📞 ስልክ፦ {member['phone_number']}\n"
                    f"🆔 Ref No፦ `{ref_no}`"
                )
            except Exception as e:
                print("Admin Notification Error:", e)

    return jsonify({"success": True, "message": "ምዝገባዎ ተጠናቋል። ከአድሚን ማረጋገጫ ይጠብቁ!", "ref_no": ref_no})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
