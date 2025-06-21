from flask import Flask, request
import requests
import os

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side.lower() == 'long':
        return entry + risk, entry + 3 * risk, entry + 5 * risk
    else:
        return entry - risk, entry - 3 * risk, entry - 5 * risk

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Sicher JSON parsen
        data = request.get_json(force=True)
        
        # Werte auslesen mit .get() zur Fehlervermeidung
        entry = float(data.get('entry'))
        sl = float(data.get('sl'))
        side = data.get('side')
        symbol = data.get('symbol')

        if not all([entry, sl, side, symbol]):
            return {"error": "Fehlende Daten im Request"}, 400

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
        return {"status": "OK"}, 200

    except Exception as e:
        return {"error": str(e)}, 500

def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown'
    }
    response = requests.post(url, data=data)
    # Optional: Fehler prüfen
    if response.status_code != 200:
        print("Telegram-Fehler:", response.text)
