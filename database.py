# database.py
import sqlite3

DB_NAME = "wallet.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # የተጠቃሚዎች መረጃ ሰንጠረዥ (Users Table)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            phone_number TEXT,
            password TEXT,
            ton_balance REAL DEFAULT 0.0,
            etb_balance REAL DEFAULT 0.0,
            memo_id TEXT UNIQUE,
            kyc_status TEXT DEFAULT 'NOT_SUBMITTED', -- NOT_SUBMITTED, PENDING, APPROVED, REJECTED
            kyc_doc_type TEXT,
            kyc_doc_path TEXT,
            otp_code TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # የትራንዛክሽን ታሪክ ሰንጠረዥ (Transactions Table)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            type TEXT, -- DEPOSIT_ETB, DEPOSIT_TON, WITHDRAW
            amount REAL,
            currency TEXT,
            status TEXT, -- PENDING, COMPLETED, FAILED
            reference_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(" Database initialized successfully!")
