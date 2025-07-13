import time
import json
import requests
import os
from datetime import datetime

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
METALS_API_KEY = os.environ.get("METALS_API_KEY")
TWELVE_API_KEY = os.environ.get("TWELVE_API_KEY")


def get_price(symbol):
    symbol = symbol.upper()

    if symbol == "BTCUSD":
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        try:
            r = requests.get(url)
            return float(r.json().get("bitcoin", {}).get("usd", 0))
        except:
            return 0

    if symbol == "XAUUSD":
        url = "https://api.coingecko.com/api/v3/simple/price?ids=gold&vs_currencies=usd"
        try:
            r = requests.get(url)
            return float(r.json().get("gold", {}).get("usd", 0))
        except:
            return 0

    from_curr = symbol[:3]
    to_curr = symbol[3:]
    url = (
        f"https://www.alphavantage.co/query"
        f"?function=CURRENCY_EXCHANGE_RATE"
        f"&from_currency={from_curr}&to_currency={to_curr}&apikey={ALPHA_API_KEY}"
    )
    try:
        r = requests.get(url)
        data = r.json().get("Realtime Currency Exchange Rate", {})
        return float(data.get("5. Exchange Rate", 0))
    except:
        return 0

def send_telegram(msg, retry=True):
    try:
        print("📨 Sende:", msg)
        res = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10
        )
        if res.status_code != 200:
            raise Exception(f"Status {res.status_code}: {res.text}")
        time.sleep(1)
    except Exception as e:
        log_error(f"Telegram Fehler: {e}")
        if retry:
            print("🔁 Versuche erneut zu senden…")
            send_telegram(msg, retry=False)

def log_error(error_text):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("errors.log", "a") as f:
        f.write(f"[{now}] {error_text}\n")

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

        t.setdefault("tp1_hit", False)
        t.setdefault("tp2_hit", False)
        t.setdefault("tp3_hit", False)
        t.setdefault("sl_hit", False)

        symbol = t.get("symbol", "").upper()
        entry = t.get("entry")
        sl = t.get("sl")
        side = t.get("side")
        tp1, tp2, tp3 = t.get("tp1"), t.get("tp2"), t.get("tp3")

        price = get_price(symbol)
        print(f"🔍 {symbol} Preis: {price}")

        if price == 0:
            print(f"⚠️ Kein Preis für {symbol} – übersprungen")
            updated.append(t)
            continue

        digits = 5 if symbol in ["EURUSD", "GBPUSD"] else 2
        fmt = f"{{:.{digits}f}}"

        if side == "long":
            if price <= sl and not t["sl_hit"]:
                msg = (
                    f"*{symbol}* | *{side.upper()}*\n"
                    f"❌ *SL erreicht*\n"
                    f"📍 Entry: `{fmt.format(entry)}`\n"
                    f"🛑 SL: `{fmt.format(sl)}`\n"
                    f"💰 Aktueller Preis: `{fmt.format(price)}`"
                )
                send_telegram(msg)
                t["sl_hit"] = True
                t["closed"] = True
            elif price >= tp1 and not t["tp1_hit"]:
                send_telegram(f"*{symbol}* | *{side.upper()}*\n✅ *TP1 erreicht*\n🎯 TP1: `{fmt.format(tp1)}`\n💰 Preis: `{fmt.format(price)}`")
                t["tp1_hit"] = True
            elif price >= tp2 and not t["tp2_hit"]:
                send_telegram(f"*{symbol}* | *{side.upper()}*\n✅ *TP2 erreicht*\n🎯 TP2: `{fmt.format(tp2)}`\n💰 Preis: `{fmt.format(price)}`")
                t["tp2_hit"] = True
            elif price >= tp3 and not t["tp3_hit"]:
                send_telegram(f"*{symbol}* | *{side.upper()}*\n🏁 *Full TP erreicht – Glückwunsch!*\n🏁 TP3: `{fmt.format(tp3)}`\n💰 Preis: `{fmt.format(price)}`")
                t["tp3_hit"] = True
                t["closed"] = True

        elif side == "short":
            if price >= sl and not t["sl_hit"]:
                msg = (
                    f"*{symbol}* | *{side.upper()}*\n"
                    f"❌ *SL erreicht*\n"
                    f"📍 Entry: `{fmt.format(entry)}`\n"
                    f"🛑 SL: `{fmt.format(sl)}`\n"
                    f"💰 Aktueller Preis: `{fmt.format(price)}`"
                )
                send_telegram(msg)
                t["sl_hit"] = True
                t["closed"] = True
            elif price <= tp1 and not t["tp1_hit"]:
                send_telegram(f"*{symbol}* | *{side.upper()}*\n✅ *TP1 erreicht*\n🎯 TP1: `{fmt.format(tp1)}`\n💰 Preis: `{fmt.format(price)}`")
                t["tp1_hit"] = True
            elif price <= tp2 and not t["tp2_hit"]:
                send_telegram(f"*{symbol}* | *{side.upper()}*\n✅ *TP2 erreicht*\n🎯 TP2: `{fmt.format(tp2)}`\n💰 Preis: `{fmt.format(price)}`")
                t["tp2_hit"] = True
            elif price <= tp3 and not t["tp3_hit"]:
                send_telegram(f"*{symbol}* | *{side.upper()}*\n🏁 *Full TP erreicht – Glückwunsch!*\n🏁 TP3: `{fmt.format(tp3)}`\n💰 Preis: `{fmt.format(price)}`")
                t["tp3_hit"] = True
                t["closed"] = True

        updated.append(t)

    save_trades(updated)

