import os
import sqlite3
import html
import threading
import time
import telebot
from telebot import types
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------
# Configurations
# ---------------------------------------------------------
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8416599811:AAGJEB4bu2fM1r76NnhfCEEo5ciFBJzh3i8").strip()
SUPER_ADMIN_ID = str(os.environ.get("ADMIN_ID", "5351353727")).strip()
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://gbh-wallet.onrender.com").strip()

DB_NAME = "database.db"

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

# ---------------------------------------------------------
# Database Setup
# ---------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_no TEXT UNIQUE,
            loan_series_no TEXT DEFAULT '',
            first_name TEXT,
            father_name TEXT,
            grand_name TEXT,
            country TEXT,
            phone_number TEXT,
            tin_number TEXT,
            national_id_path TEXT,
            trade_license_path TEXT,
            photo_path TEXT,
            status TEXT DEFAULT 'pending',
            paid_amount REAL DEFAULT 0.0,
            approved_loan REAL DEFAULT 0.0,
            paid_loan REAL DEFAULT 0.0,
            telegram_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def sanitize_input(text):
    if text is None: return ""
    return html.escape(str(text).strip())

# ---------------------------------------------------------
# TELEGRAM BOT HANDLERS
# ---------------------------------------------------------
if bot:
    @bot.message_handler(commands=['start', 'admin'])
    def send_welcome(message):
        try:
            user_id = str(message.from_user.id)
            markup = types.InlineKeyboardMarkup()
            
            web_app_info = types.WebAppInfo(url=WEB_APP_URL)
            web_btn = types.InlineKeyboardButton(text="📱 ምዝገባ / የኔ ደብተሮች", web_app=web_app_info)
            markup.add(web_btn)
            
            if user_id == SUPER_ADMIN_ID:
                admin_web_info = types.WebAppInfo(url=f"{WEB_APP_URL}/admin")
                admin_btn = types.InlineKeyboardButton(text="⚙️ የአድሚን ፓናል (Admin Panel)", web_app=admin_web_info)
                markup.add(admin_btn)
            
            welcome_msg = (
                f"ሰላም {message.from_user.first_name}! 👋\n\n"
                f"እንኳን ወደ **ተራመድ የቁጠባና ብድር ህብረት ስራ ማህበር** በሰላም መጡ።\n"
                f"የቁጠባ እና የብድር አገልግሎት ለማግኘት ከታች ያለውን ቁልፍ ይጫኑ።"
            )
            bot.send_message(message.chat.id, welcome_msg, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            print(f"Start command error: {e}")

    def run_bot_polling():
        while True:
            try:
                bot.remove_webhook()
                bot.infinity_polling(timeout=20, long_polling_timeout=10, skip_pending=True)
            except Exception as e:
                time.sleep(5)

    threading.Thread(target=run_bot_polling, daemon=True).start()

# ---------------------------------------------------------
# Web Routes
# ---------------------------------------------------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------
@app.route('/api/member/status', methods=['GET'])
def get_member_status():
    telegram_id = request.args.get('telegram_id')
    if not telegram_id:
        return jsonify({"exists": False, "admin_id": SUPER_ADMIN_ID})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members WHERE telegram_id = ?", (telegram_id,))
    member = cursor.fetchone()
    conn.close()

    if member:
        return jsonify({"exists": True, "member": dict(member), "admin_id": SUPER_ADMIN_ID})
    return jsonify({"exists": False, "admin_id": SUPER_ADMIN_ID})

@app.route('/api/payment/submit', methods=['POST'])
def submit_payment():
    try:
        req = request.form
        files = request.files

        pay_type = req.get('type') # 'savings' or 'loan'
        amount = req.get('amount')
        telegram_id = req.get('telegram_id')
        ref_no = req.get('ref_no')
        series_no = req.get('series_no', '')

        if 'receipt' not in files:
            return jsonify({"success": False, "message": "እባክዎን የባንክ ደረሰኝ ስክሪንሾት ያያይዙ!"}), 400

        receipt_file = files['receipt']
        filename = secure_filename(f"pay_{pay_type}_{ref_no}_{receipt_file.filename}")
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        receipt_file.save(save_path)

        if bot and SUPER_ADMIN_ID:
            if pay_type == "savings":
                type_str = "💰 የቁጠባ ገቢ ደረሰኝ"
                detail_str = f"<b>የቁጠባ ደብተር ቁጥር:</b> {ref_no}"
            else:
                type_str = "💳 የብድር ክፍያ ተመላሽ ደረሰኝ"
                detail_str = f"<b>የቁጠባ ደብተር:</b> {ref_no}\n<b>የብድር ሴሪ ቁጥር:</b> {series_no}"

            caption = (
                f"📥 <b>አዲስ የክፍያ ማረጋገጫ ተልኳል!</b>\n\n"
                f"<b>ዓይነት:</b> {type_str}\n"
                f"{detail_str}\n"
                f"<b>የተከፈለው መጠን:</b> {amount} ETB\n"
                f"<b>Telegram ID:</b> {telegram_id}"
            )
            with open(save_path, 'rb') as photo:
                bot.send_photo(SUPER_ADMIN_ID, photo, caption=caption, parse_mode="HTML")

        return jsonify({"success": True, "message": "የክፍያ ማረጋገጫው ለአድሚን በስኬት ተልኳል! አድሚኑ አረጋግጦ ሂሳብዎን ያዘምነዋል።"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/register', methods=['POST'])
def register_member():
    try:
        req = request.form
        files = request.files

        conn = get_db_connection()
        cursor = conn.cursor()
        
        telegram_id = sanitize_input(req.get('telegram_id'))
        if telegram_id:
            cursor.execute("SELECT id FROM members WHERE telegram_id = ?", (telegram_id,))
            if cursor.fetchone():
                conn.close()
                return jsonify({"success": False, "message": "በዚህ የቴሌግራም አካውንት ቀደም ብለው ተመዝግበዋል!"}), 400

        cursor.execute("SELECT COUNT(*) FROM members")
        count = cursor.fetchone()[0]
        ref_no = f"SAV-{(count + 1):03d}" # የቁጠባ ደብተር ቁጥር

        nat_id_path, trade_lic_path, photo_path = "", "", ""

        if 'national_id' in files and files['national_id'].filename != '':
            f = files['national_id']
            filename = secure_filename(f"{ref_no}_nid_{f.filename}")
            nat_id_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            f.save(nat_id_path)

        if 'user_photo' in files and files['user_photo'].filename != '':
            f = files['user_photo']
            filename = secure_filename(f"{ref_no}_photo_{f.filename}")
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            f.save(photo_path)

        if 'trade_license' in files and files['trade_license'].filename != '':
            f = files['trade_license']
            filename = secure_filename(f"{ref_no}_trade_{f.filename}")
            trade_lic_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            f.save(trade_lic_path)

        cursor.execute('''
            INSERT INTO members (
                ref_no, first_name, father_name, grand_name, country, 
                phone_number, tin_number, national_id_path, trade_license_path, 
                photo_path, telegram_id, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (
            ref_no, sanitize_input(req.get('first_name')), sanitize_input(req.get('father_name')),
            sanitize_input(req.get('grand_name')), sanitize_input(req.get('country')),
            sanitize_input(req.get('phone_number')), sanitize_input(req.get('tin_number')),
            nat_id_path, trade_lic_path, photo_path, telegram_id
        ))

        new_id = cursor.lastrowid
        conn.commit()
        conn.close()

        if bot and SUPER_ADMIN_ID:
            msg_text = (
                f"🆕 <b>አዲስ የአባልነት ምዝገባ!</b>\n\n"
                f"<b>የቁጠባ ደብተር No:</b> {ref_no}\n"
                f"<b>ስም:</b> {req.get('first_name')} {req.get('father_name')}\n"
                f"<b>ስልክ:</b> {req.get('phone_number')}"
            )
            bot.send_message(SUPER_ADMIN_ID, msg_text, parse_mode="HTML")

        return jsonify({"success": True, "message": "ምዝገባዎ በስኬት ተልኳል! አድሚኑ ሲያጸድቀው ደብተሮችዎ ይከፈታሉ።"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/members', methods=['GET'])
def get_admin_members():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members ORDER BY id DESC")
    members = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "members": members}), 200

@app.route('/api/admin/update_status', methods=['POST'])
def update_status():
    try:
        data = request.get_json(silent=True) or {}
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE members SET status = ? WHERE id = ?", (data.get('status'), data.get('member_id')))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "የአባሉ ሁኔታ በስኬት ተቀይሯል!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/update_financials', methods=['POST'])
def update_financials():
    try:
        data = request.get_json(silent=True) or {}
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE members 
            SET paid_amount = ?, approved_loan = ?, paid_loan = ?, loan_series_no = ?
            WHERE id = ?
        ''', (
            float(data.get('paid_amount', 0)), 
            float(data.get('approved_loan', 0)), 
            float(data.get('paid_loan', 0)),
            data.get('loan_series_no', ''),
            data.get('member_id')
        ))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "የደብተር እና የፋይናንስ መረጃው በስኬት ተዘምኗል!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
