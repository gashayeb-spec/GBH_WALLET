import os
import telebot
from threading import Thread
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID", "5351353727")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "https://gbh-wallet.onrender.com")

members_db = []
settings_db = {
    "latest_draw_number": "ዙር 01",
    "winner_name": "-",
    "latest_draw_date": "የለም",
    "support_phone": "0916039015"
}

if BOT_TOKEN:
    try:
        bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
        bot.remove_webhook()

        @bot.message_handler(commands=['start'])
        def send_welcome(message):
            markup = telebot.types.InlineKeyboardMarkup()
            btn = telebot.types.InlineKeyboardButton(
                text="🚀 ተራመድ ሳኮ አፕ ክፈት", 
                web_app=telebot.types.WebAppInfo(url=WEB_APP_URL)
            )
            # ለአድሚኑ ብቻ የሚታይ የአድሚን ፓናል መክፈቻ ቁልፍ
            if str(message.chat.id) == str(ADMIN_ID):
                admin_btn = telebot.types.InlineKeyboardButton(
                    text="⚙️ አድሚን ፓናል ክፈት", 
                    web_app=telebot.types.WebAppInfo(url=f"{WEB_APP_URL}/admin")
                )
                markup.add(admin_btn)

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
        first_name = request.form.get('first_name')
        father_name = request.form.get('father_name')
        grand_name = request.form.get('grand_name')
        phone_number = request.form.get('phone_number')
        address = request.form.get('address')
        tin_number = request.form.get('tin_number', 'የለም')
        share_count = int(request.form.get('share_count', 1))
        ref_no = request.form.get('ref_no')
        telegram_id = request.form.get('telegram_id')

        id_card_file = request.files.get('id_card')
        license_file = request.files.get('trade_license')

        new_member = {
            "id": len(members_db) + 1,
            "ref_no": ref_no,
            "telegram_id": telegram_id,
            "first_name": first_name,
            "father_name": father_name,
            "grand_name": grand_name,
            "phone_number": phone_number,
            "address": address,
            "tin_number": tin_number,
            "share_count": share_count,
            "paid_amount": 0,
            "weekly_paid_status": 0
        }
        members_db.append(new_member)

        # ለአድሚኑ በቴሌግራም መልእክትና ፋይሎችን መላክ
        if BOT_TOKEN and ADMIN_ID:
            try:
                msg = (
                    f"📝 **አዲስ የአባልነት ምዝገባ ደርሷል!**\n\n"
                    f"🆔 **Ref No:** `{ref_no}`\n"
                    f"👤 **ስም:** {first_name} {father_name} {grand_name}\n"
                    f"📞 **ስልክ:** `{phone_number}`\n"
                    f"📍 **አካባቢ/መኖሪያ:** {address}\n"
                    f"📄 **ቲን ቁጥር (TIN):** `{tin_number}`\n"
                    f"🔢 **የዕጣ/ቁጠባ ብዛት:** {share_count}\n"
                    f"💬 **Telegram ID:** `{telegram_id}`"
                )
                bot.send_message(ADMIN_ID, msg)

                if id_card_file:
                    id_card_file.seek(0)
                    bot.send_photo(ADMIN_ID, photo=id_card_file, caption=f"🆔 የቀበሌ መታወቂያ - {first_name} {father_name}")
                if license_file:
                    license_file.seek(0)
                    bot.send_photo(ADMIN_ID, photo=license_file, caption=f"📜 የንግድ ፈቃድ/ሰነድ - {first_name} {father_name}")
            except Exception as err:
                print("Telegram Registration Notify Error:", err)

        return jsonify({"success": True, "message": "ምዝገባዎ በስኬት ተጠናቆ ለአድሚኑ ተልኳል!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"ስህተት: {str(e)}"}), 400

@app.route('/api/upload_weekly_receipt', methods=['POST'])
def upload_weekly_receipt():
    try:
        member_id = request.form.get('member_id')
        receipt_ref = request.form.get('receipt_ref')
        file = request.files.get('receipt')

        for member in members_db:
            if str(member['id']) == str(member_id):
                member['weekly_paid_status'] = 1
                member['paid_amount'] += 1000

                if BOT_TOKEN and ADMIN_ID:
                    try:
                        msg = f"📩 **አዲስ የቁጠባ ክፍያ ደረሰኝ!**\n\n👤 **አባል:** {member['first_name']} {member['father_name']}\n🆔 **Ref:** `{member['ref_no']}`\n🔢 **Transaction Ref:** `{receipt_ref}`"
                        if file:
                            file.seek(0)
                            bot.send_photo(ADMIN_ID, photo=file, caption=msg)
                        else:
                            bot.send_message(ADMIN_ID, msg)
                    except Exception as err:
                        print("Telegram Receipt Notify Error:", err)
                break

        return jsonify({"success": True, "message": "የቁጠባ ክፍያ መረጃዎ በስኬት ተልኳል!"}), 200
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

@app.route('/api/admin/settings', methods=['POST'])
def update_settings():
    try:
        data = request.get_json()
        if data:
            settings_db['latest_draw_number'] = data.get('latest_draw_number', settings_db['latest_draw_number'])
            settings_db['winner_name'] = data.get('winner_name', settings_db['winner_name'])
            settings_db['latest_draw_date'] = data.get('latest_draw_date', settings_db['latest_draw_date'])
            settings_db['support_phone'] = data.get('support_phone', settings_db['support_phone'])
        return jsonify({"success": True, "message": "ቅንብሮች በስኬት ተዘምነዋል!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"ስህተት: {str(e)}"}), 400

@app.route('/api/admin/broadcast', methods=['POST'])
def broadcast_message():
    try:
        data = request.get_json()
        message_text = data.get('message', '')
        if not message_text:
            return jsonify({"success": False, "message": "መልእክቱ ባዶ ነው!"}), 400

        sent_count = 0
        if BOT_TOKEN and members_db:
            for member in members_db:
                tg_id = member.get('telegram_id')
                if tg_id:
                    try:
                        bot.send_message(tg_id, f"📢 **የአድሚን ማስታወቂያ፦**\n\n{message_text}")
                        sent_count += 1
                    except Exception as err:
                        print(f"Failed to send to {tg_id}:", err)

        return jsonify({"success": True, "message": f"ማስታወቂያው ለ {sent_count} አባላት ተልኳል!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"ስህተት: {str(e)}"}), 400

@app.route('/api/admin/toggle_payment', methods=['POST'])
def toggle_payment():
    try:
        data = request.get_json()
        member_id = str(data.get('member_id'))
        status = int(data.get('status', 0))

        for member in members_db:
            if str(member['id']) == member_id:
                member['weekly_paid_status'] = status
                break

        return jsonify({"success": True, "message": "የክፍያ ሁኔታው ተቀይሯል!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"ስህተት: {str(e)}"}), 400

@app.route('/api/admin/edit_member', methods=['POST'])
def edit_member():
    try:
        data = request.get_json()
        member_id = str(data.get('id'))
        for member in members_db:
            if str(member['id']) == member_id:
                member['first_name'] = data.get('first_name', member['first_name'])
                member['father_name'] = data.get('father_name', member['father_name'])
                member['grand_name'] = data.get('grand_name', member['grand_name'])
                member['phone_number'] = data.get('phone_number', member['phone_number'])
                member['address'] = data.get('address', member.get('address', ''))
                member['tin_number'] = data.get('tin_number', member.get('tin_number', ''))
                member['paid_amount'] = float(data.get('paid_amount', member['paid_amount']))
                break
        return jsonify({"success": True, "message": "የአባል መረጃ በስኬት ተስተካክሏል!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": f"ስህተት: {str(e)}"}), 400

if __name__ == '__main__':
    # Render በራሱ የሚሰጠውን PORT ወይም 10000 ይጠቀማል
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
