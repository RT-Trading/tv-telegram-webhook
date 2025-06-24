from flask import Flask, request
import requests
import os
import json

app = Flask(__name__)

# === Telegram Konfiguration ===
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

# === SL: 0.5 %, TP1: 1.0 %, TP2: 1.8 %, Full TP: 2.8 % ===
def calc_sl(entry, side):
    sl_pct = 0.005
    return entry * (1 - sl_pct) if side == 'long' else entry * (1 + sl_pct)

def calc_tp(entry, side):
    tp1_pct = 0.010
    tp2_pct = 0.018
    tp3_pct = 0.028

    if side == 'long':
        return entry * (1 + tp1_pct), entry * (1 + tp2_pct), entry * (1 + tp3_pct)
    else:
        return entry * (1 - tp1_pct), entry * (1 - tp2_pct), entry * (1 - tp3_pct)

# === Formatierte Nachricht ===
def format_message(symbol, entry, sl, tp1, tp2, tp3, side):
    direction = '🟢 *LONG* 📈' if side == 'long' else '🔴 *SHORT* 📉'

    if symbol in ["BTCUSD", "NAS100", "XAUUSD"]:
        digits = 2
    elif symbol in ["EURUSD", "GBPUSD"]:
        digits = 5
    else:
        digits = 4

    fmt = f"{{:.{digits}f}}"

    return f"""\ud83d\udd14 *RT-Trading VIP* \ud83d\udd14  
{direction}

\ud83d\udccd *Entry*: `{fmt.format(entry)}`  
\ud83d\uded1 *SL*: `{fmt.format(sl)}`

\ud83c\udfaf *TP 1*: `{fmt.format(tp1)}`  
\ud83c\udfaf *TP 2*: `{fmt.format(tp2)}`  
\ud83c\udfaf *Full TP*: `{fmt.format(tp3)}`

\u26a0\ufe0f *Keine Finanzberatung!*  
\ud83d\udccc Achtet auf *Money Management*!  
\ud83d\udd01 *TP1 erreicht \u2192 Breakeven setzen*.
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
        print("\u274c Telegram-Fehler:", r.text)
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
        print("\ud83d\udce9 Empfangen:", data)

        entry = float(data.get("entry", 0))
        side = (data.get("side") or data.get("direction") or "").strip().lower()
        symbol = str(data.get("symbol", "")).strip().upper()

        if not entry or side not in ["long", "short"] or not symbol:
            raise ValueError("\u274c Ung\u00fcltige Daten")

        sl = calc_sl(entry, side)
        tp1, tp2, tp3 = calc_tp(entry, side)
        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)

        send_to_telegram(msg)
        save_trade(symbol, entry, sl, tp1, tp2, tp3, side)
        print("\u2705 Gesendet:", symbol, side, entry)
        return "\u2705 OK", 200

    except Exception as e:
        print("\u274c Fehler:", str(e))
        return f"\u274c Fehler: {str(e)}", 400

# === Lokaler Teststart ===
if __name__ == "__main__":
    app.run(debug=True, port=5000)
