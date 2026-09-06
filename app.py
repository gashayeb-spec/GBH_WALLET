import os
import sqlite3
import html
import threading
import time
import random
import telebot
from telebot import types
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# ---------------------------------------------------------
# Configurations & Persistent Paths (Render Storage Safe)
# ---------------------------------------------------------
# Render ላይ Persistent Disk Attach ከተደረገ Path ው /var/data ነው
DATA_DIR = os.environ.get("DATA_DIR", "/var/data" if os.path.exists("/var/data") else ".")
os.makedirs(DATA_DIR, exist_ok=True)

UPLOAD_FOLDER = os.path.join(DATA_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
SUPER_ADMIN_ID = str(os.environ.get("ADMIN_ID", "5351353727")).strip()
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://gbh-wallet.onrender.com").strip()
DEFAULT_ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin123").strip()

# SQLite Database path inside Persistent Directory
DB_NAME = os.path.join(DATA_DIR, "database.db")
DATABASE_URL = os.environ.get("DATABASE_URL")

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def format_file_url(path):
    if not path:
        return ""
    filename = os.path.basename(path)
    return f"/uploads/{filename}"

def sanitize_input(text):
    if text is None: return ""
    return html.escape(str(text).strip())

# ---------------------------------------------------------
# Route for Serving Uploaded Files
# ---------------------------------------------------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---------------------------------------------------------
# Database Connection Manager (Supports SQLite & PostgreSQL)
# ---------------------------------------------------------
def get_db_connection():
    if DATABASE_URL:
        import psycopg2
        import psycopg2.extras
        # Fix Render dialect name if needed (postgres:// -> postgresql://)
        pg_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(pg_url, cursor_factory=psycopg2.extras.DictCursor)
        return conn
    else:
        conn = sqlite3.connect(DB_NAME, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    is_postgres = bool(DATABASE_URL)
    auto_inc = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
    timestamp_type = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS members (
            id {auto_inc},
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
            created_at {timestamp_type}
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS receipts (
            id {auto_inc},
            member_id INTEGER,
            ref_no TEXT,
            pay_type TEXT,
            amount REAL,
            receipt_path TEXT,
            status TEXT DEFAULT 'pending',
            created_at {timestamp_type},
            FOREIGN KEY (member_id) REFERENCES members (id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS messages (
            id {auto_inc},
            ref_no TEXT,
            sender TEXT,
            message_text TEXT,
            created_at {timestamp_type}
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS announcements (
            id {auto_inc},
            title TEXT,
            content TEXT,
            status TEXT DEFAULT 'active',
            created_at {timestamp_type}
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS admins (
            id {auto_inc},
            telegram_id TEXT UNIQUE,
            full_name TEXT,
            role_sector TEXT,
            created_at {timestamp_type}
        )
    ''')

    cursor.execute("SELECT value FROM settings WHERE key = 'bank_account'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO settings (key, value) VALUES ('bank_account', %s)" if is_postgres else "INSERT INTO settings (key, value) VALUES ('bank_account', ?)", 
                       ('1000070780201 - ኢትዮጵያ ንግድ ባንክ (ጋሻዬ በጅጉ)',))

    cursor.execute("SELECT value FROM settings WHERE key = 'admin_password'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO settings (key, value) VALUES ('admin_password', %s)" if is_postgres else "INSERT INTO settings (key, value) VALUES ('admin_password', ?)", (DEFAULT_ADMIN_PASS,))

    conn.commit()
    conn.close()

init_db()

# Helper for SQL Parameter Substitution
def q(query):
    if DATABASE_URL:
        return query.replace('?', '%s')
    return query

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
            
            is_admin = False
            if user_id == SUPER_ADMIN_ID:
                is_admin = True
            else:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(q("SELECT id FROM admins WHERE telegram_id = ?"), (user_id,))
                if cursor.fetchone():
                    is_admin = True
                conn.close()

            if is_admin:
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

    @bot.callback_query_handler(func=lambda call: True)
    def callback_inline(call):
        try:
            data = call.data.split(":")
            action = data[0]
            
            if action in ["approve_member", "cancel_member"]:
                member_id = data[1]
                new_status = "approved" if action == "approve_member" else "rejected"
                
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(q("UPDATE members SET status = ? WHERE id = ?"), (new_status, member_id))
                conn.commit()
                conn.close()
                
                status_txt = "✅ አባልነቱ ጸድቋል!" if new_status == "approved" else "❌ አባልነቱ ተሰርዟል!"
                bot.answer_callback_query(call.id, status_txt)
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                                         caption=f"{call.message.caption}\n\n<b>ውሳኔ:</b> {status_txt}", parse_mode="HTML")
            
            elif action in ["approve_pay", "cancel_pay"]:
                receipt_id = data[1]

                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(q("SELECT * FROM receipts WHERE id = ?"), (receipt_id,))
                receipt = cursor.fetchone()

                if receipt and receipt['status'] == 'pending':
                    try:
                        if action == "approve_pay":
                            if receipt['pay_type'] == "savings":
                                cursor.execute(q("UPDATE members SET paid_amount = paid_amount + ? WHERE id = ?"), (receipt['amount'], receipt['member_id']))
                            else:
                                cursor.execute(q("UPDATE members SET paid_loan = paid_loan + ? WHERE id = ?"), (receipt['amount'], receipt['member_id']))
                            
                            cursor.execute(q("UPDATE receipts SET status = 'approved' WHERE id = ?"), (receipt_id,))
                            conn.commit()
                            bot.answer_callback_query(call.id, "✅ ክፍያው ተቀባይነት አግኝቶ ደብተሩ ተዘምኗል!")
                            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                                                     caption=f"{call.message.caption}\n\n<b>ውሳኔ:</b> ✅ ክፍያው ጸድቋል (ደብተሩ ተዘምኗል)", parse_mode="HTML")
                        
                        elif action == "cancel_pay":
                            cursor.execute(q("UPDATE receipts SET status = 'rejected' WHERE id = ?"), (receipt_id,))
                            conn.commit()
                            bot.answer_callback_query(call.id, "❌ ክፍያው ውድቅ ተደርጓል!")
                            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                                                     caption=f"{call.message.caption}\n\n<b>ውሳኔ:</b> ❌ ክፍያው ውድቅ ተደርጓል", parse_mode="HTML")
                    except Exception as tx_err:
                        conn.rollback()
                        print(f"Transaction failed: {tx_err}")
                conn.close()
        except Exception as e:
            print(f"Callback error: {e}")

    def run_bot_polling():
        while True:
            try:
                bot.remove_webhook()
                bot.infinity_polling(timeout=20, long_polling_timeout=10, skip_pending=True)
            except Exception as e:
                time.sleep(5)

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        threading.Thread(target=run_bot_polling, daemon=True).start()

# ---------------------------------------------------------
# Admin Authentication Endpoints
# ---------------------------------------------------------
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    try:
        data = request.get_json(silent=True) or {}
        password = data.get('password', '').strip()

        if not password:
            return jsonify({"success": False, "status": "error", "message": "እባክዎን የይለፍ ቃል ያስገቡ!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(q("SELECT value FROM settings WHERE key = 'admin_password'"))
        row = cursor.fetchone()
        conn.close()

        stored_pass = row['value'] if row else DEFAULT_ADMIN_PASS

        if password == stored_pass:
            return jsonify({"success": True, "status": "success", "message": "በስኬት ገብተዋል!"}), 200
        else:
            return jsonify({"success": False, "status": "error", "message": "የተሳሳተ የይለፍ ቃል አስገብተዋል!"}), 401
    except Exception as e:
        return jsonify({"success": False, "status": "error", "message": str(e)}), 500

# ---------------------------------------------------------
# Direct OTP Sending API
# ---------------------------------------------------------
@app.route('/api/admin/send-otp', methods=['POST'])
@app.route('/api/send-otp', methods=['POST'])
def send_admin_otp():
    try:
        data = request.get_json(silent=True) or {}
        
        target_telegram_id = str(
            data.get('telegram_id') or 
            data.get('admin_id') or 
            data.get('chat_id') or 
            data.get('user_id') or 
            SUPER_ADMIN_ID
        ).strip()

        if not target_telegram_id:
            return jsonify({
                "success": False, 
                "status": "error", 
                "message": "የቴሌግራም User ID አልተገኘም!"
            }), 400

        if not bot:
            return jsonify({
                "success": False, 
                "status": "error", 
                "message": "የቴሌግራም ቦት አልተጀመረም! BOT_TOKEN መዋቀሩን ያረጋግጡ።"
            }), 400

        otp_code = str(random.randint(100000, 999999))

        conn = get_db_connection()
        cursor = conn.cursor()
        
        upsert_query = (
            "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            if DATABASE_URL else
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)"
        )
        
        cursor.execute(upsert_query, ('admin_otp', otp_code))
        cursor.execute(upsert_query, ('admin_otp_time', str(int(time.time()))))
        conn.commit()
        conn.close()

        msg = f"🔑 <b>የአድሚን ማረጋገጫ OTP ኮድ:</b>\n\n<code>{otp_code}</code>\n\nይህንን ኮድ በመጠቀም የይለፍ ቃልዎን መቀየር ይችላሉ።"
        
        try:
            bot.send_message(chat_id=target_telegram_id, text=msg, parse_mode="HTML")
        except Exception as telegram_err:
            print(f"Telegram Send Message Error: {telegram_err}")
            return jsonify({
                "success": False, 
                "status": "error", 
                "message": f"OTP መላክ አልተቻለም! ቦቱን በቴሌግራም /start ማድረጎትን ያረጋግጡ። (User ID: {target_telegram_id})"
            }), 400

        return jsonify({"success": True, "status": "success", "message": "OTP ኮድ ቀጥታ ወደ ቴሌግራምዎ ተልኳል!"}), 200

    except Exception as e:
        print(f"General Send OTP Error: {e}")
        return jsonify({"success": False, "status": "error", "message": f"የውስጥ ሰርቨር ስህተት: {str(e)}"}), 500

# ---------------------------------------------------------
# Password Change Endpoint
# ---------------------------------------------------------
@app.route('/api/admin/change-password', methods=['POST'])
@app.route('/api/change-password', methods=['POST'])
def change_admin_password():
    try:
        data = request.get_json(silent=True) or {}
        
        otp_input = str(data.get('otp') or data.get('otp_code') or "").strip()
        new_password = str(data.get('new_password') or data.get('password') or "").strip()
        confirm_password = str(data.get('confirm_password') or data.get('confirm_new_password') or "").strip()
        old_password = str(data.get('old_password') or "").strip()

        if not new_password:
            return jsonify({"success": False, "status": "error", "message": "እባክዎን አዲሱን የይለፍ ቃል ያስገቡ!"}), 400

        if confirm_password and new_password != confirm_password:
            return jsonify({"success": False, "status": "error", "message": "አዲሱ የይለፍ ቃል እና ማረጋገጫው አይመሳሰሉም!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        if old_password:
            cursor.execute(q("SELECT value FROM settings WHERE key = 'admin_password'"))
            row = cursor.fetchone()
            stored_pass = row['value'] if row else DEFAULT_ADMIN_PASS
            if old_password != stored_pass:
                conn.close()
                return jsonify({"success": False, "status": "error", "message": "የድሮው የይለፍ ቃል የተሳሳተ ነው!"}), 400

        elif otp_input:
            cursor.execute(q("SELECT value FROM settings WHERE key = 'admin_otp'"))
            otp_row = cursor.fetchone()

            if not otp_row or str(otp_row['value']).strip() != otp_input:
                conn.close()
                return jsonify({"success": False, "status": "error", "message": "የተሳሳተ OTP ኮድ አስገብተዋል!"}), 400
        else:
            conn.close()
            return jsonify({"success": False, "status": "error", "message": "እባክዎን የተላከልዎትን OTP ኮድ ያስገቡ!"}), 400

        upsert_query = (
            "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            if DATABASE_URL else
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)"
        )
        cursor.execute(upsert_query, ('admin_password', new_password))
        cursor.execute(q("DELETE FROM settings WHERE key = 'admin_otp'"))
        cursor.execute(q("DELETE FROM settings WHERE key = 'admin_otp_time'"))
        conn.commit()
        conn.close()

        return jsonify({"success": True, "status": "success", "message": "የይለፍ ቃሉ በስኬት ተቀይሯል!"}), 200

    except Exception as e:
        return jsonify({"success": False, "status": "error", "message": f"ስህተት ተከሰተ: {str(e)}"}), 500

# ---------------------------------------------------------
# Web Page & Core API Routes
# ---------------------------------------------------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@app.route('/api/member/status', methods=['GET'])
def get_member_status():
    telegram_id = request.args.get('telegram_id')
    if not telegram_id:
        return jsonify({"exists": False, "admin_id": SUPER_ADMIN_ID})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(q("SELECT * FROM members WHERE telegram_id = ?"), (telegram_id,))
    row = cursor.fetchone()

    if row:
        member = dict(row)
        member['national_id_path'] = format_file_url(member.get('national_id_path'))
        member['trade_license_path'] = format_file_url(member.get('trade_license_path'))
        member['photo_path'] = format_file_url(member.get('photo_path'))
        
        cursor.execute(q("SELECT COUNT(*) FROM receipts WHERE member_id = ? AND pay_type = 'loan' AND status = 'pending'"), (member['id'],))
        pending_loan_receipts = cursor.fetchone()[0]
        member['has_pending_loan_receipt'] = True if pending_loan_receipts > 0 else False

        conn.close()
        return jsonify({"exists": True, "member": member, "admin_id": SUPER_ADMIN_ID})
    
    conn.close()
    return jsonify({"exists": False, "admin_id": SUPER_ADMIN_ID})

@app.route('/api/settings/bank', methods=['GET'])
def get_bank_account():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(q("SELECT value FROM settings WHERE key = 'bank_account'"))
    row = cursor.fetchone()
    conn.close()
    bank_info = row['value'] if row else "1000070780201 - ኢትዮጵያ ንግድ ባንክ (ጋሻዬ በጅጉ)"
    return jsonify({"bank_account": bank_info})

@app.route('/api/admin/settings/bank', methods=['POST'])
def set_bank_account():
    try:
        data = request.get_json(silent=True) or {}
        bank_info = data.get('bank_account', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        upsert_query = (
            "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            if DATABASE_URL else
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)"
        )
        cursor.execute(upsert_query, ('bank_account', bank_info))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "የባንክ ሂሳብ መረጃው ተዘምኗል!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/payment/submit', methods=['POST'])
def submit_payment():
    try:
        req = request.form
        files = request.files

        pay_type = req.get('type')
        amount = float(req.get('amount', 0))
        ref_no = req.get('ref_no')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(q("SELECT * FROM members WHERE ref_no = ?"), (ref_no,))
        member = cursor.fetchone()

        if not member:
            conn.close()
            return jsonify({"success": False, "message": "አባሉ አልተገኘም!"}), 404

        if 'receipt' not in files or files['receipt'].filename == '':
            conn.close()
            return jsonify({"success": False, "message": "እባክዎን የባንክ ደረሰኝ ስክሪንሾት ያያይዙ!"}), 400

        receipt_file = files['receipt']
        if not allowed_file(receipt_file.filename):
            conn.close()
            return jsonify({"success": False, "message": "የተሳሳተ የፋይል ዓይነት! (png, jpg, jpeg, pdf ብቻ)"}), 400

        filename = secure_filename(f"pay_{pay_type}_{ref_no}_{receipt_file.filename}")
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        receipt_file.save(save_path)

        cursor.execute(q('''
            INSERT INTO receipts (member_id, ref_no, pay_type, amount, receipt_path, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        '''), (member['id'], ref_no, pay_type, amount, save_path))
        
        receipt_id = cursor.lastrowid if not DATABASE_URL else None
        if DATABASE_URL:
            cursor.execute("SELECT LASTVAL()")
            receipt_id = cursor.fetchone()[0]

        conn.commit()
        conn.close()

        if bot and SUPER_ADMIN_ID:
            type_str = "💰 የቁጠባ ገቢ" if pay_type == "savings" else "💳 የብድር ክፍያ ተመላሽ"
            caption = (
                f"📥 <b>አዲስ የክፍያ ማረጋገጫ ተልኳል!</b>\n\n"
                f"👤 <b>አባል:</b> {member['first_name']} {member['father_name']}\n"
                f"📞 <b>ስልክ:</b> {member['phone_number']}\n"
                f"🆔 <b>የቁጠባ No:</b> {member['ref_no']}\n"
                f"🔢 <b>የብድር ሴሪ:</b> {member['loan_series_no'] or 'የለውም'}\n"
                f"💵 <b>የተከፈለው መጠን:</b> {amount} ETB\n"
                f"📌 <b>ዓይነት:</b> {type_str}"
            )
            
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Approve (አጽድቅ)", callback_data=f"approve_pay:{receipt_id}"),
                types.InlineKeyboardButton("❌ Cancel (ሰርዝ)", callback_data=f"cancel_pay:{receipt_id}")
            )

            with open(save_path, 'rb') as photo:
                bot.send_photo(SUPER_ADMIN_ID, photo, caption=caption, reply_markup=markup, parse_mode="HTML")

        return jsonify({"success": True, "message": "የክፍያ ማረጋገጫው ለአድሚን በስኬት ተልኳል!"}), 200
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
            cursor.execute(q("SELECT id FROM members WHERE telegram_id = ?"), (telegram_id,))
            if cursor.fetchone():
                conn.close()
                return jsonify({"success": False, "message": "በዚህ የቴሌግራም አካውንት ቀደም ብለው ተመዝግበዋል!"}), 400

        cursor.execute("SELECT COUNT(*) FROM members")
        count = cursor.fetchone()[0]
        ref_no = f"SAV-{(count + 1):03d}"

        nat_id_path, trade_lic_path, photo_path = "", "", ""

        if 'national_id' in files and files['national_id'].filename != '':
            f = files['national_id']
            if allowed_file(f.filename):
                filename = secure_filename(f"{ref_no}_nid_{f.filename}")
                nat_id_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                f.save(nat_id_path)

        if 'user_photo' in files and files['user_photo'].filename != '':
            f = files['user_photo']
            if allowed_file(f.filename):
                filename = secure_filename(f"{ref_no}_photo_{f.filename}")
                photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                f.save(photo_path)

        if 'trade_license' in files and files['trade_license'].filename != '':
            f = files['trade_license']
            if allowed_file(f.filename):
                filename = secure_filename(f"{ref_no}_trade_{f.filename}")
                trade_lic_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                f.save(trade_lic_path)

        cursor.execute(q('''
            INSERT INTO members (
                ref_no, first_name, father_name, grand_name, country, 
                phone_number, tin_number, national_id_path, trade_license_path, 
                photo_path, telegram_id, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        '''), (
            ref_no, sanitize_input(req.get('first_name')), sanitize_input(req.get('father_name')),
            sanitize_input(req.get('grand_name')), sanitize_input(req.get('country')),
            sanitize_input(req.get('phone_number')), sanitize_input(req.get('tin_number')),
            nat_id_path, trade_lic_path, photo_path, telegram_id
        ))

        new_id = cursor.lastrowid if not DATABASE_URL else None
        if DATABASE_URL:
            cursor.execute("SELECT LASTVAL()")
            new_id = cursor.fetchone()[0]

        conn.commit()
        conn.close()

        if bot and SUPER_ADMIN_ID:
            msg_text = (
                f"🆕 <b>አዲስ የአባልነት ምዝገባ!</b>\n\n"
                f"<b>የቁጠባ ደብተር No:</b> {ref_no}\n"
                f"<b>ስም:</b> {req.get('first_name')} {req.get('father_name')}\n"
                f"<b>ስልክ:</b> {req.get('phone_number')}"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_member:{new_id}"),
                types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_member:{new_id}")
            )
            bot.send_message(SUPER_ADMIN_ID, msg_text, reply_markup=markup, parse_mode="HTML")

        return jsonify({"success": True, "message": "ምዝገባዎ በስኬት ተልኳል! አድሚኑ ሲያጸድቀው ደብተሮችዎ ይከፈታሉ።"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/members', methods=['GET'])
def get_admin_members():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members ORDER BY id DESC")
    members = []
    for row in cursor.fetchall():
        m = dict(row)
        m['national_id_path'] = format_file_url(m.get('national_id_path'))
        m['trade_license_path'] = format_file_url(m.get('trade_license_path'))
        m['photo_path'] = format_file_url(m.get('photo_path'))
        members.append(m)
    conn.close()
    return jsonify({"status": "success", "members": members}), 200

@app.route('/api/admin/receipts', methods=['GET'])
def get_admin_receipts():
    pay_type = request.args.get('type')
    date_str = request.args.get('date')

    conn = get_db_connection()
    cursor = conn.cursor()

    query = '''
        SELECT r.*, m.first_name, m.father_name, m.phone_number 
        FROM receipts r
        JOIN members m ON r.member_id = m.id
        WHERE 1=1
    '''
    params = []

    if pay_type:
        query += " AND r.pay_type = " + ("%s" if DATABASE_URL else "?")
        params.append(pay_type)
    
    if date_str:
        query += " AND DATE(r.created_at) = DATE(" + ("%s" if DATABASE_URL else "?") + ")"
        params.append(date_str)

    query += " ORDER BY r.id DESC"

    cursor.execute(query, params)
    receipts = []
    for row in cursor.fetchall():
        rc = dict(row)
        rc['receipt_path'] = format_file_url(rc.get('receipt_path'))
        receipts.append(rc)
    conn.close()

    return jsonify({"status": "success", "receipts": receipts}), 200

@app.route('/api/admin/receipt/action', methods=['POST'])
def process_receipt_action():
    try:
        data = request.get_json(silent=True) or {}
        receipt_id = data.get('receipt_id')
        action = data.get('action')

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(q("SELECT * FROM receipts WHERE id = ?"), (receipt_id,))
        receipt = cursor.fetchone()

        if not receipt:
            conn.close()
            return jsonify({"status": "error", "message": "ደረሰኙ አልተገኘም!"}), 404

        if receipt['status'] != 'pending':
            conn.close()
            return jsonify({"status": "error", "message": "ይህ ደረሰኝ ቀደም ብሎ ውሳኔ አግኝቷል!"}), 400

        try:
            if action == 'approve':
                if receipt['pay_type'] == 'savings':
                    cursor.execute(q("UPDATE members SET paid_amount = paid_amount + ? WHERE id = ?"), (receipt['amount'], receipt['member_id']))
                else:
                    cursor.execute(q("UPDATE members SET paid_loan = paid_loan + ? WHERE id = ?"), (receipt['amount'], receipt['member_id']))
                
                cursor.execute(q("UPDATE receipts SET status = 'approved' WHERE id = ?"), (receipt_id,))
                msg = "ክፍያው በስኬት ጸድቋል፤ የደብተር ሂሳቡ ተዘምኗል!"
            else:
                cursor.execute(q("UPDATE receipts SET status = 'rejected' WHERE id = ?"), (receipt_id,))
                msg = "ክፍያው ውድቅ ተደርጓል!"

            conn.commit()
        except Exception as tx_err:
            conn.rollback()
            conn.close()
            return jsonify({"status": "error", "message": f"የሂሳብ ዝማኔው አልተሳካም: {str(tx_err)}"}), 500

        conn.close()
        return jsonify({"status": "success", "message": msg}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/analytics', methods=['GET'])
def get_admin_analytics():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM members")
    total_members = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM members WHERE status = 'pending'")
    pending_members = cursor.fetchone()[0]

    date_fn = "CURRENT_DATE" if DATABASE_URL else "DATE('now')"

    cursor.execute(f"SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND DATE(created_at) = {date_fn}")
    daily_income = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND created_at >= CURRENT_DATE - INTERVAL '7 days'" if DATABASE_URL else "SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND DATE(created_at) >= DATE('now', '-7 days')")
    weekly_income = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND created_at >= DATE_TRUNC('month', CURRENT_DATE)" if DATABASE_URL else "SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND DATE(created_at) >= DATE('now', 'start of month')")
    monthly_income = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND created_at >= DATE_TRUNC('year', CURRENT_DATE)" if DATABASE_URL else "SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND DATE(created_at) >= DATE('now', 'start of year')")
    yearly_income = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        "status": "success",
        "analytics": {
            "total_members": total_members,
            "pending_members": pending_members,
            "daily_income": daily_income,
            "weekly_income": weekly_income,
            "monthly_income": monthly_income,
            "yearly_income": yearly_income
        }
    }), 200

@app.route('/api/admin/update_status', methods=['POST'])
def update_status():
    try:
        data = request.get_json(silent=True) or {}
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(q("UPDATE members SET status = ? WHERE id = ?"), (data.get('status'), data.get('member_id')))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "የአባሉ ሁኔታ በስኬት ተቀይሯል!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/update_financials', methods=['POST'])
def update_financials():
    try:
        data = request.get_json(silent=True) or {}
        member_id = data.get('member_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()

        deduct_savings = float(data.get('deduct_savings', 0))
        deduct_loan = float(data.get('deduct_loan', 0))

        if deduct_savings > 0 or deduct_loan > 0:
            cursor.execute(q('''
                UPDATE members 
                SET paid_amount = CASE WHEN paid_amount - ? < 0 THEN 0 ELSE paid_amount - ? END,
                    paid_loan = paid_loan + ?
                WHERE id = ?
            '''), (deduct_savings, deduct_savings, deduct_loan, member_id))
        else:
            cursor.execute(q('''
                UPDATE members 
                SET paid_amount = ?, approved_loan = ?, paid_loan = ?, loan_series_no = ?
                WHERE id = ?
            '''), (
                float(data.get('paid_amount', 0)), 
                float(data.get('approved_loan', 0)), 
                float(data.get('paid_loan', 0)),
                data.get('loan_series_no', ''),
                member_id
            ))

        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "የአባሉ ደብተር በስኬት ተዘምኗል!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/delete_member', methods=['POST'])
def delete_member():
    try:
        data = request.get_json(silent=True) or {}
        member_id = data.get('member_id')
        
        if not member_id:
            return jsonify({"status": "error", "message": "የአባል ID አልተገለጸም!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(q("SELECT ref_no FROM members WHERE id = ?"), (member_id,))
        row = cursor.fetchone()
        if row:
            ref_no = row['ref_no']
            cursor.execute(q("DELETE FROM receipts WHERE member_id = ?"), (member_id,))
            cursor.execute(q("DELETE FROM messages WHERE ref_no = ?"), (ref_no,))
            cursor.execute(q("DELETE FROM members WHERE id = ?"), (member_id,))
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "message": "አባሉና የተያያዙ ፋይሎቹ ሙሉ በሙሉ ተሰርዘዋል!"}), 200

        conn.close()
        return jsonify({"status": "error", "message": "አባሉ አልተገኘም!"}), 404

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/messages/send', methods=['POST'])
def send_message():
    try:
        data = request.get_json(silent=True) or {}
        ref_no = sanitize_input(data.get('ref_no'))
        sender = sanitize_input(data.get('sender'))
        msg_text = sanitize_input(data.get('message_text'))

        if not ref_no or not msg_text:
            return jsonify({"status": "error", "message": "ያልተሟላ መረጃ!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(q('''
            INSERT INTO messages (ref_no, sender, message_text)
            VALUES (?, ?, ?)
        '''), (ref_no, sender, msg_text))
        conn.commit()

        if sender == 'admin' and bot:
            cursor.execute(q("SELECT telegram_id, first_name FROM members WHERE ref_no = ?"), (ref_no,))
            mem = cursor.fetchone()
            if mem and mem['telegram_id']:
                try:
                    bot.send_message(
                        mem['telegram_id'], 
                        f"📩 <b>አዲስ መልእክት ከአድሚን!</b>\n\n{msg_text}\n\n👉 ለመመለስ ሚኒ አፑን ይክፈቱ።", 
                        parse_mode="HTML"
                    )
                except Exception as t_err:
                    print("Telegram notification error:", t_err)

        conn.close()
        return jsonify({"status": "success", "message": "መልእክቱ ተልኳል!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/messages/get', methods=['GET'])
def get_messages():
    try:
        ref_no = request.args.get('ref_no')
        if not ref_no:
            return jsonify({"status": "error", "message": "Ref No አልተጠቀሰም!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(q("SELECT * FROM messages WHERE ref_no = ? ORDER BY id ASC"), (ref_no,))
        messages = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return jsonify({"status": "success", "messages": messages}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/admin/borrowers/status', methods=['GET'])
def get_borrowers_status():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM members WHERE approved_loan > 0 ORDER BY id DESC")
        borrowers = [dict(row) for row in cursor.fetchall()]
        
        categorized = []
        for b in borrowers:
            approved = float(b.get('approved_loan', 0))
            paid = float(b.get('paid_loan', 0))
            remaining = approved - paid
            
            if remaining <= 0:
                health_status = "fully_paid"
                status_label = "✅ ብድሩን ሙሉ በሙሉ የጨረሰ"
            elif paid > 0:
                health_status = "good"
                status_label = "🟢 ክፍያ በአግባቡ እየከፈለ ያለ"
            else:
                health_status = "pending_start"
                status_label = "⚠️ ክፍያ ያልጀመረ / የዘገየ"

            b_info = dict(b)
            b_info['remaining_loan'] = remaining
            b_info['health_status'] = health_status
            b_info['status_label'] = status_label
            categorized.append(b_info)

        conn.close()
        return jsonify({"status": "success", "borrowers": categorized}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ---------------------------------------------------------
# Sub-Admin Role Assignment Endpoint (Fixed & Flexible)
# ---------------------------------------------------------
@app.route('/api/admin/roles/assign', methods=['POST'])
@app.route('/assign-sub-admin', methods=['POST'])
def assign_sub_admin_role():
    try:
        data = request.get_json(silent=True) or {}
        
        # Frontend በልዩ ልዩ ስም ቢልካቸው እንኳን በአንድ ላይ ማስተናገድ
        telegram_id = sanitize_input(data.get('telegram_id') or data.get('admin_id') or data.get('user_id'))
        full_name = sanitize_input(data.get('full_name') or data.get('name'))
        role_sector = sanitize_input(data.get('role_sector') or data.get('role') or data.get('sector'))

        if not telegram_id or not full_name:
            return jsonify({
                "success": False,
                "status": "error", 
                "message": "እባክዎን የቴሌግራም ID እና ሙሉ ስም ያስገቡ!"
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        
        if DATABASE_URL:
            upsert_query = """
                INSERT INTO admins (telegram_id, full_name, role_sector) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (telegram_id) 
                DO UPDATE SET full_name = EXCLUDED.full_name, role_sector = EXCLUDED.role_sector
            """
            cursor.execute(upsert_query, (telegram_id, full_name, role_sector))
        else:
            cursor.execute(q("SELECT id FROM admins WHERE telegram_id = ?"), (telegram_id,))
            exists = cursor.fetchone()
            if exists:
                cursor.execute(q("UPDATE admins SET full_name = ?, role_sector = ? WHERE telegram_id = ?"), (full_name, role_sector, telegram_id))
            else:
                cursor.execute(q("INSERT INTO admins (telegram_id, full_name, role_sector) VALUES (?, ?, ?)"), (telegram_id, full_name, role_sector))

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "status": "success", 
            "message": f"{full_name} በስኬት ንኡስ አድሚን ሆነው ተሾመዋል!"
        }), 200
    except Exception as e:
        print(f"Error in assign_sub_admin_role: {e}")
        return jsonify({
            "success": False,
            "status": "error", 
            "message": f"ስህተት ተከሰተ: {str(e)}"
        }), 500

@app.route('/api/admin/announcement', methods=['POST'])
def create_announcement():
    try:
        data = request.get_json(silent=True) or {}
        title = data.get('title', '').strip()
        content = data.get('content', '').strip() or data.get('message', '').strip()

        if not title:
            title = "📢 ከአድሚን የተላከ ማስታወቂያ"

        if not content:
            return jsonify({"status": "error", "message": "እባክዎን የማስታወቂያውን ዝርዝር መልእክት ያስገቡ!"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("UPDATE announcements SET status = 'disabled'")
        cursor.execute(q("INSERT INTO announcements (title, content, status) VALUES (?, ?, 'active')"), (title, content))
        conn.commit()

        if bot:
            cursor.execute("SELECT telegram_id FROM members WHERE telegram_id IS NOT NULL AND telegram_id != ''")
            members = cursor.fetchall()
            broadcast_msg = f"📢 <b>{title}</b>\n\n{content}"
            
            def send_broadcast():
                for m in members:
                    try:
                        bot.send_message(m['telegram_id'], broadcast_msg, parse_mode="HTML")
                        time.sleep(0.05)
                    except Exception:
                        pass

            threading.Thread(target=send_broadcast, daemon=True).start()

        conn.close()

        return jsonify({"status": "success", "message": "ማስታወቂያው በስኬት ለሁሉም አባላት ተሰራጭቷል!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/announcements', methods=['GET'])
@app.route('/api/get_announcements', methods=['GET'])
@app.route('/api/announcement', methods=['GET'])
def get_active_announcements():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM announcements WHERE status = 'active' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        
        if not row:
            cursor.execute("SELECT * FROM announcements ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()

        conn.close()

        if row:
            ann_data = dict(row)
            return jsonify({
                "status": "success", 
                "success": True, 
                "announcements": [ann_data],
                "announcement": ann_data,
                "data": ann_data,
                "title": ann_data.get('title', '📢 ከአድሚን የተላከ ማስታወቂያ'),
                "content": ann_data.get('content', '')
            }), 200
        else:
            return jsonify({
                "status": "success", 
                "success": True, 
                "announcements": [],
                "announcement": None,
                "data": None,
                "content": ""
            }), 200

    except Exception as e:
        return jsonify({"status": "error", "success": False, "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
