import time
import json
import requests
import os
import threading
from datetime import datetime
from flask import Flask

app = Flask(__name__)

# === HARDCODED API-KEYS (zum Testen – später wieder sichern) ===
BOT_TOKEN = "8138998907:AAGe7lTtVqctKW1W2i_ivX8iONPkaUTV_sU"
CHAT_ID = "-1002497064342"
ALPHA_API_KEY = "Y0R96TR1F6ZXP85H"
METALS_API_KEY = "40si7u8md80d0r3c5u096363sm05lvy1imqh25m6ujvcm3xd2damp7wmu57g"

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

    ALPHA_MAP = {
        "XAUUSD": "XAUUSD",
        "SILVER": "XAGUSD",
        "NAS100": "NDX",
        "GER40": "GDAXI",
        "US30": "DJI",
        "US500": "SPX",
        "VIX": "VIX",
        "USDOLLAR": "DX-Y.NYB",
        "GC1!": "XAUUSD"
    }

    FOREX_SYMBOLS = {
        "GBPJPY", "GBPUSD", "EURUSD", "EURJPY", "USDCHF",
        "NZDCHF", "EURGBP", "USDCAD", "AUDJPY", "CHFJPY", "SOLEUR"
    }

    try:
        # === CoinGecko ===
        if symbol in COINGECKO_MAP:
            r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={COINGECKO_MAP[symbol]}&vs_currencies=usd", timeout=10)
            data = r.json()
            print("CoinGecko:", data)
            return float(data[COINGECKO_MAP[symbol]]["usd"])

        # === MetalsAPI ===
        if symbol in ["XAUUSD", "SILVER", "XAGUSD"]:
            base = "XAU" if "XAU" in symbol else "XAG"
            r = requests.get(f"https://metals-api.com/api/latest?access_key={METALS_API_KEY}&base={base}&symbols=USD", timeout=10)
            data = r.json()
            print("MetalsAPI:", data)
            if data.get("success") and "rates" in data and "USD" in data["rates"]:
                return float(data["rates"]["USD"])
            else:
                raise Exception(f"MetalsAPI Fehler: {data}")

        # === Alpha Vantage ===
        av_symbol = ALPHA_MAP.get(symbol, symbol)
        if len(av_symbol) == 6:  # Forex
            r = requests.get(
                f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={av_symbol[:3]}&to_currency={av_symbol[3:]}&apikey={ALPHA_API_KEY}",
                timeout=10
            )
            data = r.json()
            print("Alpha Forex:", data)
            rate = data.get("Realtime Currency Exchange Rate", {}).get("5. Exchange Rate")
            if not rate:
                raise Exception(f"AlphaVantage Forex Fehler: {data}")
            return float(rate)
        else:  # Index
            r = requests.get(
                f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={av_symbol}&interval=5min&apikey={ALPHA_API_KEY}",
                timeout=10
            )
            data = r.json()
            print("Alpha Index:", data)
            ts = data.get("Time Series (5min)")
            if not ts:
                raise Exception(f"AlphaVantage Index Fehler: {data}")
            letzter = next(iter(ts.values()))
            return float(letzter["4. close"])

    except Exception as e:
        log_error(f"❌ Preisabruf Fehler für {symbol}: {e}")

    print(f"❌ Kein Preis für {symbol}")
    return 0

def send_telegram(msg, retry=True):
    try:
        print("📨 Sende:", msg)
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

def log_error(text):
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

        def alert(msg): send_telegram(f"*{symbol}* | *{side.upper()}*\n{msg}\n💰 Preis: `{price:.2f}`")

        if side == "long":
            if not t["sl_hit"] and price <= sl:
                t["sl_hit"] = True
                alert("❌ *SL erreicht – schade. Wir bewerten neu und kommen stärker zurück.*")
                t["closed"] = True
            elif not t["tp1_hit"] and price >= tp1:
                t["tp1_hit"] = True
                alert("🎯 *TP1 erreicht – spätestens jetzt BE setzen oder Trade managen.*")
            elif t["tp1_hit"] and not t["tp2_hit"] and price >= tp2:
                t["tp2_hit"] = True
                alert("📈 *TP2 erreicht – wir machen uns auf den Weg zum Full TP!*")
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
                alert("🎯 *TP1 erreicht – spätestens jetzt BE setzen oder Trade managen.*")
            elif t["tp1_hit"] and not t["tp2_hit"] and price <= tp2:
                t["tp2_hit"] = True
                alert("📈 *TP2 erreicht – wir machen uns auf den Weg zum Full TP!*")
            elif t["tp2_hit"] and not t["tp3_hit"] and price <= tp3:
                t["tp3_hit"] = True
                alert("🎉 *Full TP erreicht – Glückwunsch!*")
                t["closed"] = True

        updated.append(t)

    save_trades(updated)

def monitor_loop():
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler: {e}")
        time.sleep(60)

def monitor_loop():
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler: {e}")
        time.sleep(600)  # statt 60 Sekunden, 10 Minuten warten

