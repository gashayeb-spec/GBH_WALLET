import os
import re
import math
import random
import sqlite3
import requests
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
SUPER_ADMIN_ID = str(os.environ.get("ADMIN_ID", "5351353727"))
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://gbh-wallet.onrender.com")

admin_config = {
    "password": "admin123"
}

# Temporary OTP Store (In-Memory)
otp_store = {}

# --- IN-MEMORY DATABASE & DATA STORES ---
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

# Roles DB (Registered Admins)
admins_db = [
    {
        "admin_id": SUPER_ADMIN_ID,
        "password": "admin123",
        "role": "super"
    }
]

expenses_db = []
receipts_db = []
loans_db = []
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

        # --- TELEGRAM INLINE BUTTON CALLBACK HANDLER ---
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

                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=call.message.text + f"\n\n📌 **የአድሚን ውሳኔ፦** {status_text[action]}"
                    )

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

    except Exception as e:
        print("Bot Initialization Error:", e)

# SAFELY RUN BOT POLLING IN A SINGLE THREAD
def run_bot_safe():
    if bot:
        try:
            bot.remove_webhook()
        except Exception as e:
            print("Webhook Removal Warning:", e)
        try:
            print(">>> TELEGRAM BOT RUNNING SAFELY... <<<")
            bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except Exception as e:
            print("Bot Polling Error:", e)

# Helper function to send Telegram Messages
def send_telegram_msg(chat_id, message):
    if bot:
        try:
            bot.send_message(chat_id, message)
        except Exception as e:
            print(f"Error sending message to {chat_id}:", e)

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

# --- ADMIN AUTH, ROLES & OTP API ---

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json(silent=True) or {}
    admin_id = str(data.get('admin_id', '')).strip()
    password = str(data.get('pass', '')).strip()

    # 1. SUPER ADMIN LOGIN CHECK
    if admin_id == SUPER_ADMIN_ID:
        if password == admin_config["password"]:
            otp = str(random.randint(100000, 999999))
            otp_store[admin_id] = otp
            
            msg = f"🔐 **ተራመድ ሳኮ - Super Admin Login OTP**\n\nየመግቢያ ማረጋገጫ ኮድዎ፦ `{otp}`\n\nእባክዎን ይህንን ኮድ ለማንም አያጋሩ!"
            send_telegram_msg(SUPER_ADMIN_ID, msg)
            
            return jsonify({"status": "otp_required", "message": "OTP ማረጋገጫ ኮድ ወደ ቴሌግራምህ ተልኳል!"}), 200
        else:
            return jsonify({"message": "የተሳሳተ የይለፍ ቃል!"}), 401

    # 2. OTHER ROLE-BASED ADMINS CHECK
    target_admin = next((a for a in admins_db if str(a['admin_id']) == admin_id and a['password'] == password), None)
    
    if target_admin:
        return jsonify({"status": "success", "role": target_admin['role']}), 200
    else:
        return jsonify({"message": "የተሳሳተ የይለፍ ቃል ወይም Admin ID!"}), 401


@app.route('/api/admin/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json(silent=True) or {}
    admin_id = str(data.get('admin_id', '')).strip()
    user_otp = str(data.get('otp', '')).strip()

    if admin_id in otp_store and otp_store[admin_id] == user_otp:
        del otp_store[admin_id]
        return jsonify({"status": "success", "role": "super"}), 200
    else:
        return jsonify({"message": "የተሳሳተ ወይም ጊዜው ያለፈበት OTP!"}), 400


@app.route('/api/admin/assign_role', methods=['POST'])
def assign_role():
    data = request.get_json(silent=True) or {}
    admin_id = str(data.get('admin_id', '')).strip()
    role = str(data.get('role', '')).strip()

    if not admin_id or not role:
        return jsonify({"message": "እባክዎን Admin ID እና Role ያስገቡ!"}), 400

    existing_admin = next((a for a in admins_db if str(a['admin_id']) == admin_id), None)
    if existing_admin:
        existing_admin['role'] = role
    else:
        admins_db.append({
            "admin_id": admin_id,
            "password": "123456",  # Default Password for newly created admin
            "role": role
        })

    msg = f"🎖 **አዲስ የአድሚን ስልጣን ተሰጥቶዎታል!**\n\nየስራ ድርሻዎ፦ **{role.upper()}**\nመግቢያ Password፦ `123456`\nእባክዎን ገብተው ፓስወርድዎን ይቀይሩ።"
    send_telegram_msg(admin_id, msg)

    return jsonify({"message": f"አድሚን {admin_id} በ {role} ስልጣን በስኬት ተሾሟል!"}), 200


@app.route('/api/admin/request_reset', methods=['POST'])
def request_reset():
    data = request.get_json(silent=True) or {}
    admin_id = str(data.get('admin_id', '')).strip()

    otp = str(random.randint(100000, 999999))
    otp_store[f"reset_{admin_id}"] = otp

    msg = f"⚠️ **የይለፍ ቃል ቅያሬ ጥያቄ!**\n\nAdmin ID: `{admin_id}` የይለፍ ቃል ለመቀየር እየሞከረ ነው።\n\nለመፍቀድ ይህንን OTP ይስጡት፦ `{otp}`"
    send_telegram_msg(SUPER_ADMIN_ID, msg)

    return jsonify({"message": "የይለፍ ቃል መቀየሪያ OTP ለ Super Admin ተልኳል። ከእሱ ተቀብለው ያስገቡ!"}), 200


# --- FINANCE & EXPENSES API ---

@app.route('/api/admin/add_expense', methods=['POST'])
def add_expense():
    data = request.get_json(silent=True) or {}
    desc = data.get('description', '')
    amount = float(data.get('amount', 0))

    if not desc or amount <= 0:
        return jsonify({"message": "እባክዎን ትክክለኛ መረጃ ያስገቡ!"}), 400

    expenses_db.append({"description": desc, "amount": amount})
    return jsonify({"message": "ወጪው በስኬት ተመዝግቧል!"}), 200


# --- MEMBER MANAGEMENT ---

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
        
        if bot:
            markup = telebot.types.InlineKeyboardMarkup()
            
            btn_approve = telebot.types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{new_id}")
            btn_cancel = telebot.types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{new_id}")
            btn_block = telebot.types.InlineKeyboardButton("🚫 Block", callback_data=f"block_{new_id}")
            
            admin_panel_url = f"{WEB_APP_URL}/admin"
            btn_panel = telebot.types.InlineKeyboardButton(
                "📊 አድሚን ፓናል ክፈት", 
                web_app=telebot.types.WebAppInfo(url=admin_panel_url)
            )

            markup.add(btn_approve, btn_cancel, btn_block)
            markup.add(btn_panel)

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

            try:
                bot.send_message(SUPER_ADMIN_ID, admin_msg, reply_markup=markup)
            except Exception as e:
                print(f"Admin Notification Error for {SUPER_ADMIN_ID}:", e)

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
        "guarantors": guarantors_db,
        "expenses": expenses_db,
        "receipts": receipts_db,
        "loans": loans_db
    })

# --- START BOT SAFELY IN BACKGROUND ---
if bot:
    Thread(target=run_bot_safe, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
