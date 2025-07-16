import os
import time
import json
import threading
from datetime import datetime
from flask import Flask, request
import requests

app = Flask(__name__)

# === ENV-VARIABLEN ===
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
METALS_API_KEY = os.environ.get("METALS_API_KEY")
TWELVE_API_KEY = os.environ.get("TWELVE_API_KEY")

# =========  GRUND-FUNKTIONEN ===========

def calc_sl(entry, side):
    risk_pct = 0.005
    return entry * (1 - risk_pct) if side == 'long' else entry * (1 + risk_pct)

def calc_tp(entry, sl, side, symbol):
    metals = ["XAUUSD", "SILVER"]
    risk = abs(entry - sl)
    if symbol in metals:
        tp_pct = [0.004, 0.008, 0.012]
        if side == "long":
            return entry * (1 + tp_pct[0]), entry * (1 + tp_pct[1]), entry * (1 + tp_pct[2])
        else:
            return entry * (1 - tp_pct[0]), entry * (1 - tp_pct[1]), entry * (1 - tp_pct[2])
    else:
        if side == 'long':
            return entry + 2 * risk, entry + 3.6 * risk, entry + 5.6 * risk
        else:
            return entry - 2 * risk, entry - 3.6 * risk, entry - 5.6 * risk

def format_message(symbol, entry, sl, tp1, tp2, tp3, side):
    five_digits = ["EURUSD", "GBPUSD", "GBPJPY"]
    three_digits = ["USDJPY"]
    two_digits = ["BTCUSD", "NAS100", "XAUUSD", "SILVER", "US30", "US500", "GER40"]

    if symbol in five_digits:
        digits = 5
    elif symbol in three_digits:
        digits = 3
    elif symbol in two_digits:
        digits = 2
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

def send_telegram(text, retry=True):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': CHAT_ID,
            'text': text,
            'parse_mode': 'Markdown'
        }
        r = requests.post(url, data=payload, timeout=10)
        print("📡 Telegram Response:", r.status_code, r.text)
        if r.status_code != 200:
            raise Exception("Telegram-Fehler")
    except Exception as e:
        print(f"Telegram Fehler: {e}")
        if retry:
            send_telegram(text, retry=False)

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

def load_trades():
    if not os.path.exists("trades.json"):
        return []
    try:
        with open("trades.json", "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Fehler beim Laden von trades.json: {e}")
        return []

def save_trades(trades):
    try:
        with open("trades.json", "w") as f:
            json.dump(trades, f, indent=2)
    except Exception as e:
        print(f"Fehler beim Speichern von trades.json: {e}")

def log_error(text):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("errors.log", "a") as f:
        f.write(f"[{now}] {text}\n")
    print(f"⚠️ {text}")

# ========== PREISABFRAGE =============

def get_price(symbol):
    symbol = symbol.upper()
    COINGECKO_MAP = {
        "BTCUSD": "bitcoin",
        "ETHUSD": "ethereum",
        "XRPUSD": "ripple",
        "DOGEUSD": "dogecoin"
    }
    try:
        if symbol in COINGECKO_MAP:
            r = requests.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids={COINGECKO_MAP[symbol]}&vs_currencies=usd",
                timeout=10
            )
            return float(r.json()[COINGECKO_MAP[symbol]]["usd"])
        if symbol in ["XAUUSD", "SILVER", "XAGUSD"]:
            base = "XAU" if "XAU" in symbol else "XAG"
            r = requests.get(
                f"https://metals-api.com/api/latest?access_key={METALS_API_KEY}&base={base}&symbols=USD",
                timeout=10
            )
            data = r.json()
            if data.get("success") and "rates" in data and "USD" in data["rates"]:
                return float(data["rates"]["USD"])
            else:
                raise Exception(f"MetalsAPI Fehler: {data}")
        r = requests.get(
            f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVE_API_KEY}",
            timeout=10
        )
        data = r.json()
        if "price" in data:
            return float(data["price"])
        else:
            raise Exception(f"Twelve Data Fehler: {data}")
    except Exception as e:
        log_error(f"❌ Preisabruf Fehler für {symbol}: {e}")
        return 0

# =========== MONITOR LOGIK ===========

def check_trades():
    trades = load_trades()
    updated = []
    for t in trades:
        if t.get("closed"):
            updated.append(t)
            continue
        symbol = t.get("symbol", "").upper()
        sl = t.get("sl")
        side = t.get("side")
        tp1, tp2, tp3 = t.get("tp1"), t.get("tp2"), t.get("tp3")
        t.setdefault("tp1_hit", False)
        t.setdefault("tp2_hit", False)
        t.setdefault("tp3_hit", False)
        t.setdefault("sl_hit", False)
        price = get_price(symbol)
        print(f"🔍 {symbol} Preis: {price}")
        if price == 0:
            updated.append(t)
            continue
        def alert(msg):
            send_telegram(f"*{symbol}* | *{side.upper()}*\n{msg}\n💰 Preis: `{price:.2f}`")
        if side == "long":
            if not t["sl_hit"] and price <= sl:
                t["sl_hit"] = True
                alert("❌ *SL erreicht – schade. Wir bewerten neu und kommen stärker zurück.*")
                t["closed"] = True
            elif not t["tp1_hit"] and price >= tp1:
                t["tp1_hit"] = True
                alert("🎯 *TP1 erreicht – BE setzen oder Trade managen.*")
            elif t["tp1_hit"] and not t["tp2_hit"] and price >= tp2:
                t["tp2_hit"] = True
                alert("📈 *TP2 erreicht – Full TP in Sicht!*")
            elif t["tp2_hit"] and not t["tp3_hit"] and price >= tp3:
                t["tp3_hit"] = True
                alert("🎉 *Full TP erreicht – Glückwunsch!*")
                t["closed"] = True
        elif side == "short":
            if not t["sl_hit"] and price >= sl:
                t["sl_hit"] = True
                alert("❌ *SL erreicht – schade. Wir bewerten neu und kommen stärker zurück.*")
                t["closed"] = True
            elif not t["tp1_hit"] and price <= tp1:
                t["tp1_hit"] = True
                alert("🎯 *TP1 erreicht – BE setzen oder Trade managen.*")
            elif t["tp1_hit"] and not t["tp2_hit"] and price <= tp2:
                t["tp2_hit"] = True
                alert("📈 *TP2 erreicht – Full TP in Sicht!*")
            elif t["tp2_hit"] and not t["tp3_hit"] and price <= tp3:
                t["tp3_hit"] = True
                alert("🎉 *Full TP erreicht – Glückwunsch!*")
                t["closed"] = True
        updated.append(t)
    save_trades(updated)

def monitor_loop():
    send_telegram("✅ *Trade-Monitor gestartet*")
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler: {e}")
        time.sleep(60)

# =========== FLASK ROUTES ==============

@app.route("/")
def health():
    return "✅ Monitor läuft", 200

@app.route("/trades", methods=["GET"])
def show_trades():
    try:
        with open("trades.json", "r") as f:
            return f.read(), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return f"Fehler beim Laden: {e}", 500

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
        tp1, tp2, tp3 = calc_tp(entry, sl, side, symbol)
        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)
        send_telegram(msg)
        save_trade(symbol, entry, sl, tp1, tp2, tp3, side)
        return "✅ OK", 200
    except Exception as e:
        print("❌ Fehler:", str(e))
        return f"❌ Fehler: {str(e)}", 400


# ============ STARTUP ==============

# Startet den Trade-Monitor-Thread IMMER, auch wenn Gunicorn verwendet wird
threading.Thread(target=monitor_loop, daemon=True).start()

