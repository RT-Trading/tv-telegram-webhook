from flask import Flask, request
import requests
import os
import json

app = Flask(__name__)

# === Telegram Konfiguration ===
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

# === Rundungslogik je Symbol ===
def get_precision(symbol):
    symbol = symbol.upper()
    if "BTC" in symbol or "NAS" in symbol or "SPX" in symbol:
        return 2
    elif "JPY" in symbol:
        return 3
    elif "USD" in symbol:
        return 5
    else:
        return 4

# === SL & TP Berechnung ===
def calc_sl(entry, side):
    risk_pct = 0.007
    return entry * (1 - risk_pct) if side == 'long' else entry * (1 + risk_pct)

def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side == 'long':
        return entry + 3 * risk, entry + 5 * risk, entry + 7 * risk
    else:
        return entry - 3 * risk, entry - 5 * risk, entry - 7 * risk

# === Nachricht formatieren ===
def format_message(symbol, entry, sl, tp1, tp2, tp3, side):
    precision = get_precision(symbol)
    fmt = lambda x: f"{x:.{precision}f}"
    direction = '🟢 *LONG* 📈' if side == 'long' else '🔴 *SHORT* 📉'

    return f"""🔔 *{symbol}* 🔔  
{direction}

📍 *Entry*: `{fmt(entry)}`
🛑 *SL*: `{fmt(sl)}`

🎯 *TP 1 (2.1%)*: `{fmt(tp1)}`
🎯 *TP 2 (3.5%)*: `{fmt(tp2)}`
🎯 *TP 3 (4.9%)*: `{fmt(tp3)}`

⚠️ *Keine Finanzberatung!*  
📌 Achtet auf *Money Management*!
🔁 TP1 erreicht → *Breakeven setzen*
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

# === Webhook ===
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
        tp1, tp2, tp3 = calc_tp(entry, sl, side)
        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)

        send_to_telegram(msg)
        save_trade(symbol, entry, sl, tp1, tp2, tp3, side)
        print("✅ Gesendet:", symbol, side, entry)
        return "✅ OK", 200

    except Exception as e:
        print("❌ Fehler:", str(e))
        return f"❌ Fehler: {str(e)}", 400

# === Lokaler Start (optional) ===
if __name__ == "__main__":
    app.run(debug=True, port=5000)
