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
        "grand_name": "ካሳ",
        "phone_number": "0911000000", 
        "address": "ሀዋሳ",
        "tin_number": "123456",
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

        # --- TELEGRAM INLINE BUTTON CALLBACK HANDLER (Approve / Cancel / Block) ---
        @bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'cancel_', 'block_')))
        def handle_admin_action(call):
            try:
                action, member_id = call.data.split('_')
                member_id = int(member_id)
                
                global members_db
                member = next((m for m in members_db if m['id'] == member_id), None)

                if member:
                    status_map = {'approve': 'approved', 'cancel': 'cancelled', 'block': 'blocked'}
                    member['status'] = status_map[action]
                    
                    status_text = {
                        'approve': '✅ **ተፅድቋል (Approved)**',
                        'cancel': '❌ **ተሰርዟል (Cancelled)**',
                        'block': '🚫 **ታግዷል (Blocked)**'
                    }

                    # በአድሚኑ የቴሌግራም መልእክት ስር ውሳኔውን ማሻሻል
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=call.message.text + f"\n\n📌 **የአድሚን ውሳኔ፦** {status_text[action]}"
                    )

                    # ለተመዝጋቢው ተጠቃሚ በቴሌግራም መልእክት መላክ
                    if member.get('telegram_id'):
                        try:
                            user_msgs = {
                                "approve": "🎉 **ደስ ደስ ይበልዎት!** የምዝገባ ጥያቄዎ በአድሚኑ ፀድቋል። አሁን መተግበሪያውን መጠቀም ይችላሉ።",
                                "cancel": "⚠️ **ማሳሰቢያ፦** የምዝገባ ጥያቄዎ አልተቀበለም። እባክዎን መረጃዎን አስተካክለው ድጋሚ ይሞክሩ።",
                                "block": "🚫 **ማሳሰቢያ፦** መለያዎ በአድሚን ታግዷል። ለበለጠ መረጃ ድጋፍን ያናግሩ።"
                            }
                            bot.send_message(member['telegram_id'], user_msgs[action])
                        except Exception as e:
                            print("Telegram User Notif Error:", e)
            except Exception as e:
                print("Callback Handling Error:", e)

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

# --- USER INFO API ---

@app.route('/api/member_info/<telegram_id>', methods=['GET'])
def get_member_info(telegram_id):
    user_members = [m for m in members_db if str(m.get('telegram_id')) == str(telegram_id)]
    return jsonify({
        "members": user_members,
        "settings": settings_db
    })

# --- ADMIN AUTH & OTP API ---

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json(silent=True) or {}
    if data.get('password') == admin_config["password"]:
        return jsonify({"success": True, "token": "secret-admin-token"}), 200
    return jsonify({"success": False, "message": "የይለፍ ቃል የተሳሳተ ነው!"}), 401

@app.route('/api/admin/send_otp', methods=['POST'])
def send_otp():
    otp = str(random.randint(100000, 999999))
    admin_config["otp"] = otp
    if bot and ADMIN_IDS and ADMIN_IDS[0]:
        try:
            bot.send_message(ADMIN_IDS[0], f"🔑 **የይለፍ ቃል ማደሻ ማረጋገጫ ኮድ (OTP)፦** `{otp}`")
            return jsonify({"success": True, "message": "የማረጋገጫ ኮድ (OTP) በቴሌግራም ተልኳል!"})
        except Exception as e:
            return jsonify({"success": False, "message": f"ኮዱን በቴሌግራም መላክ አልተቻለም፦ {str(e)}"})
    return jsonify({"success": False, "message": "የቴሌግራም አድሚን ID አልተገናኘም!"})

