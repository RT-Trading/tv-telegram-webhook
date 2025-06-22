from flask import Flask, request
import requests
import os
import threading

app = Flask(__name__)

# Telegram-Konfiguration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8138998907:AAGe7lTtVqctKW1W2i_ivX8iONPkaUTV_sU')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '-1002497064342')

# SL = 1% Risiko
def calc_sl(entry, side, risk_pct=0.01):
    return entry * (1 - risk_pct) if side == 'long' else entry * (1 + risk_pct)

# TP-Ziele basierend auf CRV (1:1, 1:3, 1:5)
def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side == 'long':
        return entry + risk, entry + 3 * risk, entry + 5 * risk
    else:
        return entry - risk, entry - 3 * risk, entry - 5 * risk

# Telegram Nachricht formatieren
def format_message(symbol, entry, sl, tp1, tp2, tp3, side):
    direction = '🟢 *LONG* 📈' if side == 'long' else '🔴 *SHORT* 📉'
    return f"""🔔 *{symbol}* 🔔  
{direction}

📍 *Entry*: `{entry:.5f}`  
🛑 *SL*: `{sl:.5f}`

💶 *TP 1 (1:1)*: `{tp1:.5f}`  
💶 *TP 2 (1:3)*: `{tp2:.5f}`  
💶 *TP 3 (1:5)*: `{tp3:.5f}`

⚠️ *Keine Finanzberatung!*  
📌 Achtet auf *Money Management*!  
❗️Sehr *riskant* – aufpassen!  
🔁 *Bei TP 1 auf Breakeven setzen* oder eigenständig managen.
"""

# Webhook-Endpoint
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print("📥 Empfangen:", data)

    try:
        entry = float(data.get('entry'))
        raw_side = data.get('side') or data.get('direction')
        side = str(raw_side).strip().lower()
        symbol = str(data.get('symbol', '')).strip().upper()

        if not symbol or side not in ['long', 'short']:
            return f'❌ Ungültige Richtung \"{side}\" oder kein Symbol', 400

        sl = calc_sl(entry, side)
        tp1, tp2, tp3 = calc_tp(entry, sl, side)
        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)

        # Parallel senden, damit Antwort schnell kommt
        threading.Thread(target=send_to_telegram, args=(msg,)).start()

        print(f"✅ Gesendet: {symbol} | {side.upper()} | Entry={entry:.5f}")
        return '✅ OK', 200

    except Exception as e:
        print("❌ Fehler beim Verarbeiten:", e)
        return '❌ Fehlerhafte Daten', 400

# Telegram senden mit Timeout & Error-Handling
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': f"Test-Nachricht\n{text}",
        'parse_mode': 'Markdown'
    }
    try:
        requests.post(url, data=payload, timeout=3)
    except Exception as e:
        print("⚠️ Telegram-Fehler:", e)