if __name__ == "__main__":
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler: {e}")
        time.sleep(60)


**************************

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

    # Prozentuale Methode (für Gold etc.)
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

        print("🧪 Nachricht an Telegram:", msg)
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
  äääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääääää 
    
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
ALPHA_API_KEY = os.environ.get("ALPHA_API_KEY")
METALS_API_KEY = os.environ.get("METALS_API_KEY")  # nicht hardcoden!

first_run = True  # Verhindert Alerts beim ersten Start

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
        if symbol in COINGECKO_MAP:
            r = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={COINGECKO_MAP[symbol]}&vs_currencies=usd", timeout=10)
            return float(r.json()[COINGECKO_MAP[symbol]]["usd"])

        if symbol in ["XAUUSD", "SILVER", "XAGUSD"]:
            base = "XAU" if "XAU" in symbol else "XAG"
            r = requests.get(f"https://metals-api.com/api/latest?access_key={METALS_API_KEY}&base={base}&symbols=USD", timeout=10)
            data = r.json()
            if data.get("success") and "rates" in data and "USD" in data["rates"]:
                return float(data["rates"]["USD"])
            else:
                raise Exception(f"MetalsAPI Fehler: {data}")

        av_symbol = ALPHA_MAP.get(symbol, symbol)
        if len(av_symbol) == 6:
            r = requests.get(f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={av_symbol[:3]}&to_currency={av_symbol[3:]}&apikey={ALPHA_API_KEY}", timeout=10)
            rate = r.json().get("Realtime Currency Exchange Rate", {}).get("5. Exchange Rate")
            return float(rate) if rate else 0
        else:
            r = requests.get(f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={av_symbol}&interval=5min&apikey={ALPHA_API_KEY}", timeout=10)
            ts = r.json().get("Time Series (5min)")
            if not ts:
                raise Exception(f"AlphaVantage Index Fehler: {r.json()}")
            letzter = next(iter(ts.values()))
            return float(letzter["4. close"])
    except Exception as e:
        log_error(f"❌ Preisabruf Fehler für {symbol}: {e}")
        return 0

def send_telegram(msg, retry=True):
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
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
    global first_run
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
            if first_run:
                print(f"⏭️ {symbol}: Erste Runde – überspringe Alert")
                return
            send_telegram(f"*{symbol}* | *{side.upper()}*\n{msg}\n💰 Preis: `{price:.2f}`")


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
    first_run = False  # erst nach dem ersten Check Alerts erlauben

def monitor_loop():
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler: {e}")
        time.sleep(60)

# Start
if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)


all in one

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
    threading.Thread(target=monitor_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)


📋 Nächste Schritte

    Speichere das Skript als main.py

    Stelle sicher, dass trades.json existiert (auch wenn leer):

[]

    Erstelle eine Datei requirements.txt mit folgendem Inhalt:

Flask
requests

    Deploy auf Render oder starte lokal:

python main.py

Wenn du willst, kann ich dir ein fertiges ZIP mit allen Dateien geben. Sag einfach Bescheid. ✅
