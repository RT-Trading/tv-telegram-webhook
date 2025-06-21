from flask import Flask, request
import requests
import os

app = Flask(__name__)

# TELEGRAM Bot-Konfiguration (nutze .env oder Render Environment)
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Funktion zum Berechnen von Take Profits
def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side.lower() == 'long':
        return entry + risk, entry + 3*risk, entry + 5*risk
    else:
        return entry - risk, entry - 3*risk, entry - 5*risk

# Webhook-Endpunkt
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    entry = float(data['entry'])
    sl = float(data['sl'])
    side = data['side']
    symbol = data['symbol']

    tp1, tp2, tp3 = calc_tp(entry, sl, side)

    msg = f"""📈 *Signal*: {symbol}
*Richtung*: {side.upper()}
*Entry*: {entry}
*SL*: {sl}
*TP1 (1:1)*: {tp1}
*TP2 (1:3)*: {tp2}
*Full TP (1:5)*: {tp3}
"""
    send_to_telegram(msg)
    return 'OK', 200

# Telegram-Nachricht senden
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'Markdown'}
    requests.post(url, data=data)

# Render erwartet diese Zeile
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