@app.route('/api/admin/reset_password', methods=['POST'])
def reset_password():
    data = request.get_json(silent=True) or {}
    user_otp = str(data.get('otp', '')).strip()
    new_password = str(data.get('new_password', '')).strip()

    if not admin_config["otp"]:
        return jsonify({"success": False, "message": "እባክዎ አስቀድመው የ OTP ኮድ ይላኩ!"}), 400

    if user_otp != admin_config["otp"]:
        return jsonify({"success": False, "message": "የተሳሳተ OTP ኮድ ነው! እባክዎ እንደገና ይሞክሩ።"}), 400

    if not new_password:
        return jsonify({"success": False, "message": "እባክዎ አዲስ የይለፍ ቃል ያስገቡ!"}), 400

    admin_config["password"] = new_password
    admin_config["otp"] = None  # OTPው ጥቅም ላይ ስለዋለ ያጠፋዋል
    return jsonify({"success": True, "message": "የይለፍ ቃል በስኬት ተቀይሯል! አሁን በአዲሱ የይለፍ ቃል መግባት ይችላሉ።"})

# --- MEMBER MANAGEMENT (Panel & Telegram Action) ---

@app.route('/api/admin/member_action', methods=['POST'])
def member_action():
    data = request.get_json(silent=True) or {}
    member_id = int(data.get('member_id', 0))
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

            return jsonify({"success": True, "message": "የተመዝጋቢው ሁኔታ ተቀይሯል!"})

    return jsonify({"success": False, "message": "አባሉ አልተገኘም!"})

# --- PUBLIC USER REGISTER API ---

@app.route('/api/register', methods=['POST'])
def register_member():
    try:
        # FormData ወይም JSON ዳታዎችን በአንድ ላይ ይቀበላል
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()

        new_id = len(members_db) + 1
        ref_no = f"TS-{new_id:03d}"
        
        member = {
            "id": new_id,
            "ref_no": ref_no,
            "first_name": data.get("first_name", ""),
            "father_name": data.get("father_name", ""),
            "grand_name": data.get("grand_name", ""),
            "phone_number": data.get("phone_number", ""),
            "address": data.get("address", ""),
            "tin_number": data.get("tin_number", ""),
            "share_count": int(data.get("share_count", 1)),
            "status": "pending",
            "paid_amount": 0,
            "telegram_id": str(data.get("telegram_id", ""))
        }
        members_db.append(member)
        
        # ቦቱ ለአድሚን ከእነ Inline Action Buttons እንዲልክ ማድረግ
        if bot:
            markup = telebot.types.InlineKeyboardMarkup(row_width=3)
            btn_approve = telebot.types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{new_id}")
            btn_cancel = telebot.types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{new_id}")
            btn_block = telebot.types.InlineKeyboardButton("🚫 Block", callback_data=f"block_{new_id}")
            markup.add(btn_approve, btn_cancel, btn_block)

            admin_msg = (
                f"🆕 **አዲስ የሰው ምዝገባ ጥያቄ!**\n\n"
                f"👤 **ስም፦** {member['first_name']} {member['father_name']} {member['grand_name']}\n"
                f"📞 **ስልክ፦** {member['phone_number']}\n"
                f"📍 **አድራሻ፦** {member['address']}\n"
                f"🆔 **TIN፦** {member['tin_number'] if member['tin_number'] else 'የለውም'}\n"
                f"🔢 **ዕድል ብዛት፦** {member['share_count']}\n"
                f"🆔 **Ref No፦** `{ref_no}`\n"
                f"💬 **TG ID፦** `{member['telegram_id']}`"
            )

            for admin_id in ADMIN_IDS:
                if admin_id:
                    try:
                        bot.send_message(admin_id, admin_msg, reply_markup=markup)
                    except Exception as e:
                        print(f"Admin Notification Error for {admin_id}:", e)

        return jsonify({"success": True, "message": "ምዝገባዎ ተጠናቋል። ከአድሚን ማረጋገጫ ይጠብቁ!", "ref_no": ref_no}), 200

    except Exception as e:
        print("Registration Error:", e)
        return jsonify({"success": False, "message": f"ምዝገባውን ማካሄድ አልተቻለም፦ {str(e)}"}), 500

# --- ADMIN API DATA GETTER ---

@app.route('/api/admin/data', methods=['GET'])
def get_admin_data():
    return jsonify({
        "settings": settings_db,
        "members": members_db,
        "guarantors": guarantors_db
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
