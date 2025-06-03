import os
import requests
import base64
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from dotenv import load_dotenv
from database import log_transaction, get_user_transactions

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MPESA_CONSUMER_KEY = os.getenv('MPESA_CONSUMER_KEY')
MPESA_CONSUMER_SECRET = os.getenv('MPESA_CONSUMER_SECRET')
MPESA_PASSKEY = os.getenv('MPESA_PASSKEY')
MPESA_BUSINESS_SHORTCODE = os.getenv('MPESA_BUSINESS_SHORTCODE')
MPESA_CALLBACK_URL = os.getenv('MPESA_CALLBACK_URL')

# Bundle definitions
BUNDLES = {
    'data': [
        {'name': '1GB, 1hr', 'price': 19, 'code': 'DATA1GB1HR'},
        {'name': '1.5GB, 3hrs', 'price': 50, 'code': 'DATA1.5GB3HR'},
    ],
    'sms': [
        {'name': '20 SMS, 1day', 'price': 5, 'code': 'SMS20DAY'},
    ],
    'voice': [
        {'name': '45 minutes, 3hrs', 'price': 21, 'code': 'VOICE45MIN'},
    ]
}

# State management
USER_STATES = {}

def get_mpesa_access_token():
    """Get M-Pesa OAuth access token"""
    url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    auth = base64.b64encode(f"{MPESA_CONSUMER_KEY}:{MPESA_CONSUMER_SECRET}".encode()).decode()
    headers = {'Authorization': f'Basic {auth}'}
    response = requests.get(url, headers=headers)
    return response.json().get('access_token')

