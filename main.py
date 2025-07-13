import os
import time
import json
import requests
import threading
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)

# === ENV-VARIABLEN ===
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
METALS_API_KEY = os.environ.get("METALS_API_KEY")
TWELVE_API_KEY = os.environ.get("TWELVE_API_KEY")

# === Telegram senden ===
def send_telegram(msg, retry=True):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
        if r.status_code != 200:
            raise Exception(f"Status {r.status_code}: {r.text}")
    except Exception as e:
        log_error(f"Telegram Fehler: {e}")
        if retry:
            send_telegram(msg, retry=False)

# === Logging ===
def log_error(text):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("errors.log", "a") as f:
        f.write(f"[{now}] {text}\n")

# === Preisabruf ===
def get_price(symbol):
    symbol = symbol.upper()

    COINGECKO_MAP = {
        "BTCUSD": "bitcoin",
        "ETHUSD": "ethereum",
        "XRPUSD": "ripple",
        "DOGEUSD": "dogecoin"
    }

    TWELVE_MAP = {
        "EURUSD": "EUR/USD",
        "GBPUSD": "GBP/USD",
        "GBPJPY": "GBP/JPY",
        "NAS100": "NDX",
        "US30": "DJI",
        "US500": "SPX",
        "GER40": "DAX"
    }

    try:
        if symbol in COINGECKO_MAP:
            r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={COINGECKO_MAP[symbol]}&vs_currencies=usd", timeout=10)
            data = r.json()
            return float(data[COINGECKO_MAP[symbol]]["usd"])

        if symbol in ["XAUUSD", "SILVER", "XAGUSD"]:
            base = "XAU" if "XAU" in symbol else "XAG"
            r = requests.get(f"https://metals-api.com/api/latest?access_key={METALS_API_KEY}&base={base}&symbols=USD", timeout=10)
            data = r.json()
            if data.get("success") and "rates" in data and "USD" in data["rates"]:
                return float(data["rates"]["USD"])
            else:
                raise Exception(f"MetalsAPI Fehler: {data}")

        if symbol in TWELVE_MAP:
            sym = TWELVE_MAP[symbol]
            r = requests.get(f"https://api.twelvedata.com/price?symbol={sym}&apikey={TWELVE_API_KEY}", timeout=10)
            data = r.json()
            if "price" in data:
                return float(data["price"])
            else:
                raise Exception(f"TwelveData Fehler: {data}")

    except Exception as e:
        log_error(f"❌ Preisabruf Fehler für {symbol}: {e}")

    return 0

# === Trades speichern und laden ===
def load_trades():
    if not os.path.exists("trades.json"):
        return []
    try:
        with open("trades.json", "r") as f:
            return json.load(f)
    except Exception as e:
        log_error(f"Fehler beim Laden von trades.json: {e}")
        return []

def save_trades(trades):
    try:
        with open("trades.json", "w") as f:
            json.dump(trades, f, indent=2)
    except Exception as e:
        log_error(f"Fehler beim Speichern von trades.json: {e}")

# === Check Trades für TP / SL ===
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

        def alert(msg): send_telegram(f"*{symbol}* | *{side.upper()}*\n{msg}\n💰 Preis: `{price:.2f}`")

        if side == "long":
            if not t["sl_hit"] and price <= sl:
                t["sl_hit"] = True
                alert("❌ *SL erreicht – schade. Wir bewerten neu und kommen stärker zurück.*")
                t["closed"] = True
            elif not t["tp1_hit"] and price >= tp1:
                t["tp1_hit"] = True
                alert("🌟 *TP1 erreicht – BE setzen oder Trade managen.*")
            elif t["tp1_hit"] and not t["tp2_hit"] and price >= tp2:
                t["tp2_hit"] = True
                alert("📈 *TP2 erreicht – auf dem Weg zum Full TP!*")
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
                alert("🌟 *TP1 erreicht – BE setzen oder Trade managen.*")
            elif t["tp1_hit"] and not t["tp2_hit"] and price <= tp2:
                t["tp2_hit"] = True
                alert("📈 *TP2 erreicht – auf dem Weg zum Full TP!*")
            elif t["tp2_hit"] and not t["tp3_hit"] and price <= tp3:
                t["tp3_hit"] = True
                alert("🎉 *Full TP erreicht – Glückwunsch!*")
                t["closed"] = True

        updated.append(t)

    save_trades(updated)

# === SL/TP Berechnung ===
def calc_sl(entry, side):
    risk_pct = 0.005
    return entry * (1 - risk_pct) if side == 'long' else entry * (1 + risk_pct)

def calc_tp(entry, sl, side, symbol):
    if symbol == "XAUUSD":
        tp_pct = [0.004, 0.008, 0.012]
    else:
        risk = abs(entry - sl)
        if side == 'long':
            return entry + 2 * risk, entry + 3.6 * risk, entry + 5.6 * risk
        else:
            return entry - 2 * risk, entry - 3.6 * risk, entry - 5.6 * risk

    if side == "long":
        return entry * (1 + tp_pct[0]), entry * (1 + tp_pct[1]), entry * (1 + tp_pct[2])
    else:
        return entry * (1 - tp_pct[0]), entry * (1 - tp_pct[1]), entry * (1 - tp_pct[2])

# === Webhook Empfang von TradingView ===
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        raw_data = request.data.decode("utf-8")
        data = json.loads(raw_data)
        print("📩 Empfangen:", data)

        entry = float(data.get("entry", 0))
        side = (data.get("side") or data.get("direction") or "").strip().lower()
        symbol = str(data.get("symbol", "")).strip().upper()

        if not entry or side not in ["long", "short"] or not symbol:
            raise ValueError("❌ Ungültige Daten")

        sl = calc_sl(entry, side)
        tp1, tp2, tp3 = calc_tp(entry, sl, side, symbol)

        msg = f"""🔔 *RT-Trading VIP* 🔔  
📊 *{symbol}*  
{"🟢 *LONG*" if side == 'long' else "🔴 *SHORT*"} 📈📉

📍 *Entry*: `{entry:.2f}`  
🛑 *SL*: `{sl:.2f}`

🎯 *TP1*: `{tp1:.2f}`  
🎯 *TP2*: `{tp2:.2f}`  
🎯 *TP3*: `{tp3:.2f}`

⚠️ *Keine Finanzberatung!*  
🔁 TP1 erreicht → BE setzen!
"""
        send_telegram(msg)

        # === Speichern ===
        trades = load_trades()
        trades.append({
            "symbol": symbol, "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
            "side": side, "tp1_hit": False, "tp2_hit": False, "tp3_hit": False, "sl_hit": False, "closed": False
        })
        save_trades(trades)
        return "✅ OK", 200

    except Exception as e:
        log_error(f"Webhook Fehler: {e}")
        return f"❌ Fehler: {e}", 400

@app.route("/")
def health():
    return "✅ Läuft", 200

@app.route("/trades")
def trades_view():
    try:
        with open("trades.json", "r") as f:
            return f.read(), 200, {'Content-Type': 'application/json'}
    except:
        return "[]", 200

# === Start Überwachung ===
def monitor_loop():
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler: {e}")
        time.sleep(600)  # alle 10 Min

# === Start Server ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
