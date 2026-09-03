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
# Database Setup & Migrations
# ---------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Members Table
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

    # 2. Receipts Table (ለቁጠባና ብድር ተመላሽ ደረሰኞች መዝገብ)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER,
            ref_no TEXT,
            pay_type TEXT,
            amount REAL,
            receipt_path TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES members (id)
        )
    ''')

    # 3. Settings Table (ለባንክ ሂሳብ ቁጥሮች መረጃ ማስቀመጫ)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Default Bank Account (ነባሪ የባንክ ሂሳብ)
    cursor.execute("SELECT value FROM settings WHERE key = 'bank_account'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO settings (key, value) VALUES ('bank_account', ?)", 
                       ('1000070780201 - ኢትዮጵያ ንግድ ባንክ (ጋሻዬ በጅጉ)',))

    conn.commit()
    conn.close()

init_db()

def sanitize_input(text):
    if text is None: return ""
    return html.escape(str(text).strip())

# ---------------------------------------------------------
# TELEGRAM BOT & INLINE ACTION HANDLERS
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

    # አድሚኑ ከቴሌግራም ቀጥታ Approve/Cancel ሲያደርግ የሚሰራ
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
                cursor.execute("UPDATE members SET status = ? WHERE id = ?", (new_status, member_id))
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
                cursor.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,))
                receipt = cursor.fetchone()

                if receipt:
                    if action == "approve_pay" and receipt['status'] == 'pending':
                        if receipt['pay_type'] == "savings":
                            cursor.execute("UPDATE members SET paid_amount = paid_amount + ? WHERE id = ?", (receipt['amount'], receipt['member_id']))
                        else: # loan
                            cursor.execute("UPDATE members SET paid_loan = paid_loan + ? WHERE id = ?", (receipt['amount'], receipt['member_id']))
                        
                        cursor.execute("UPDATE receipts SET status = 'approved' WHERE id = ?", (receipt_id,))
                        conn.commit()
                        bot.answer_callback_query(call.id, "✅ ክፍያው ተቀባይነት አግኝቶ ደብተሩ ተዘምኗል!")
                        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                                                 caption=f"{call.message.caption}\n\n<b>ውሳኔ:</b> ✅ ክፍያው ጸድቋል (ደብተሩ ተዘምኗል)", parse_mode="HTML")
                    
                    elif action == "cancel_pay" and receipt['status'] == 'pending':
                        cursor.execute("UPDATE receipts SET status = 'rejected' WHERE id = ?", (receipt_id,))
                        conn.commit()
                        bot.answer_callback_query(call.id, "❌ ክፍያው ውድቅ ተደርጓል!")
                        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                                                 caption=f"{call.message.caption}\n\n<b>ውሳኔ:</b> ❌ ክፍያው ውድቅ ተደርጓል", parse_mode="HTML")
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

# ባንክ አካውንት መረጃ ለተጠቃሚ ማቅረቢያ
@app.route('/api/settings/bank', methods=['GET'])
def get_bank_account():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'bank_account'")
    row = cursor.fetchone()
    conn.close()
    bank_info = row['value'] if row else "1000070780201 - ኢትዮጵያ ንግድ ባንክ (ጋሻዬ በጅጉ)"
    return jsonify({"bank_account": bank_info})

# አድሚን የባንክ አካውንት ቁጥር መቀየሪያ
@app.route('/api/admin/settings/bank', methods=['POST'])
def set_bank_account():
    try:
        data = request.get_json(silent=True) or {}
        bank_info = data.get('bank_account', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bank_account', ?)", (bank_info,))
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

        pay_type = req.get('type') # 'savings' or 'loan'
        amount = float(req.get('amount', 0))
        ref_no = req.get('ref_no')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM members WHERE ref_no = ?", (ref_no,))
        member = cursor.fetchone()

        if not member:
            conn.close()
            return jsonify({"success": False, "message": "አባሉ አልተገኘም!"}), 404

        if 'receipt' not in files:
            conn.close()
            return jsonify({"success": False, "message": "እባክዎን የባንክ ደረሰኝ ስክሪንሾት ያያይዙ!"}), 400

        receipt_file = files['receipt']
        filename = secure_filename(f"pay_{pay_type}_{ref_no}_{receipt_file.filename}")
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        receipt_file.save(save_path)

        # በደረሰኞች ሰንጠረዥ (receipts table) መዝግቦ ማስቀመጥ
        cursor.execute('''
            INSERT INTO receipts (member_id, ref_no, pay_type, amount, receipt_path, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (member['id'], ref_no, pay_type, amount, save_path))
        
        receipt_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # ለቴሌግራም አድሚን ፈጣን Approve/Cancel በተን መላክ
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

        return jsonify({"success": True, "message": "የክፍያ ማረጋገጫው ለአድሚን በስኬት ተልኳል! አድሚኑ እንደተቀበለው ደብተሩ ይዘመናል።"}), 200
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
        ref_no = f"SAV-{(count + 1):03d}"

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
    members = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "members": members}), 200

