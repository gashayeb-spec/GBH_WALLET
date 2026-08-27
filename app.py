import os
import random
import sqlite3
from threading import Thread
import requests
import telebot
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPER_ADMIN_ID = str(os.environ.get("ADMIN_ID", "5351353727")).strip()
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://gbh-wallet.onrender.com")

admin_config = {
    "password": "admin123"
}

otp_store = {}

# --- DATABASE SETUP (SQLite) ---
DB_NAME = "database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. አባላት
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_no TEXT UNIQUE,
            first_name TEXT,
            father_name TEXT,
            grand_name TEXT,
            phone_number TEXT,
            address TEXT,
            tin_number TEXT,
            share_count INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            paid_amount REAL DEFAULT 0.0,
            approved_loan REAL DEFAULT 0.0,
            paid_loan REAL DEFAULT 0.0,
            telegram_id TEXT,
            id_card_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. አድሚኖች
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            admin_id TEXT PRIMARY KEY,
            password TEXT,
            role TEXT
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO admins (admin_id, password, role) VALUES (?, ?, 'super')", 
                   (SUPER_ADMIN_ID, admin_config["password"]))

    # 3. ወጪዎች
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT,
            amount REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 4. ሴቲንግ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            latest_draw_number TEXT DEFAULT 'ዙር 01',
            winner_name TEXT DEFAULT '-',
            latest_draw_date TEXT DEFAULT 'የለም',
            support_phone TEXT DEFAULT '0916039015'
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    
    conn.commit()
    conn.close()

init_db()

# --- ASYNC TELEGRAM MESSAGING ---
def send_async_msg(chat_id, text, reply_markup=None):
    def run():
        if bot and chat_id:
            try:
                bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="Markdown")
            except Exception as e:
                print(f"Async Message Error ({chat_id}):", e)
    Thread(target=run).start()

def send_async_admin_notification(member_id, ref_no, data):
    def run():
        if not bot or not SUPER_ADMIN_ID:
            return
            
        markup = telebot.types.InlineKeyboardMarkup()
        btn_approve = telebot.types.InlineKeyboardButton("✅ Approve", callback_data=f"ap_{member_id}")
        btn_cancel = telebot.types.InlineKeyboardButton("❌ Cancel", callback_data=f"can_{member_id}")
        btn_block = telebot.types.InlineKeyboardButton("🚫 Block", callback_data=f"blk_{member_id}")
        
        admin_panel_url = f"{WEB_APP_URL}/admin"
        btn_panel = telebot.types.InlineKeyboardButton("📊 የአድሚን ፓናል ክፈት", url=admin_panel_url)

        markup.add(btn_approve, btn_cancel, btn_block)
        markup.add(btn_panel)

        admin_msg = (
            f"🆕 **አዲስ የሰው ምዝገባ ጥያቄ!**\n\n"
            f"👤 **ስም፦** {data.get('first_name')} {data.get('father_name')} {data.get('grand_name')}\n"
            f"📞 **ስልክ፦** {data.get('phone_number')}\n"
            f"📍 **አድራሻ፦** {data.get('address')}\n"
            f"🆔 **TIN፦** {data.get('tin_number') if data.get('tin_number') else 'የለውም'}\n"
            f"🔢 **ዕድል ብዛት፦** {data.get('share_count', 1)}\n"
            f"🆔 **Ref No፦** `{ref_no}`\n"
            f"💬 **TG ID፦** `{data.get('telegram_id')}`"
        )
        try:
            bot.send_message(SUPER_ADMIN_ID, admin_msg, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            print("Admin Notification Error:", e)

    Thread(target=run).start()

# --- TELEGRAM BOT SETUP ---
bot = None
if BOT_TOKEN:
    try:
        bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

        @bot.message_handler(commands=['start'])
        def send_welcome(message):
            user_id = str(message.chat.id).strip()
            keyboard = telebot.types.InlineKeyboardMarkup()
            
            # የተጠቃሚ መተግበሪያ ቁልፍ
            web_app_info = telebot.types.WebAppInfo(url=WEB_APP_URL)
            btn_user = telebot.types.InlineKeyboardButton(text="📱 ተራመድ ሳኮ መተግበሪያን ክፈት", web_app=web_app_info)
            keyboard.add(btn_user)

            # ተጠቃሚው አድሚን ከሆነ የአድሚን ፓናል ቁልፍ ጨምርለት
            if user_id == SUPER_ADMIN_ID:
                admin_web_info = telebot.types.WebAppInfo(url=f"{WEB_APP_URL}/admin")
                btn_admin = telebot.types.InlineKeyboardButton(text="📊 የአድሚን ፓናል ክፈት", web_app=admin_web_info)
                keyboard.add(btn_admin)

            text = (
                "🌟 **እንኳን ወደ «ተራመድ ሳኮ» ዲጂታል የቁጠባና ብድር ህብረት ሥራ ማህበር በሰላም መጡ!** 🌟\n\n"
                "ወደ ተሻለ የፋይናንስ እድገትና የወደፊት ብልጽግና የሚወስድዎትን መንገድ ከእኛ ጋር ይጀምሩ! "
                "ተራመድ ሳኮ በአነስተኛ ወለድ ፈጣንና አውቶሜትድ የብድር እና የቁጠባ አገልግሎቶችን ያቀርባል።\n\n"
                "👇 **አሁኑኑ ለመመዝገብና አገልግሎቱን ለማግኘት ከታች ያለውን ቁልፍ ይጫኑ!**"
            )
            bot.send_message(message.chat.id, text, reply_markup=keyboard, parse_mode="Markdown")

        @bot.callback_query_handler(func=lambda call: call.data.startswith(('ap_', 'can_', 'blk_')))
        def handle_admin_action(call):
            try:
                prefix, member_id = call.data.split('_')
                member_id = int(member_id)
                status_map = {'ap': 'approved', 'can': 'cancelled', 'blk': 'blocked'}
                new_status = status_map[prefix]

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT telegram_id FROM members WHERE id = ?", (member_id,))
                member = cursor.fetchone()

                if member:
                    cursor.execute("UPDATE members SET status = ? WHERE id = ?", (member_id,))
                    conn.commit()

                    status_text = {'ap': '✅ **ተፅድቋል**', 'can': '❌ **ተሰርዟል**', 'blk': '🚫 **ታግዷል**'}
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=call.message.text + f"\n\n📌 **የአድሚን ውሳኔ፦** {status_text[prefix]}"
                    )

                    if member['telegram_id']:
                        user_msgs = {
                            "ap": "🎉 **ደስ ደስ ይበልዎት!** የምዝገባ ጥያቄዎ በአድሚኑ ፀድቋል።",
                            "can": "⚠️ **ማሳሰቢያ፦** የምዝገባ ጥያቄዎ አልተቀበለም።",
                            "blk": "🚫 **ማሳሰቢያ፦** መለያዎ በአድሚን ታግዷል።"
                        }
                        send_async_msg(member['telegram_id'], user_msgs[prefix])
                conn.close()
            except Exception as e:
                print("Callback Handling Error:", e)

    except Exception as e:
        print("Bot Initialization Error:", e)

