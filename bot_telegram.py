import random
import requests
import sqlite3
from config import BOT_TOKEN, ADMIN_ID

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_telegram_message(chat_id, text, reply_markup=None):
    """ለተጠቃሚው በቴሌግራም መልእክት መላኪያ"""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    response = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)
    return response.json()

def generate_and_send_otp(telegram_id):
    """የ 6 አሃዝ OTP ማመንጫ እና በቴሌግራም መላኪያ"""
    otp = str(random.randint(100000, 999999))
    
    # OTP በዳታቤዝ ውስጥ ማስቀመጥ
    conn = sqlite3.connect('wallet.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET otp_code = ? WHERE telegram_id = ?', (otp, telegram_id))
    conn.commit()
    conn.close()
    
    # መልእክት ለተጠቃሚው መላክ
    msg = f"🔐 **የ GBH Wallet ማረጋገጫ ኮድ (OTP)**\n\nየእርስዎ ኮድ: `{otp}`\n\nይህንን ኮድ ለማንም አያጋሩ!"
    send_telegram_message(telegram_id, msg)
    return otp

def send_kyc_to_admin(telegram_id, full_name, doc_type, photo_file_id):
    """የተጠቃሚውን KYC መረጃ ለ Admin መላኪያ"""
    caption = (
        f"📩 **አዲስ የ KYC ማረጋገጫ ጥያቄ!**\n\n"
        f"👤 **ስም:** {full_name}\n"
        f"🆔 **Telegram ID:** `{telegram_id}`\n"
        f"📄 **የሰነድ አይነት:** {doc_type}\n"
    )
    
    # የ Admin ውሳኔ መስጫ በተኖች
    inline_keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"approve_kyc_{telegram_id}"},
            {"text": "❌ Reject", "callback_data": f"reject_kyc_{telegram_id}"}
        ]]
    }
    
    payload = {
        "chat_id": ADMIN_ID,
        "photo": photo_file_id,
        "caption": caption,
        "parse_mode": "Markdown",
        "reply_markup": inline_keyboard
    }
    
    requests.post(f"{TELEGRAM_API}/sendPhoto", json=payload)

if __name__ == "__main__":
    print("Bot helper script loaded successfully!")