# ---------------------------------------------------------
# NEW: ደረሰኞችን በቀንና በዓይነት (ቁጠባ vs ብድር) አውጥቶ ማሳያ
# ---------------------------------------------------------
@app.route('/api/admin/receipts', methods=['GET'])
def get_admin_receipts():
    pay_type = request.args.get('type') # 'savings' or 'loan'
    date_str = request.args.get('date') # e.g. '2026-03-30'

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
        query += " AND r.pay_type = ?"
        params.append(pay_type)
    
    if date_str:
        query += " AND DATE(r.created_at) = DATE(?)"
        params.append(date_str)

    query += " ORDER BY r.id DESC"

    cursor.execute(query, params)
    receipts = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({"status": "success", "receipts": receipts}), 200

# ---------------------------------------------------------
# NEW: ደረሰኝ ከአድሚን ፓናል Approve/Reject ማድረጊያ
# ---------------------------------------------------------
@app.route('/api/admin/receipt/action', methods=['POST'])
def process_receipt_action():
    try:
        data = request.get_json(silent=True) or {}
        receipt_id = data.get('receipt_id')
        action = data.get('action') # 'approve' or 'reject'

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,))
        receipt = cursor.fetchone()

        if not receipt:
            conn.close()
            return jsonify({"status": "error", "message": "ደረሰኙ አልተገኘም!"}), 404

        if receipt['status'] != 'pending':
            conn.close()
            return jsonify({"status": "error", "message": "ይህ ደረሰኝ ቀደም ብሎ ውሳኔ አግኝቷል!"}), 400

        if action == 'approve':
            if receipt['pay_type'] == 'savings':
                cursor.execute("UPDATE members SET paid_amount = paid_amount + ? WHERE id = ?", (receipt['amount'], receipt['member_id']))
            else: # loan return
                cursor.execute("UPDATE members SET paid_loan = paid_loan + ? WHERE id = ?", (receipt['amount'], receipt['member_id']))
            
            cursor.execute("UPDATE receipts SET status = 'approved' WHERE id = ?", (receipt_id,))
            msg = "ክፍያው በስኬት ጸድቋል፤ የደብተር ሂሳቡ ተዘምኗል!"
        else:
            cursor.execute("UPDATE receipts SET status = 'rejected' WHERE id = ?", (receipt_id,))
            msg = "ክፍያው ውድቅ ተደርጓል!"

        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": msg}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ---------------------------------------------------------
# NEW: አጠቃላይ የአድሚን ዳሽቦርድ ስታቲስቲክስ
# ---------------------------------------------------------
@app.route('/api/admin/analytics', methods=['GET'])
def get_admin_analytics():
    conn = get_db_connection()
    cursor = conn.cursor()

    # የሰው ብዛት
    cursor.execute("SELECT COUNT(*) FROM members")
    total_members = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM members WHERE status = 'pending'")
    pending_members = cursor.fetchone()[0]

    # የገቢ ስታቲስቲክስ (በቀን፣ በሳምንት፣ በወር፣ በዓመት)
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND DATE(created_at) = DATE('now')")
    daily_income = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND DATE(created_at) >= DATE('now', '-7 days')")
    weekly_income = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND DATE(created_at) >= DATE('now', 'start of month')")
    monthly_income = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM receipts WHERE status = 'approved' AND DATE(created_at) >= DATE('now', 'start of year')")
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
        member_id = data.get('member_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()

        # Deduction or Update
        deduct_savings = float(data.get('deduct_savings', 0))
        deduct_loan = float(data.get('deduct_loan', 0))

        if deduct_savings > 0 or deduct_loan > 0:
            cursor.execute('''
                UPDATE members 
                SET paid_amount = MAX(0, paid_amount - ?),
                    paid_loan = paid_loan + ?
                WHERE id = ?
            ''', (deduct_savings, deduct_loan, member_id))
        else:
            cursor.execute('''
                UPDATE members 
                SET paid_amount = ?, approved_loan = ?, paid_loan = ?, loan_series_no = ?
                WHERE id = ?
            ''', (
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
