from flask import Flask, request
import requests

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = 'DEIN_TELEGRAM_BOT_TOKEN'
TELEGRAM_CHAT_ID = 'DEINE_CHAT_ID'

def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side.lower() == 'long':
        return entry + risk, entry + 3*risk, entry + 5*risk
    else:
        return entry - risk, entry - 3*risk, entry - 5*risk

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

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'Markdown'}
    requests.post(url, data=data)
