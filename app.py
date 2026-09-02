import os
import sqlite3
import html
import telebot
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------
# Configurations & File Upload Setup
# ---------------------------------------------------------
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPER_ADMIN_ID = str(os.environ.get("ADMIN_ID", "5351353727")).strip()
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://gbh-wallet.onrender.com")

DB_NAME = "database.db"

# Telegram Bot Initializer
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

# ---------------------------------------------------------
# Database Helpers & Initialization
# ---------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Members Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_no TEXT UNIQUE,
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
            is_defaulted INTEGER DEFAULT 0,
            telegram_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Savings & Payments Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS savings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER,
            amount REAL,
            receipt_path TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (member_id) REFERENCES members (id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

def sanitize_input(text):
    if text is None: 
        return ""
    return html.escape(str(text).strip())

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
# API Endpoints (User / Client)
# ---------------------------------------------------------

# የአባልን ሁኔታ እና የኔ ደብተር መረጃ መፈተሻ
@app.route('/api/member/status', methods=['GET'])
def get_member_status():
    telegram_id = request.args.get('telegram_id')
    if not telegram_id:
        return jsonify({"exists": False})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members WHERE telegram_id = ?", (telegram_id,))
    member = cursor.fetchone()
    conn.close()

    if member:
        return jsonify({"exists": True, "member": dict(member)})
    return jsonify({"exists": False})

# የአባልነት ምዝገባ በሰነዶችና ፎቶ
@app.route('/api/register', methods=['POST'])
def register_member():
    try:
        req = request.form
        files = request.files

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if user already exists
        telegram_id = sanitize_input(req.get('telegram_id'))
        if telegram_id:
            cursor.execute("SELECT id FROM members WHERE telegram_id = ?", (telegram_id,))
            if cursor.fetchone():
                conn.close()
                return jsonify({"success": False, "message": "በዚህ የቴሌግራም አካውንት ቀደም ብለው ተመዝግበዋል!"}), 400

        # Ref Number Generation
        cursor.execute("SELECT COUNT(*) FROM members")
        count = cursor.fetchone()[0]
        ref_no = f"TS-{(count + 1):03d}"

        # Handling File Uploads
        nat_id_path = ""
        trade_lic_path = ""
        photo_path = ""

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
            ref_no,
            sanitize_input(req.get('first_name')),
            sanitize_input(req.get('father_name')),
            sanitize_input(req.get('grand_name')),
            sanitize_input(req.get('country')),
            sanitize_input(req.get('phone_number')),
            sanitize_input(req.get('tin_number')),
            nat_id_path, trade_lic_path, photo_path,
            telegram_id
        ))

        conn.commit()
        conn.close()

        # Notify Telegram Admin
        if bot and SUPER_ADMIN_ID:
            try:
                msg = f"🆕 <b>አዲስ የአባልነት ምዝገባ!</b>\n\n<b>ስም:</b> {req.get('first_name')} {req.get('father_name')}\n<b>መታወቂያ:</b> {ref_no}\n<b>ስልክ:</b> {req.get('phone_number')}\n<b>ሀገር:</b> {req.get('country')}"
                bot.send_message(SUPER_ADMIN_ID, msg, parse_mode="HTML")
            except Exception as bot_err:
                print(f"Telegram notification failed: {bot_err}")

        return jsonify({"success": True, "message": "ምዝገባዎ በስኬት ተልኳል! ለአድሚን ተመርቷል።"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ---------------------------------------------------------
# API Endpoints (Admin Operations)
# ---------------------------------------------------------

# የአባላትን ዝርዝር ማግኛ
@app.route('/api/admin/members', methods=['GET'])
def get_admin_members():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members ORDER BY id DESC")
    members = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "members": members}), 200

# የአባል ሁኔታ መለወጫ (Pending -> Approved / Rejected)
@app.route('/api/admin/update_status', methods=['POST'])
def update_status():
    data = request.get_json(silent=True) or {}
    member_id = data.get('member_id')
    status = data.get('status')

    if not member_id or not status:
        return jsonify({"status": "error", "message": "ጎደሎ መረጃ"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE members SET status = ? WHERE id = ?", (status, member_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": f"የአባሉ ሁኔታ ወደ '{status}' ተቀይሯል!"}), 200

# የብድር እና የቁጠባ ሂሳብ ማስተካከያ በአድሚን
@app.route('/api/admin/update_financials', methods=['POST'])
def update_financials():
    data = request.get_json(silent=True) or {}
    member_id = data.get('member_id')
    paid_amount = float(data.get('paid_amount', 0))
    approved_loan = float(data.get('approved_loan', 0))
    paid_loan = float(data.get('paid_loan', 0))
    is_defaulted = int(data.get('is_defaulted', 0))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE members 
        SET paid_amount = ?, approved_loan = ?, paid_loan = ?, is_defaulted = ?
        WHERE id = ?
    ''', (paid_amount, approved_loan, paid_loan, is_defaulted, member_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "የፋይናንስ መረጃው በስኬት ተዘምኗል!"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
