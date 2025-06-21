from flask import Flask, request
import requests
import os

app = Flask(__name__)

# Umgebungsvariablen
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# SL automatisch berechnen (1 % Risiko)
def calc_sl(entry, side, risk_pct=0.01):
    return entry * (1 - risk_pct) if side == 'long' else entry * (1 + risk_pct)

# TP-Ziele basierend auf CRV (Chance-Risiko-Verhältnis)
def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side == 'long':
        return entry + risk, entry + 3 * risk, entry + 5 * risk
    else:
        return entry - risk, entry - 3 * risk, entry - 5 * risk

# Formatierte Telegram-Nachricht
def format_message(symbol, entry, sl, tp1, tp2, tp3, side):
    if side == 'long':
        direction = '🟢 *LONG* 📈'
    elif side == 'short':
        direction = '🔴 *SHORT* 📉'
    else:
        direction = f'*{side.upper()}*'

    return f"""🔔 *{symbol}* 🔔  
{direction}

📍 *Entry*: `{entry:.2f}`  
🛑 *SL*: `{sl:.2f}`

💶 *TP 1 (1:1)*: `{tp1:.2f}`  
💶 *TP 2 (1:3)*: `{tp2:.2f}`  
💶 *TP 3 (1:5)*: `{tp3:.2f}`

⚠️ *Keine Finanzberatung!*  
📌 Achtet auf *Money Management*!  
❗️Sehr *riskant* – aufpassen!  
🔁 *Bei TP 1 auf Breakeven setzen* oder eigenständig managen.
"""

# Webhook-Endpunkt
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    try:
        entry = float(data['entry'])
        side = data.get('side', '').strip().lower()
        symbol = data.get('symbol', '').strip().upper()
        if not symbol or side not in ['long', 'short']:
            return '❌ Fehler: symbol oder side fehlt/ungültig', 400
    except (KeyError, ValueError, TypeError):
        return '❌ Ungültige Eingabedaten – entry, side, symbol erforderlich.', 400

    sl = calc_sl(entry, side)
    tp1, tp2, tp3 = calc_tp(entry, sl, side)
    msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)

    send_to_telegram(msg)

    print(f"✅ Webhook: {symbol} | {side.upper()} | Entry={entry} | SL={sl:.2f}")
    return '✅ Signal gesendet', 200

# Telegram-Nachricht senden
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': f"Test-Nachricht\n{text}",
        'parse_mode': 'Markdown'
    }
    response = requests.post(url, data=data)
    print("📨 Telegram Antwort:", response.status_code, response.text)

# App starten
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
