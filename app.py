from flask import Flask, request
import requests
import os

app = Flask(__name__)

# 🔐 Umgebungsvariablen
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# 🔢 SL-Berechnung: 1% Risiko
def calc_sl(entry, side):
    risk_pct = 0.01
    return round(entry * (1 - risk_pct), 2) if side == 'long' else round(entry * (1 + risk_pct), 2)

# 🎯 Take-Profit-Berechnung
def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side == 'long':
        return round(entry + risk, 2), round(entry + 3*risk, 2), round(entry + 5*risk, 2)
    else:
        return round(entry - risk, 2), round(entry - 3*risk, 2), round(entry - 5*risk, 2)

# 📤 Telegram-Nachricht senden
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown'
    }
    response = requests.post(url, data=data)
    print("🔍 Telegram Response:", response.status_code, response.text)

# 🔔 Webhook-Route
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        print("📥 Webhook empfangen:", data)

        entry = float(data['entry'])
        symbol = data.get('symbol', 'UNBEKANNT').upper()
        side = data.get('side', '').lower()

        if side not in ['long', 'short']:
            icon = "⚪️ UNBEKANNT"
            side_display = "UNBEKANNT"
        else:
            icon = "🟢 LONG" if side == 'long' else "🔴 SHORT"
            side_display = "LONG" if side == 'long' else "SHORT"

        sl = calc_sl(entry, side) if side in ['long', 'short'] else entry
        tp1, tp2, tp3 = calc_tp(entry, sl, side) if side in ['long', 'short'] else (entry, entry, entry)

        # 🧾 Formatierte Nachricht
        msg = f"""*Test-Nachricht*
🔔 *{symbol}* 🔔
{icon}

📍 *Entry:* {entry:.2f}  
🛑 *SL:* {sl:.2f}

💶 *TP 1:* {tp1:.2f}  
💶 *TP 2:* {tp2:.2f}  
💶 *TP 3:* {tp3:.2f}

⚠️ *Keine Finanzberatung!*  
📌 Achtet auf *Money Management!*  
❗️ *Sehr riskant* – aufpassen!  
🔁 *Bei TP 1 auf Breakeven setzen* oder eigenständig managen."""

        send_to_telegram(msg)
        return 'OK', 200

    except Exception as e:
        print("❌ Fehler:", str(e))
        return 'Fehler', 500

# 🟢 App starten
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)