def run_bot_safe():
    if bot:
        try:
            bot.remove_webhook()
        except Exception:
            pass
        try:
            print(">>> TELEGRAM BOT RUNNING SAFELY... <<<")
            bot.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
        except Exception as e:
            print("Bot Polling Error:", e)

# --- WEB ROUTES ---
@app.route('/', methods=['GET', 'HEAD'])
def home():
    return render_template('index.html')

@app.route('/admin', methods=['GET', 'HEAD'])
def admin_page():
    return render_template('admin.html')

# --- ADMIN API ENDPOINTS ---

@app.route('/api/admin/members', methods=['GET'])
def get_admin_members():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members ORDER BY id DESC")
    members = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(members), 200

@app.route('/api/admin/update_status', methods=['POST'])
def update_member_status():
    data = request.get_json(silent=True) or {}
    member_id = data.get('member_id')
    status = data.get('status') # 'approved', 'cancelled', 'blocked'

    if not member_id or status not in ['approved', 'cancelled', 'blocked']:
        return jsonify({"success": False, "message": "የተሳሳተ መረጃ!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE members SET status = ? WHERE id = ?", (status, member_id))
    cursor.execute("SELECT telegram_id FROM members WHERE id = ?", (member_id,))
    member = cursor.fetchone()
    conn.commit()
    conn.close()

    if member and member['telegram_id']:
        status_msgs = {
            "approved": "🎉 **ደስ ደስ ይበልዎት!** የምዝገባ ጥያቄዎ በአድሚኑ ፀድቋል።",
            "cancelled": "⚠️ **ማሳሰቢያ፦** የምዝገባ ጥያቄዎ አልተቀበለም።",
            "blocked": "🚫 **ማሳሰቢያ፦** መለያዎ በአድሚን ታግዷል።"
        }
        send_async_msg(member['telegram_id'], status_msgs[status])

    return jsonify({"success": True, "message": f"የተጠቃሚው ሁኔታ ወደ {status} ተቀይሯል!"}), 200

@app.route('/api/admin/remove_user', methods=['POST'])
def remove_user():
    data = request.get_json(silent=True) or {}
    member_id = data.get('member_id')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM members WHERE id = ?", (member_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "አባሉ በስኬት ተሰርዟል!"}), 200

@app.route('/api/admin/send_custom_msg', methods=['POST'])
def send_custom_msg():
    data = request.get_json(silent=True) or {}
    member_id = data.get('member_id')
    custom_msg = data.get('message', '').strip()

    if not custom_msg:
        return jsonify({"success": False, "message": "መልእክቱ ባዶ መሆን አይችልም!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id, first_name FROM members WHERE id = ?", (member_id,))
    member = cursor.fetchone()
    conn.close()

    if member and member['telegram_id']:
        formatted_text = f"📩 **ከአድሚን የተላከ መልእክት፦**\n\n{custom_msg}"
        send_async_msg(member['telegram_id'], formatted_text)
        return jsonify({"success": True, "message": "መልእክቱ ለተጠቃሚው በቴሌግራም ተልኳል!"}), 200
    else:
        return jsonify({"success": False, "message": "ተጠቃሚው Telegram ID የለውም!"}), 400

@app.route('/api/admin/set_loan', methods=['POST'])
def set_loan():
    data = request.get_json(silent=True) or {}
    member_id = data.get('member_id')
    approved_loan = float(data.get('approved_loan', 0))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE members SET approved_loan = ? WHERE id = ?", (approved_loan, member_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "የብድር መጠኑ በስኬት ተስተካክሏል!"}), 200

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json(silent=True) or {}
    admin_id = str(data.get('admin_id', '')).strip()
    password = str(data.get('pass', '')).strip()

    if admin_id == SUPER_ADMIN_ID:
        if password == admin_config["password"]:
            otp = str(random.randint(100000, 999999))
            otp_store[admin_id] = otp
            msg = f"🔐 **ተራመድ ሳኮ - Super Admin Login OTP**\n\nየመግቢያ ማረጋገጫ ኮድዎ፦ `{otp}`"
            send_async_msg(SUPER_ADMIN_ID, msg)
            return jsonify({"status": "otp_required", "message": "OTP ማረጋገጫ ኮድ ተልኳል!"}), 200
        else:
            return jsonify({"message": "የተሳሳተ የይለፍ ቃል!"}), 401

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admins WHERE admin_id = ? AND password = ?", (admin_id, password))
    target_admin = cursor.fetchone()
    conn.close()

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

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO admins (admin_id, password, role) VALUES (?, '123456', ?)", (admin_id, role))
    conn.commit()
    conn.close()

    msg = f"🎖 **አዲስ የአድሚን ስልጣን ተሰጥቶዎታል!**\n\nየስራ ድርሻዎ፦ **{role.upper()}**\nየመጀመሪያ የይለፍ ቃል፦ `123456`"
    send_async_msg(admin_id, msg)

    return jsonify({"message": f"አድሚን {admin_id} በ {role} ስልጣን ተሾሟል!"}), 200

@app.route('/api/admin/add_expense', methods=['POST'])
def add_expense():
    data = request.get_json(silent=True) or {}
    desc = data.get('description', '')
    amount = float(data.get('amount', 0))

    if not desc or amount <= 0:
        return jsonify({"message": "እባክዎን ትክክለኛ መረጃ ያስገቡ!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO expenses (description, amount) VALUES (?, ?)", (desc, amount))
    conn.commit()
    conn.close()

    return jsonify({"message": "ወጪው በስኬት ተመዝግቧል!"}), 200

@app.route('/api/register', methods=['POST'])
def register_member():
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()

        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM members")
        count = cursor.fetchone()[0]
        ref_no = f"TS-{(count + 1):03d}"

        cursor.execute('''
            INSERT INTO members (ref_no, first_name, father_name, grand_name, phone_number, address, tin_number, share_count, telegram_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (
            ref_no,
            data.get("first_name", ""),
            data.get("father_name", ""),
            data.get("grand_name", ""),
            data.get("phone_number", ""),
            data.get("address", ""),
            data.get("tin_number", ""),
            int(data.get("share_count", 1)),
            str(data.get("telegram_id", ""))
        ))
        
        member_id = cursor.lastrowid
        conn.commit()
        conn.close()

        send_async_admin_notification(member_id, ref_no, data)

        return jsonify({"success": True, "message": "ምዝገባዎ ተጠናቋል። ከአድሚን ማረጋገጫ ይጠብቁ!", "ref_no": ref_no}), 200

    except Exception as e:
        return jsonify({"success": False, "message": f"ምዝገባውን ማካሄድ አልተቻለም፦ {str(e)}"}), 500

# --- START BOT IN BACKGROUND ---
if bot:
    Thread(target=run_bot_safe, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
