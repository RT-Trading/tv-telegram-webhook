from flask import Flask, request
import requests
import os
import json

app = Flask(__name__)

# === Telegram Konfiguration ===
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

# === SL: 0,5 %, TP1: 1,0 %, TP2: 1,8 %, Full TP: 2,8 % ===
def calc_sl(entry, side):
    risk_pct = 0.005
    return entry * (1 - risk_pct) if side == 'long' else entry * (1 + risk_pct)

def calc_tp(entry, sl, side):
    risk = abs(entry - sl)
    if side == 'long':
        return entry + 2 * risk, entry + 3.6 * risk, entry + 5.6 * risk
    else:
        return entry - 2 * risk, entry - 3.6 * risk, entry - 5.6 * risk

# === Nachricht formatieren mit Symbol und korrektem Icon ===
def format_message(symbol, entry, sl, tp1, tp2, tp3, side):
    # Dezimalstellen je nach Markt
    if symbol in ["BTCUSD", "NAS100", "XAUUSD"]:
        digits = 2
    elif symbol in ["EURUSD", "GBPUSD"]:
        digits = 5
    else:
        digits = 4  # fallback

    fmt = f"{{:.{digits}f}}"
    direction = "🟢 *LONG* 📈" if side == 'long' else "🔴 *SHORT* 📉"

    return f"""🔔 *RT-Trading VIP* 🔔  
📊 *{symbol}*  
{direction}

📍 *Entry*: `{fmt.format(entry)}`  
🛑 *SL*: `{fmt.format(sl)}`

🎯 *TP 1*: `{fmt.format(tp1)}`  
🎯 *TP 2*: `{fmt.format(tp2)}`  
🎯 *Full TP*: `{fmt.format(tp3)}`

⚠️ *Keine Finanzberatung!*  
📌 Achtet auf *Money Management*!  
🔁 TP1 erreicht → *Breakeven setzen*.
"""

# === Telegram senden ===
def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown'
    }

    print("📤 Telegram-Payload:", payload)

    r = requests.post(url, data=payload)

    print("📡 Telegram Response:", r.status_code, r.text)

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
        tp1, tp2, tp3 = calc_tp(entry, sl, side)
        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)

        send_to_telegram(msg)
        save_trade(symbol, entry, sl, tp1, tp2, tp3, side)
        print("✅ Gesendet:", symbol, side, entry)
        return "✅ OK", 200

    except Exception as e:
        print("❌ Fehler:", str(e))
        return f"❌ Fehler: {str(e)}", 400

@app.route("/trades", methods=["GET"])
def show_trades():
    try:
        with open("trades.json", "r") as f:
            return f.read(), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return f"Fehler beim Laden: {e}", 500


# === Lokaler Teststart ===
if __name__ == "__main__":
    app.run(debug=True, port=5000)
