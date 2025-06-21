from flask import Flask, request
import requests
import os

app = Flask(__name__)

# Umgebungsvariablen
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# SL automatisch berechnen + TP-Ziele
def calc_tp_auto(entry, side):
    risk_percent = 0.01  # 1% Risiko
    if side.lower() == 'long':
        sl = entry * (1 - risk_percent)
        risk = entry - sl
        return sl, entry + risk, entry + 3*risk, entry + 5*risk
    else:
        sl = entry * (1 + risk_percent)
        risk = sl - entry
        return sl, entry - risk, entry - 3*risk, entry - 5*risk

# Webhook-Route
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    # 🔢 Konvertierung
    try:
        entry = float(data['entry'])
    except (KeyError, ValueError, TypeError):
        return 'Invalid entry', 400

    side = data.get('side', '').lower()
    symbol = data.get('symbol', 'Unknown')

    sl, tp1, tp2, tp3 = calc_tp_auto(entry, side)

    msg = f"""📈 *Signal*: {symbol}
*Richtung*: {side.upper()}
*Entry*: {entry}
*SL*: {sl}
*TP1 (1:1)*: {tp1}
*TP2 (1:3)*: {tp2}
*Full TP (1:5)*: {tp3}"""

    send_to_telegram(msg)
    return 'OK', 200

# Telegram senden mit Debug-Ausgabe
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': f"Test-Nachricht\n{text}",
        # 'parse_mode': 'Markdown'  # optional aktivieren
    }
    response = requests.post(url, data=data)
    print("🔍 Telegram Response:", response.status_code, response.text)

# Render erwartet diese Zeile
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

