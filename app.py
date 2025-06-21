from flask import Flask, request
import requests
import os

app = Flask(__name__)

# Umgebungsvariablen für Token und Chat-ID
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# SL berechnen (1% Risiko)
def calc_sl(entry, side):
    risk_pct = 0.01
    return entry * (1 - risk_pct) if side == 'long' else entry * (1 + risk_pct)

# TP-Ziele berechnen
def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side == 'long':
        return entry + risk, entry + 3 * risk, entry + 5 * risk
    else:
        return entry - risk, entry - 3 * risk, entry - 5 * risk

# Telegram-Nachricht senden
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': f"Test-Nachricht\n{text}",
        'parse_mode': 'Markdown'
    }
    response = requests.post(url, data=data)
    print("🔍 Telegram Response:", response.status_code, response.text)

# Webhook-Empfang
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    try:
        entry = float(data['entry'])
        side_raw = data.get('side', '').strip().lower()
        symbol = data.get('symbol', 'Unknown').upper()
    except (KeyError, ValueError, TypeError):
        return 'Invalid input', 400

    # Validierung der Richtung
    if side_raw not in ['long', 'short']:
        side = 'unbekannt'
        sl = entry
        tp1 = tp2 = tp3 = entry
    else:
        side = side_raw
        sl = calc_sl(entry, side)
        tp1, tp2, tp3 = calc_tp(entry, sl, side)

    # Icon je nach Richtung
    side_icon = {
        'long': '🟢 LONG',
        'short': '🔴 SHORT'
    }.get(side, '⚪️ UNBEKANNT')

    # Nachricht formatieren
    msg = f"""🔔 *{symbol}* 🔔
{side_icon}

📍 *Entry*: {entry:.2f}  
🛑 *SL*: {sl:.2f}

💶 *TP 1*: {tp1:.2f}  
💶 *TP 2*: {tp2:.2f}  
💶 *TP 3*: {tp3:.2f}

⚠️ *Keine Finanzberatung!*  
📌 Achtet auf *Money Management*!  
❗️ *Sehr riskant* – aufpassen!  
🔁 *Bei TP 1 auf Breakeven setzen* oder eigenständig managen."""

    send_to_telegram(msg)
    return 'OK', 200

# Für Render
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

