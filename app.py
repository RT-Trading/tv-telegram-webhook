from flask import Flask, request
import requests
import os

app = Flask(__name__)

# Telegram-Konfiguration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'HIER_DEIN_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', 'HIER_DEINE_CHAT_ID')

# SL: 1 % Risiko
def calc_sl(entry, side, risk_pct=0.01):
    return entry * (1 - risk_pct) if side == 'long' else entry * (1 + risk_pct)

# TP-Ziele: 1:1, 1:3, 1:5 CRV
def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side == 'long':
        return entry + risk, entry + 3 * risk, entry + 5 * risk
    else:
        return entry - risk, entry - 3 * risk, entry - 5 * risk

# Formatierte Telegram-Nachricht
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

# Webhook-Endpunkt für TradingView
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print("📥 Empfangenes JSON:", data)  # Debug-Ausgabe

    try:
        # ENTRY-Preis
        entry = float(data.get('entry', 0))

        # DIRECTION – robust lesen
        raw_direction = data.get('side') or data.get('direction')
        if raw_direction is None:
            return '❌ Kein direction/side-Feld empfangen.', 400
        side = str(raw_direction).strip().lower()

        # SYMBOL
        symbol = str(data.get('symbol', '')).strip().upper()

        # Validierung
        if not symbol or side not in ['long', 'short']:
            return f'❌ Fehler: ungültige Richtung "{raw_direction}" oder fehlender Symbol', 400

    except (KeyError, ValueError, TypeError) as e:
        print("❌ Parsing-Fehler:", e)
        return '❌ Ungültige Daten – entry, direction und symbol erforderlich.', 400

    # Berechnungen
    sl = calc_sl(entry, side)
    tp1, tp2, tp3 = calc_tp(entry, sl, side)
    msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)

    # Telegram versenden
    send_to_telegram(msg)

    # Bestätigung + Log
    print(f"✅ Webhook verarbeitet: {symbol} | {side.upper()} | Entry={entry:.5f}")
    return '✅ OK', 200

# Telegram-Nachricht versenden
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': f"Test-Nachricht\n{text}",
        'parse_mode': 'Markdown'
    }
    response = requests.post(url, data=data)
    print("📨 Telegram Antwort:", response.status_code, response.text)

# Server starten
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
