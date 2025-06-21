from flask import Flask, request
import requests
import os

app = Flask(__name__)

# Umgebungsvariablen
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# SL automatisch berechnen
def calc_sl(entry, side):
    risk_pct = 0.01  # z. B. 1 % Risiko
    return entry * (1 - risk_pct) if side == 'long' else entry * (1 + risk_pct)

# Take-Profit-Ziele berechnen
def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side == 'long':
        return entry + risk, entry + 3 * risk, entry + 5 * risk
    else:
        return entry - risk, entry - 3 * risk, entry - 5 * risk

# Webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    try:
        entry = float(data['entry'])
        side = data.get('side', '').lower()
        symbol = data.get('symbol', 'Unknown').upper()
    except (KeyError, ValueError, TypeError):
        return 'Invalid input', 400

    sl = calc_sl(entry, side)
    tp1, tp2, tp3 = calc_tp(entry, sl, side)

    side_icon = '🟢 LONG' if side == 'long' else '🔴 SHORT'

    msg = f"""🔔 *{symbol}* 🔔  
{side_icon}

📍 *Entry*: {entry:.2f}  
🛑 *SL*: {sl:.2f}

💶 *TP 1*: {tp1:.2f}  
💶 *TP 2*: {tp2:.2f}  
💶 *TP 3*: {tp3:.2f}

⚠️ *Keine Finanzberatung!*  
📌 *Achtet auf Money Management!*  
❗️ *Sehr riskant – aufpassen!*  
🔁 *Bei TP 1 auf Breakeven setzen oder eigenständig managen.*
"""

    send_to_telegram(msg)
    return 'OK', 200

# Telegram senden
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': f"Test-Nachricht\n{text}",
        'parse_mode': 'Markdown'
    }
    response = requests.post(url, data=data)
    print("🔍 Telegram Response:", response.status_code, response.text)

# Render erwartet das
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)