def initiate_stk_push(phone, amount, bundle_code, user_id):
    """Initiate M-Pesa STK Push"""
    access_token = get_mpesa_access_token()
    url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = base64.b64encode(
        f"{MPESA_BUSINESS_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()
    ).decode()
    
    payload = {
        "BusinessShortCode": MPESA_BUSINESS_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": MPESA_BUSINESS_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": bundle_code,
        "TransactionDesc": f"Bingwa {bundle_code}"
    }
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        checkout_request_id = response.json().get('CheckoutRequestID')
        log_transaction(user_id, phone, bundle_code, amount, checkout_request_id)
    return response.json()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message and main menu"""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📌 Data Bundles", callback_data='data')],
        [InlineKeyboardButton("📌 SMS Bundles", callback_data='sms')],
        [InlineKeyboardButton("📌 Voice Bundles", callback_data='voice')],
        [InlineKeyboardButton("📋 My Transactions", callback_data='my_transactions')],
        [InlineKeyboardButton("🆘 Help", callback_data='help')],
    ]
    
    await update.message.reply_text(
        f"Karibu {user.first_name} to Bingwa Sokoni by Safaricom!\n\n"
        "I can help you purchase mobile data, SMS, and calling minute packages easily via M-Pesa.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_bundles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bundles for selected category"""
    query = update.callback_query
    await query.answer()
    
    bundle_type = query.data
    keyboard = []
    
    for bundle in BUNDLES[bundle_type]:
        text = f"{bundle['name']} @ Ksh {bundle['price']}"
        callback_data = f"select_{bundle_type}_{bundle['code']}_{bundle['price']}"
        keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data='back')])
    
    await query.edit_message_text(
        text=f"Please select a {bundle_type} bundle:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def request_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Request phone number for bundle purchase"""
    query = update.callback_query
    await query.answer()
    
    _, bundle_type, bundle_code, price = query.data.split('_')
    USER_STATES[query.from_user.id] = {
        'bundle_type': bundle_type,
        'bundle_code': bundle_code,
        'price': price,
        'step': 'awaiting_phone'
    }
    
    bundle_name = next(
        (b['name'] for b in BUNDLES[bundle_type] if b['code'] == bundle_code),
        bundle_code
    )
    
    await query.edit_message_text(
        f"Selected: {bundle_name} @ Ksh {price}\n\n"
        "Please enter the Safaricom phone number to purchase for:\n"
        "Format: 07XXXXXXXX or 2547XXXXXXXX"
    )

async def process_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process entered phone number and initiate payment"""
    user_id = update.message.from_user.id
    phone = update.message.text.strip()
    
    # Validate phone number format
    if not (phone.startswith('2547') and len(phone) == 12) and \
       not (phone.startswith('07') and len(phone) == 10):
        await update.message.reply_text(
            "Invalid phone format. Please use 07XXXXXXXX or 2547XXXXXXXX"
        )
        return
    
    if phone.startswith('07'):
        phone = '254' + phone[1:]
    
    user_state = USER_STATES.get(user_id)
    if not user_state or user_state['step'] != 'awaiting_phone':
        await update.message.reply_text("Session expired. Please start over with /start")
        return
    
    response = initiate_stk_push(
        phone=phone,
        amount=user_state['price'],
        bundle_code=user_state['bundle_code'],
        user_id=user_id
    )
    
    if response.get('ResponseCode') == '0':
        USER_STATES[user_id]['step'] = 'awaiting_payment'
        USER_STATES[user_id]['phone'] = phone
        USER_STATES[user_id]['checkout_request_id'] = response['CheckoutRequestID']
        
        keyboard = [
            [InlineKeyboardButton("✅ I've completed payment", callback_data=f"check_{user_id}")],
            [InlineKeyboardButton("🔄 Resend STK Push", callback_data=f"resend_{user_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{user_id}")],
        ]
        
        await update.message.reply_text(
            f"Payment request sent to {phone}.\n\n"
            "1. Check your phone for M-Pesa STK Push\n"
            "2. Enter your M-Pesa PIN when prompted\n"
            "3. Confirm payment below once completed",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            "Failed to initiate payment. Please try again later or contact support."
        )

async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check payment status"""
    query = update.callback_query
    await query.answer()
    
    action, user_id = query.data.split('_')
    user_id = int(user_id)
    user_state = USER_STATES.get(user_id)
    
    if not user_state:
        await query.edit_message_text("Session expired. Please start over with /start")
        return
    
    if action == 'check':
        await query.edit_message_text(
            "✅ Payment confirmed! Your bundle will be activated shortly.\n"
            f"You'll receive an SMS confirmation on {user_state['phone']}.\n\n"
            "Thank you for using Bingwa Sokoni!"
        )
        del USER_STATES[user_id]
    elif action == 'resend':
        response = initiate_stk_push(
            phone=user_state['phone'],
            amount=user_state['price'],
            bundle_code=user_state['bundle_code'],
            user_id=user_id
        )
        
        if response.get('ResponseCode') == '0':
            await query.edit_message_text(
                f"Payment request resent to {user_state['phone']}.\n\n"
                "1. Check your phone for M-Pesa STK Push\n"
                "2. Enter your M-Pesa PIN when prompted\n"
                "3. Confirm payment below once completed",
                reply_markup=query.message.reply_markup
            )
        else:
            await query.edit_message_text("Failed to resend payment request. Please try again later.")
    elif action == 'cancel':
        await query.edit_message_text(
            "Purchase cancelled. You can start a new purchase anytime with /start\n\n"
            "For assistance, contact Safaricom support: 0722000000"
        )
        del USER_STATES[user_id]

async def show_user_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display user's transaction history"""
    query = update.callback_query
    await query.answer()
    
    transactions = get_user_transactions(query.from_user.id)
    
    if not transactions:
        await query.edit_message_text("📋 You have no transactions yet.")
        return
    
    message = "📋 Your Recent Transactions:\n\n"
    for txn in transactions:
        status_icon = "✅" if txn[6] == "completed" else "❌"
        message += (
            f"{status_icon} **{txn[3]}** (Ksh {txn[4]})\n"
            f"📞 {txn[2]} | 📅 {txn[8]}\n"
            f"Status: **{txn[6]}**\n\n"
        )
    
    await query.edit_message_text(
        message,
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help information"""
    await update.message.reply_text(
        "Need help?\n\n"
        "Contact MAXWELL customer care:\n"
        "📞 0743518481\n"
        "🕒 24/7 support\n\n"
        "To start over, type /start"
    )

def main() -> None:
    """Start the bot"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Callback query handlers
    application.add_handler(CallbackQueryHandler(show_bundles, pattern='^(data|sms|voice)$'))
    application.add_handler(CallbackQueryHandler(request_phone_number, pattern='^select_'))
    application.add_handler(CallbackQueryHandler(check_payment_status, pattern='^(check|resend|cancel)_'))
    application.add_handler(CallbackQueryHandler(show_user_transactions, pattern='^my_transactions$'))
    application.add_handler(CallbackQueryHandler(start, pattern='^back$'))
    
    # Message handler for phone number input
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone_number))

    application.run_polling()

if __name__ == '__main__':
    main()
