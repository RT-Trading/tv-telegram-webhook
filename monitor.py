import time
import json
import requests
import os
from datetime import datetime

print("🚀 Monitor gestartet")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ALPHA_API_KEY = os.environ.get("ALPHA_API_KEY")

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
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={COINGECKO_MAP[symbol]}&vs_currencies=usd"
            r = requests.get(url, timeout=10)
            preis = float(r.json()[COINGECKO_MAP[symbol]]["usd"])
            print(f"📦 Preis von CoinGecko: {preis}")
            return preis

        if symbol in FOREX_SYMBOLS or symbol in ALPHA_MAP:
            av_symbol = ALPHA_MAP.get(symbol, symbol)
            if len(av_symbol) == 6:
                r = requests.get(
                    f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE"
                    f"&from_currency={av_symbol[:3]}&to_currency={av_symbol[3:]}&apikey={ALPHA_API_KEY}",
                    timeout=10
                )
                preis = float(r.json()["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
                print(f"📦 Preis von AlphaVantage: {preis}")
                return preis
            else:
                r = requests.get(
                    f"https://www.alphavantage.co/query"
                    f"?function=TIME_SERIES_INTRADAY&symbol={av_symbol}&interval=5min&apikey={ALPHA_API_KEY}",
                    timeout=10
                )
                ts = r.json().get("Time Series (5min)", {})
                preis = float(list(ts.values())[0]["4. close"])
                print(f"📦 Preis von AlphaVantage (Index): {preis}")
                return preis

        if symbol in ["XAUUSD", "SILVER", "XAGUSD"]:
            METALS_API_KEY = os.environ.get("METALS_API_KEY")
            metal_code = "XAU" if "XAU" in symbol else "XAG"
            r = requests.get(
                f"https://metals-api.com/api/latest?access_key={METALS_API_KEY}&base=USD&symbols={metal_code}",
                timeout=10
            )
            preis = float(r.json()["rates"][metal_code])
            print(f"📦 Preis von MetalsAPI: {preis}")
            return preis

    except Exception as e:
        log_error(f"Preisabruf Fehler für {symbol}: {e}")

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

if __name__ == "__main__":
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler: {e}")
        time.sleep(60)
