import time
import json
import requests
import os
import threading
from datetime import datetime
from flask import Flask

app = Flask(__name__)

# === ENV-VARIABLEN ===
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
METALS_API_KEY = os.environ.get("METALS_API_KEY")
TWELVE_API_KEY = os.environ.get("TWELVE_API_KEY")

@app.route("/")
def health():
    return "✅ Monitor läuft", 200

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

def send_telegram(msg, retry=True):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
        if r.status_code != 200:
            raise Exception(f"Status {r.status_code}: {r.text}")
        else:
            print(f"📤 Telegram gesendet: {msg}")
    except Exception as e:
        log_error(f"Telegram Fehler: {e}")
        if retry:
            send_telegram(msg, retry=False)

def log_error(text):
    print(f"⚠️ {text}")  # WICHTIG für Render-Logs
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("errors.log", "a") as f:
        f.write(f"[{now}] {text}\n")

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
    send_telegram("✅ *Trade-Monitor gestartet*")  # Test-Message
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler: {e}")
        time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
