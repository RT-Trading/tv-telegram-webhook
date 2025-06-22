import time
import json
import requests
import os

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
def get_price(symbol):
    symbol = symbol.upper()

    if symbol == "BTCUSD":
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        r = requests.get(url)
        return r.json().get("bitcoin", {}).get("usd", 0)

    # Alpha Vantage API (z. B. EURUSD, NAS100 → NASDAQ wird nicht direkt unterstützt!)
    api_key = os.environ.get("ALPHA_API_KEY")
    url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={symbol[:3]}&to_currency={symbol[3:]}&apikey={api_key}"
    r = requests.get(url)
    data = r.json().get("Realtime Currency Exchange Rate", {})
    return float(data.get("5. Exchange Rate", 0))


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
    price = get_price()
    print(f"🔍 Preis: {price}")

    updated = []
    for t in trades:
        if t["closed"]:
            updated.append(t)
            continue

        entry = t["entry"]
        sl = t["sl"]
        side = t["side"]
        hit = None

        if side == "long":
            if price <= sl:
                hit = "❌ SL erreicht"
            elif price >= t["tp3"]:
                hit = "🏁 TP3 erreicht"
            elif price >= t["tp2"]:
                hit = "✅ TP2 erreicht"
            elif price >= t["tp1"]:
                hit = "✅ TP1 erreicht"
        elif side == "short":
            if price >= sl:
                hit = "❌ SL erreicht"
            elif price <= t["tp3"]:
                hit = "🏁 TP3 erreicht"
            elif price <= t["tp2"]:
                hit = "✅ TP2 erreicht"
            elif price <= t["tp1"]:
                hit = "✅ TP1 erreicht"

        if hit:
            msg = f"*{t['symbol']}* | {side.upper()} | Entry: {entry}\n{hit} bei Preis: {price}"
            send_telegram(msg)
            t["closed"] = True

        updated.append(t)

    save_trades(updated)

if __name__ == "__main__":
    print("🟢 Monitor gestartet…")
    while True:
        try:
            check_trades()
        except Exception as e:
            print("❌ Fehler:", e)
        time.sleep(60)
