from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import os

app = Flask(__name__, template_folder='.')
CORS(app)  # CORS ችግር እንዳይፈጠር ይረዳል

# ጊዜያዊ የዳታ መያዣዎች (Database በቅርቡ ሲቀየር እዚህ ይተካል)
members_db = []
settings_db = {
    "latest_draw_number": "ዙር 01",
    "winner_name": "-",
    "latest_draw_date": "የለም",
    "support_phone": "0916039015"
}

# 1. ገጾችን ማሳያ Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')


# 2. የተጠቃሚዎች API Endpoints
@app.route('/api/member_info/<telegram_id>', methods=['GET'])
def get_member_info(telegram_id):
    user_members = [m for m in members_db if str(m.get('telegram_id')) == str(telegram_id)]
    return jsonify({
        "settings": settings_db,
        "members": user_members
    })

@app.route('/api/register', methods=['POST'])
def register_member():
    try:
        # Form-data ወይም JSON መቀበያ
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
        return jsonify({"success": False, "message": f"ስህተት ተፈጥሯል: {str(e)}"}), 400

@app.route('/api/upload_weekly_receipt', methods=['POST'])
def upload_receipt():
    try:
        member_id = request.form.get('member_id')
        receipt_ref = request.form.get('receipt_ref')
        
        # ደረሰኝ ምስል ካለ መቀበያ
        receipt_file = request.files.get('receipt')
        if receipt_file:
            # ምስሉን ሴቭ ማድረግ ከፈለግህ እዚህ ማስተካከል ትችላለህ
            pass

        return jsonify({"success": True, "message": "የቁጠባ ክፍያ መረጃው ገብቷል! አድሚኑ ያረጋግጣል።"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": "ክፍያውን መላክ አልተቻለም!"}), 400


# 3. የአድሚን API Endpoints
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    password = data.get('password')
    # ጊዜያዊ የይለፍ ቃል: admin123
    if password == "admin123":
        return jsonify({"success": True, "token": "secret-admin-token"}), 200
    return jsonify({"success": False, "message": "የይለፍ ቃል የተሳሳተ ነው!"}), 401

@app.route('/api/admin/data', methods=['GET'])
def get_admin_data():
    return jsonify({
        "settings": settings_db,
        "members": members_db
    })

@app.route('/api/admin/settings', methods=['POST'])
def update_settings():
    data = request.get_json()
    settings_db.update(data)
    return jsonify({"success": True, "message": "ቅንብሮች ተስተካክለዋል!"})

@app.route('/api/admin/toggle_payment', methods=['POST'])
def toggle_payment():
    data = request.get_json()
    member_id = int(data.get('member_id'))
    status = int(data.get('status'))
    
    for m in members_db:
        if m['id'] == member_id:
            m['weekly_paid_status'] = status
            break
            
    return jsonify({"success": True, "message": "የክፍያ ሁኔታ ተቀይሯል!"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
