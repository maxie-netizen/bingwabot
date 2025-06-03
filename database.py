import sqlite3
import os

def init_db():
    # Use Railway's persistent storage if available
    db_path = os.path.join(os.getcwd(), 'transactions.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        checkout_request_id TEXT UNIQUE NOT NULL,
        status TEXT DEFAULT 'pending',
        mpesa_receipt TEXT,
        transaction_date TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

def update_transaction(checkout_request_id, status, mpesa_receipt=None):
    db_path = os.path.join(os.getcwd(), 'transactions.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT OR REPLACE INTO transactions 
    (checkout_request_id, status, mpesa_receipt)
    VALUES (?, ?, ?)
    ''', (checkout_request_id, status, mpesa_receipt))
    
    conn.commit()
    conn.close()

# Initialize database on import
init_db()