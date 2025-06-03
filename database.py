cat > ~/bingwabot/database.py << 'EOF'
import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect('transactions.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        phone_number TEXT NOT NULL,
        bundle_code TEXT NOT NULL,
        amount REAL NOT NULL,
        checkout_request_id TEXT UNIQUE NOT NULL,
        status TEXT DEFAULT 'pending',
        mpesa_receipt TEXT,
        transaction_date TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

def log_transaction(user_id, phone, bundle_code, amount, checkout_request_id):
    conn = sqlite3.connect('transactions.db')
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO transactions 
    (user_id, phone_number, bundle_code, amount, checkout_request_id)
    VALUES (?, ?, ?, ?, ?)
    ''', (user_id, phone, bundle_code, amount, checkout_request_id))
    conn.commit()
    conn.close()

def get_user_transactions(user_id):
    conn = sqlite3.connect('transactions.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT * FROM transactions 
    WHERE user_id = ?
    ORDER BY transaction_date DESC
    ''', (user_id,))
    transactions = cursor.fetchall()
    conn.close()
    return transactions

def update_transaction(checkout_request_id, status, mpesa_receipt=None):
    conn = sqlite3.connect('transactions.db')
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE transactions 
    SET status = ?, mpesa_receipt = ?
    WHERE checkout_request_id = ?
    ''', (status, mpesa_receipt, checkout_request_id))
    conn.commit()
    conn.close()

# Initialize the database
init_db()
EOF