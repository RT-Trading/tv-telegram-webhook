import time
import json
import requests
import os

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ALPHA_API_KEY = os.environ.get("ALPHA_API_KEY")

def get_price(symbol):
    symbol = symbol.upper()

    if symbol == "BTCUSD":
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        try:
            r = requests.get(url)
            return float(r.json().get("bitcoin", {}).get("usd", 0))
        except:
            return 0

    # Alpha Vantage Symbol-Unterstützung prüfen
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


def send_telegram(msg):
    print("📨 Sende:", msg)
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    )

def load_trades():
    if not os.path.exists("trades.json"):
        return []
    with open("trades.json", "r") as f:
        return json.load(f)

def save_trades(trades):
    with open("trades.json", "w") as f:
        json.dump(trades, f, indent=2)

def check_trades():
    trades = load_trades()
    updated = []

    for t in trades:
        if t["closed"]:
            updated.append(t)
            continue

        symbol = t.get("symbol", "").upper()
        entry = t["entry"]
        sl = t["sl"]
        side = t["side"]
        tp1, tp2, tp3 = t["tp1"], t["tp2"], t["tp3"]

        price = get_price(symbol)
        print(f"🔍 {symbol} Preis: {price}")

        if price == 0:
            print(f"⚠️ Kein Preis für {symbol} – übersprungen")
            updated.append(t)
            continue

        # Treffererkennung
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
            # Dynamische Formatierung je nach Symbol
            digits = 5 if symbol in ["EURUSD", "GBPUSD"] else 2
            fmt = f"{{:.{digits}f}}"
            msg = (
                f"*{symbol}* | *{side.upper()}*\n"
                f"{hit}\n"
                f"📍 Entry: `{fmt.format(entry)}`\n"
                f"�



if __name__ == "__main__":
    print("🟢 Monitor gestartet…")
    while True:
        try:
            check_trades()
        except Exception as e:
            print("❌ Fehler:", e)
        time.sleep(60)

