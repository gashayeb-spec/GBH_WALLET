import os
import telebot
from threading import Thread
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

# 1. Flask App Setup
app = Flask(__name__)
CORS(app)

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://gbh-wallet.onrender.com")

members_db = []
settings_db = {
    "latest_draw_number": "ዙር 01",
    "winner_name": "-",
    "latest_draw_date": "የለም",
    "support_phone": "0916039015"
}

# 2. Telegram Bot Setup
if BOT_TOKEN:
    try:
        bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

        @bot.message_handler(commands=['start'])
        def send_welcome(message):
            markup = telebot.types.InlineKeyboardMarkup()
            btn = telebot.types.InlineKeyboardButton(
                text="🚀 ተራመድ ሳኮ አፕ ክፈት", 
                web_app=telebot.types.WebAppInfo(url=WEB_APP_URL)
            )
            markup.add(btn)
            
            bot.reply_to(
                message, 
                "እንኳን ወደ **ተራመድ ሳኮ** በሰላም መጡ! ከታች ያለውን አዝራር በመጫን የቁጠባና ብድር አፑን መክፈት ይችላሉ፦", 
                reply_markup=markup
            )

        def start_bot():
            print(">>> TELEGRAM BOT IS RUNNING... <<<")
            bot.infinity_polling(timeout=10, long_polling_timeout=5)

        Thread(target=start_bot, daemon=True).start()
    except Exception as e:
        print("Bot Error:", e)

# 3. Flask Routes & APIs
@app.route('/', methods=['GET', 'HEAD'])
def home():
    return render_template('index.html')

@app.route('/admin', methods=['GET', 'HEAD'])
def admin_page():
    return render_template('admin.html')

@app.route('/api/member_info/<telegram_id>', methods=['GET'])
def get_member_info(telegram_id):
    user_members = [m for m in members_db if str(m.get('telegram_id')) == str(telegram_id)]
    return jsonify({"settings": settings_db, "members": user_members})

@app.route('/api/register', methods=['POST'])
def register_member():
    try:
        data = request.form if request.form else request.get_json()
        new_member = {
            "id": len(members_db) + 1,
            "ref_no": data.get('ref_no'),
            "telegram_id": data.get('telegram_id'),
            "first_name": data.get('first_name'),
            "father_name": data.get('father_name'),
            "grand_name": data.get('grand_name'),
            "phone_number": data.get('phone_number'),
            "share_count": int(data.get('share_count', 1)),
            "paid_amount": 0,
            "weekly_paid_status": 0
        }
        members_db.append(new_member)
        return jsonify({"success": True, "message": "ምዝገባው በስኬት ተጠናቋል!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"ስህተት: {str(e)}"}), 400

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    if data and data.get('password') == "admin123":
        return jsonify({"success": True, "token": "secret-admin-token"}), 200
    return jsonify({"success": False, "message": "የይለፍ ቃል የተሳሳተ ነው!"}), 401

@app.route('/api/admin/data', methods=['GET'])
def get_admin_data():
    return jsonify({"settings": settings_db, "members": members_db})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
