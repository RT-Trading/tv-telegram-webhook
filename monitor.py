import time
import json
import requests
import os
from datetime import datetime

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ALPHA_API_KEY = os.environ.get("ALPHA_API_KEY")

def get_price(symbol):
    symbol = symbol.upper()

    # Bitcoin
    if symbol == "BTCUSD":
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        try:
            r = requests.get(url)
            return float(r.json().get("bitcoin", {}).get("usd", 0))
        except:
            return 0

    # Gold
    if symbol == "XAUUSD":
        url = "https://api.coingecko.com/api/v3/simple/price?ids=gold&vs_currencies=usd"
        try:
            r = requests.get(url)
            return float(r.json().get("gold", {}).get("usd", 0))
        except:
            return 0

    # Standard-Forex (via Alpha Vantage)
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

        hit = None
        close_trade = False

        if side == "long":
            if price <= sl:
                hit = "❌ *SL erreicht*"
                close_trade = True
            elif price >= tp3:
                hit = "🏁 *Full TP erreicht*"
                close_trade = True
            elif price >= tp2:
                hit = "✅ *TP2 erreicht*"
            elif price >= tp1:
                hit = "✅ *TP1 erreicht*"
        elif side == "short":
            if price >= sl:
                hit = "❌ *SL erreicht*"
                close_trade = True
            elif price <= tp3:
                hit = "🏁 *Full TP erreicht*"
                close_trade = True
            elif price <= tp2:
                hit = "✅ *TP2 erreicht*"
            elif price <= tp1:
                hit = "✅ *TP1 erreicht*"

        if hit:
            digits = 5 if symbol in ["EURUSD", "GBPUSD"] else 2
            fmt = f"{{:.{digits}f}}"
            msg = (
                f"*{symbol}* | *{side.upper()}*\n"
                f"{hit}\n"
                f"📍 Entry: `{fmt.format(entry)}`\n"
                f"🛑 SL: `{fmt.format(sl)}`\n"
                f"🎯 TP1: `{fmt.format(tp1)}`\n"
                f"🎯 TP2: `{fmt.format(tp2)}`\n"
                f"🏁 Full TP: `{fmt.format(tp3)}`\n"
                f"💰 Aktueller Preis: `{fmt.format(price)}`"
            )
            send_telegram(msg)

        if close_trade:
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
