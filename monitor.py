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

    # ✅ CoinGecko: BTCUSD, DOGEUSD, ETHUSD, XRPUSD usw.
    if symbol == "BTCUSD":
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    elif symbol == "DOGEUSD":
        url = "https://api.coingecko.com/api/v3/simple/price?ids=dogecoin&vs_currencies=usd"
    elif symbol == "ETHUSD":
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
    elif symbol == "XRPUSD":
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ripple&vs_currencies=usd"
    else:
        # ✅ AlphaVantage: Forex, Gold, Indizes wie NAS100, GER40, US30
        aliases = {
            "NAS100": "NDX",
            "GER40": "GDAXI",
            "US30": "DJI",
            "US500": "SPX",
            "SILVER": "XAGUSD",
            "GOLD": "XAUUSD"
        }

        # Symbol umwandeln
        av_symbol = aliases.get(symbol, symbol)

        # Gold, Forex usw.
        if av_symbol in ["XAUUSD", "XAGUSD"] or len(av_symbol) == 6:
            from_curr = av_symbol[:3]
            to_curr = av_symbol[3:]
            url = (
                f"https://www.alphavantage.co/query"
                f"?function=CURRENCY_EXCHANGE_RATE"
                f"&from_currency={from_curr}&to_currency={to_curr}"
                f"&apikey={ALPHA_API_KEY}"
            )
        else:
            # Indizes: TIME_SERIES_INTRADAY (z. B. NASDAQ 100)
            url = (
                f"https://www.alphavantage.co/query"
                f"?function=TIME_SERIES_INTRADAY"
                f"&symbol={av_symbol}"
                f"&interval=5min"
                f"&apikey={ALPHA_API_KEY}"
            )
            try:
                r = requests.get(url)
                data = r.json().get("Time Series (5min)", {})
                if not data:
                    return 0
                latest = list(data.values())[0]
                return float(latest["4. close"])
            except:
                return 0

    try:
        r = requests.get(url)
        if "coingecko" in url:
            coin = url.split("ids=")[1].split("&")[0]
            return float(r.json().get(coin, {}).get("usd", 0))
        else:
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

        # Fortschritts-Flags initialisieren
        t.setdefault("tp1_hit", False)
        t.setdefault("tp2_hit", False)
        t.setdefault("tp3_hit", False)
        t.setdefault("sl_hit", False)

        price = get_price(symbol)
        print(f"🔍 {symbol} Preis: {price}")

        if price == 0:
            print(f"⚠️ Kein Preis für {symbol} – übersprungen")
            updated.append(t)
            continue

        digits = 5 if symbol in ["EURUSD", "GBPUSD"] else 2
        fmt = f"{{:.{digits}f}}"

        def format_message(title, icon):
            return (
                f"*{symbol}* | *{side.upper()}*\n"
                f"{icon} {title}\n"
                f"🎯 TP1: `{fmt.format(tp1)}`\n"
                f"🎯 TP2: `{fmt.format(tp2)}`\n"
                f"🏁 Full TP: `{fmt.format(tp3)}`\n"
                f"💰 Preis: `{fmt.format(price)}`"
            )

        if side == "long":
            if not t["sl_hit"] and price <= sl:
                t["sl_hit"] = True
                send_telegram(format_message("❌ SL erreicht", "❌"))
                t["closed"] = True
            elif not t["tp3_hit"] and price >= tp3:
                t["tp3_hit"] = True
                send_telegram(format_message("🏁 Full TP erreicht 🎉", "🏁"))
                t["closed"] = True
            elif not t["tp2_hit"] and price >= tp2:
                t["tp2_hit"] = True
                send_telegram(format_message("✅ TP2 erreicht", "✅"))
            elif not t["tp1_hit"] and price >= tp1:
                t["tp1_hit"] = True
                send_telegram(format_message("✅ TP1 erreicht", "✅"))

        elif side == "short":
            if not t["sl_hit"] and price >= sl:
                t["sl_hit"] = True
                send_telegram(format_message("❌ SL erreicht", "❌"))
                t["closed"] = True
            elif not t["tp3_hit"] and price <= tp3:
                t["tp3_hit"] = True
                send_telegram(format_message("🏁 Full TP erreicht 🎉", "🏁"))
                t["closed"] = True
            elif not t["tp2_hit"] and price <= tp2:
                t["tp2_hit"] = True
                send_telegram(format_message("✅ TP2 erreicht", "✅"))
            elif not t["tp1_hit"] and price <= tp1:
                t["tp1_hit"] = True
                send_telegram(format_message("✅ TP1 erreicht", "✅"))

        updated.append(t)

    save_trades(updated)

if __name__ == "__main__":
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler: {e}")
        time.sleep(60)
