from flask import Flask, request
import requests
import os
import json

app = Flask(__name__)

# === Telegram Konfiguration ===
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

# === SL und TP-Berechnung (% vom Entry) ===
def calc_sl(entry, side):
    pct = 0.005  # 0.5 %
    return entry * (1 - pct) if side == 'long' else entry * (1 + pct)

def calc_tp(entry, side):
    pct_tp1 = 0.010  # 1.0 %
    pct_tp2 = 0.018  # 1.8 %
    pct_tp3 = 0.028  # 2.8 %

    if side == 'long':
        return entry * (1 + pct_tp1), entry * (1 + pct_tp2), entry * (1 + pct_tp3)
    else:
        return entry * (1 - pct_tp1), entry * (1 - pct_tp2), entry * (1 - pct_tp3)

# === Formatierte Nachricht mit Symbol-abhängiger Präzision ===
def format_message(symbol, entry, sl, tp1, tp2, tp3, side):
    direction_icon = '🟢 *LONG* 📈' if side == 'long' else '🔴 *SHORT* 📉'

    # Dezimalstellen nach Symbol
    if symbol in ["BTCUSD", "NAS100", "XAUUSD", "GOLD"]:
        digits = 2
    elif symbol in ["EURUSD", "GBPUSD"]:
        digits = 5
    else:
        digits = 4

    fmt = f"{{:.{digits}f}}"

    return f"""🔔 *RT-Trading VIP* 🔔  
{direction_icon}

📍 *Entry*: `{fmt.format(entry)}`
🛑 *SL*: `{fmt.format(sl)}`

🎯 *TP 1*: `{fmt.format(tp1)}`
🎯 *TP 2*: `{fmt.format(tp2)}`
🎯 *Full TP*: `{fmt.format(tp3)}`

⚠️ *Keine Finanzberatung!*  
📌 Achtet auf *Money Management*!  
🔁 TP1 erreicht → Breakeven setzen.
"""

# === Telegram senden ===
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown'
    }
    r = requests.post(url, data=payload)
    if r.status_code != 200:
        print("❌ Telegram-Fehler:", r.text)
        raise Exception("Telegram-Fehler")

# === Trade speichern ===
def save_trade(symbol, entry, sl, tp1, tp2, tp3, side):
    trade = {
        "symbol": symbol,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "side": side,
        "closed": False
    }
    try:
        with open("trades.json", "r") as f:
            trades = json.load(f)
    except FileNotFoundError:
        trades = []

    trades.append(trade)
    with open("trades.json", "w") as f:
        json.dump(trades, f, indent=2)

# === Webhook Endpoint ===
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        print("📩 Empfangen:", data)

        entry = float(data.get("entry", 0))
        side = (data.get("side") or data.get("direction") or "").strip().lower()
        symbol = str(data.get("symbol", "")).strip().upper()

        if not entry or side not in ["long", "short"] or not symbol:
            raise ValueError("❌ Ungültige Daten")

        sl = calc_sl(entry, side)
        tp1, tp2, tp3 = calc_tp(entry, side)
        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)

        send_to_telegram(msg)
        save_trade(symbol, entry, sl, tp1, tp2, tp3, side)
        print("✅ Gesendet:", symbol, side, entry)
        return "✅ OK", 200

    except Exception as e:
        print("❌ Fehler:", str(e))
        return f"❌ Fehler: {str(e)}", 400

# === Lokaler Start ===
if __name__ == "__main__":
    app.run(debug=True, port=5000)
