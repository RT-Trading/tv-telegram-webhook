from flask import Flask, request
import requests
import os

app = Flask(__name__)

# === Telegram Konfiguration ===
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'DEIN_BOT_TOKEN_HIER')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', 'DEINE_CHAT_ID_HIER')


# === Risiko und Ziel-Level berechnen ===
def calc_sl(entry, side, risk_pct=0.01):
    return entry * (1 - risk_pct) if side == 'long' else entry * (1 + risk_pct)

def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side == 'long':
        return entry + risk, entry + 3 * risk, entry + 5 * risk
    else:
        return entry - risk, entry - 3 * risk, entry - 5 * risk


# === Telegram Nachricht formatieren ===
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


# === Telegram senden mit Fehlerbehandlung ===
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': f"Test-Nachricht\n{text}",
        'parse_mode': 'Markdown'
    }
    response = requests.post(url, data=payload)

    if response.status_code != 200:
        print(f"❌ Telegram-Fehler: {response.status_code} → {response.text}")
        raise Exception("Telegram-Senden fehlgeschlagen.")


# === Webhook-Route ===
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        if not data:
            raise ValueError("❌ Kein JSON erhalten")

        entry = float(data.get("entry", 0))
        raw_side = data.get("side") or data.get("direction", "")
        side = str(raw_side).strip().lower()
        symbol = str(data.get("symbol", "")).strip().upper()

        if not entry or side not in ['long', 'short'] or not symbol:
            raise ValueError(f"❌ Ungültige Daten: entry={entry}, side={side}, symbol={symbol}")

        sl = calc_sl(entry, side)
        tp1, tp2, tp3 = calc_tp(entry, sl, side)
        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)

        send_to_telegram(msg)

        print(f"✅ Nachricht gesendet: {symbol} | {side.upper()} | Entry={entry:.5f}")
        return '✅ OK', 200

    except Exception as e:
        print(f"❌ Webhook-Fehler: {e}")
        return '❌ Fehler beim Verarbeiten der Anfrage', 400


# === Startpunkt für lokalen Test (optional) ===
if __name__ == '__main__':
    app.run(debug=True, port=5000)
