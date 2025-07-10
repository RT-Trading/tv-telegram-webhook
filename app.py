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

# Neue flexible TP-Berechnung nach Symbol
def calc_tp(entry, sl, side, symbol):
    if symbol == "XAUUSD":
        # Angepasste kleinere Ziele für Gold
        tp_pct = [0.004, 0.008, 0.012]  # 0.4%, 0.8%, 1.2%
    else:
        # Standard-Ziele für andere
        risk = abs(entry - sl)
        if side == 'long':
            return entry + 2 * risk, entry + 3.6 * risk, entry + 5.6 * risk
        else:
            return entry - 2 * risk, entry - 3.6 * risk, entry - 5.6 * risk

    if side == "long":
        return entry * (1 + tp_pct[0]), entry * (1 + tp_pct[1]), entry * (1 + tp_pct[2])
    else:
        return entry * (1 - tp_pct[0]), entry * (1 - tp_pct[1]), entry * (1 - tp_pct[2])

# === Nachricht formatieren mit Symbol und korrektem Icon ===
def format_message(symbol, entry, sl, tp1, tp2, tp3, side):
    if symbol in ["BTCUSD", "NAS100", "XAUUSD"]:
        digits = 2
    elif symbol in ["EURUSD", "GBPUSD"]:
        digits = 5
    else:
        digits = 4

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
        "tp1_hit": False,
        "tp2_hit": False,
        "tp3_hit": False,
        "sl_hit": False,
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
        # Kompatibel mit text/plain von TradingView
        try:
            raw_data = request.data.decode("utf-8")
            data = json.loads(raw_data)
        except Exception as json_err:
            print("❌ JSON Fehler beim Parsen:", json_err)
            return f"❌ Ungültiges JSON-Format", 400

        print("📩 Empfangen:", data)

        entry = float(data.get("entry", 0))
        side = (data.get("side") or data.get("direction") or "").strip().lower()
        symbol = str(data.get("symbol", "")).strip().upper()

        if not entry or side not in ["long", "short"] or not symbol:
            raise ValueError("❌ Ungültige Daten")

        sl = calc_sl(entry, side)
        tp1, tp2, tp3 = calc_tp(entry, sl, side, symbol)
        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)

        print("🧪 Nachricht an Telegram:", msg)
        send_to_telegram(msg)
        save_trade(symbol, entry, sl, tp1, tp2, tp3, side)
        print("✅ Gesendet:", symbol, side, entry)
        return "✅ OK", 200

    except Exception as e:
        print("❌ Fehler im Webhook:", str(e))
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
