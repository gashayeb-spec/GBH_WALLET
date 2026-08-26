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

# --- TELEGRAM BOT INITIALIZATION ---
bot = None
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

        # --- ADMIN ACTION CALLBACK HANDLER (Approve, Cancel, Block) ---
        @bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'cancel_', 'block_')))
        def handle_admin_action(call):
            try:
                action, member_id = call.data.split('_')
                member_id = int(member_id)

                member = next((m for m in members_db if m['id'] == member_id), None)
                if not member:
                    bot.answer_callback_query(call.id, "አባሉ አልተገኘም!")
                    return

                user_tg_id = member.get('telegram_id')

                if action == "approve":
                    member['status'] = "approved"
                    bot.answer_callback_query(call.id, "ምዝገባው ፀድቋል!")
                    new_text = f"{call.message.caption if call.message.photo else call.message.text}\n\n✅ **ሁኔታ፦ ተፀድቋል (Approved)**"
                    
                    if call.message.photo:
                        bot.edit_message_caption(caption=new_text, chat_id=call.message.chat.id, message_id=call.message.message_id)
                    else:
                        bot.edit_message_text(text=new_text, chat_id=call.message.chat.id, message_id=call.message.message_id)

                    if user_tg_id:
                        bot.send_message(user_tg_id, "🎉 **እንኳን ደስ አለዎት!** የአባልነት ምዝገባዎ በአድሚኑ ፀድቋል።")

                elif action == "cancel":
                    member['status'] = "cancelled"
                    bot.answer_callback_query(call.id, "ምዝገባው ተሰርዟል!")
                    new_text = f"{call.message.caption if call.message.photo else call.message.text}\n\n❌ **ሁኔታ፦ ተሰርዟል (Cancelled)**"
                    
                    if call.message.photo:
                        bot.edit_message_caption(caption=new_text, chat_id=call.message.chat.id, message_id=call.message.message_id)
                    else:
                        bot.edit_message_text(text=new_text, chat_id=call.message.chat.id, message_id=call.message.message_id)

                    if user_tg_id:
                        bot.send_message(user_tg_id, "⚠️ የአባልነት ምዝገባዎ አልተቀበለም/ተሰርዟል። እባክዎ ድጋሚ ይሞክሩ ወይም አድሚኑን ያናግሩ።")

                elif action == "block":
                    member['status'] = "blocked"
                    bot.answer_callback_query(call.id, "ተጠቃሚው ታግዷል!")
                    new_text = f"{call.message.caption if call.message.photo else call.message.text}\n\n🚫 **ሁኔታ፦ ታግዷል (Blocked)**"
                    
                    if call.message.photo:
                        bot.edit_message_caption(caption=new_text, chat_id=call.message.chat.id, message_id=call.message.message_id)
                    else:
                        bot.edit_message_text(text=new_text, chat_id=call.message.chat.id, message_id=call.message.message_id)

                    if user_tg_id:
                        bot.send_message(user_tg_id, "🚫 መለያዎ በሲስተሙ ታግዷል።")

            except Exception as e:
                print("Callback Action Error:", e)

        def start_bot():
            print(">>> TELEGRAM BOT IS RUNNING... <<<")
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

# --- ROUTES ---

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

        member_id = len(members_db) + 1
        new_member = {
            "id": member_id,
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
            "weekly_paid_status": 0,
            "status": "pending"
        }
        members_db.append(new_member)

        if bot and ADMIN_ID:
            try:
                # የአድሚን Action እና WebApp Buttons ማዘጋጀት
                markup = telebot.types.InlineKeyboardMarkup(row_width=3)
                
                btn_approve = telebot.types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{member_id}")
                btn_cancel = telebot.types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{member_id}")
                btn_block = telebot.types.InlineKeyboardButton("🚫 Block", callback_data=f"block_{member_id}")
                markup.add(btn_approve, btn_cancel, btn_block)

                admin_panel_btn = telebot.types.InlineKeyboardButton(
                    text="⚙️ አድሚን ፓናል ክፈት", 
                    web_app=telebot.types.WebAppInfo(url=f"{WEB_APP_URL}/admin")
                )
                markup.add(admin_panel_btn)

                msg = (
                    f"📝 **አዲስ የአባልነት ምዝገባ ደርሷል!**\n\n"
                    f"🆔 **ID / Ref:** `{ref_no}`\n"
                    f"👤 **ስም:** {first_name} {father_name} {grand_name}\n"
                    f"📞 **ስልክ:** `{phone_number}`\n"
                    f"📍 **አካባቢ:** {address}\n"
                    f"📄 **TIN:** `{tin_number}`\n"
                    f"🔢 **ዕጣ ብዛት:** {share_count}\n"
                    f"💬 **Telegram ID:** `{telegram_id}`"
                )

                if id_card_file:
                    id_card_file.seek(0)
                    bot.send_photo(ADMIN_ID, photo=id_card_file, caption=msg, reply_markup=markup)
                else:
                    bot.send_message(ADMIN_ID, msg, reply_markup=markup)

                if license_file:
                    license_file.seek(0)
                    bot.send_photo(ADMIN_ID, photo=license_file, caption=f"📜 የንግድ ፈቃድ - {first_name} {father_name}")

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

                if bot and ADMIN_ID:
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
        if bot and members_db:
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
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
