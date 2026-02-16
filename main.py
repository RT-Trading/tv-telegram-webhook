import os
import time
import json
import threading
from datetime import datetime, timezone
from flask import Flask, request
import requests

app = Flask(__name__)

# =============================================================================
# ENV
# =============================================================================
BOT_TOKEN      = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID        = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
METALS_API_KEY = os.environ.get("METALS_API_KEY", "").strip()
TWELVE_API_KEY = os.environ.get("TWELVE_API_KEY", "").strip()

# Optional (empfohlen): Secret-Key gegen fremde Webhook-Calls
# In Render als ENV setzen: RT_SECRET=irgendein_geheimes_passwort
RT_SECRET = os.environ.get("RT_SECRET", "").strip()

# =============================================================================
# NEU: BOT SIGNAL HUB (nur ENTRY Signale speichern, kein SL/TP Calc, kein Monitor)
# =============================================================================
BOT_SIGNALS_FILE = os.environ.get("BOT_SIGNALS_FILE", "bot_signals.json").strip()
BOT_SIGNALS_MAX  = int(os.environ.get("BOT_SIGNALS_MAX", "3000"))

_lock_bot = threading.Lock()

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def load_bot_signals():
    if not os.path.exists(BOT_SIGNALS_FILE):
        return []
    try:
        with _lock_bot:
            with open(BOT_SIGNALS_FILE, "r") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except Exception as e:
        print(f"Fehler beim Laden von {BOT_SIGNALS_FILE}: {e}")
        return []

def save_bot_signals(signals):
    try:
        with _lock_bot:
            with open(BOT_SIGNALS_FILE, "w") as f:
                json.dump(signals, f, indent=2)
    except Exception as e:
        print(f"Fehler beim Speichern von {BOT_SIGNALS_FILE}: {e}")

def normalize_side(raw) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    u = s.upper()
    if u in ["LONG", "BUY", "BULL"]:
        return "long"
    if u in ["SHORT", "SELL", "BEAR"]:
        return "short"
    l = s.lower()
    if l in ["long", "short"]:
        return l
    return ""

def parse_float(v):
    try:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None

def parse_entry(data: dict) -> float:
    # akzeptiert: entry oder price oder close
    return parse_float(data.get("entry")) or parse_float(data.get("price")) or parse_float(data.get("close")) or 0.0

def build_signal_id(symbol: str, side: str, tf: str, t: str) -> str:
    # stabile Dedup-ID, wenn TV mehrfach feuert
    base = f"{symbol}_{side}_{tf}_{t}"
    return base.replace(" ", "").replace(":", "").replace("-", "").replace(".", "")

def save_bot_signal(symbol, side, entry, tf, slf=None, tv_time=None, raw=None):
    signals = load_bot_signals()

    tv_time = (tv_time or "").strip()
    tf = (tf or "-").strip()

    sig_id = build_signal_id(symbol, side, tf, tv_time or utc_now_iso())

    # Dedup (letzte 500 prüfen)
    for s in reversed(signals[-500:]):
        if s.get("id") == sig_id:
            return False, "duplicate"

    sig = {
        "id": sig_id,
        "cmd": "ENTRY",
        "symbol": symbol,
        "side": side,
        "tf": tf,
        "entry": float(entry),
        "slf": float(slf) if slf is not None else None,
        "time": tv_time,
        "received_at": utc_now_iso(),
        "raw": raw or {}
    }

    signals.append(sig)
    if BOT_SIGNALS_MAX > 0 and len(signals) > BOT_SIGNALS_MAX:
        signals = signals[-BOT_SIGNALS_MAX:]

    save_bot_signals(signals)
    return True, "saved"

# =============================================================================
# GRUND-FUNKTIONEN (ALT – NICHT ÄNDERN)
# =============================================================================
def calc_sl(entry: float, side: str) -> float:
    risk_pct = 0.005
    return entry * (1 - risk_pct) if side == "long" else entry * (1 + risk_pct)

def calc_tp(entry: float, sl: float, side: str, symbol: str):
    metals = ["XAUUSD", "SILVER"]
    risk = abs(entry - sl)
    if symbol in metals:
        tp_pct = [0.004, 0.008, 0.012]
        if side == "long":
            return entry * (1 + tp_pct[0]), entry * (1 + tp_pct[1]), entry * (1 + tp_pct[2])
        else:
            return entry * (1 - tp_pct[0]), entry * (1 - tp_pct[1]), entry * (1 - tp_pct[2])
    else:
        if side == "long":
            return entry + 2 * risk, entry + 3.6 * risk, entry + 5.6 * risk
        else:
            return entry - 2 * risk, entry - 3.6 * risk, entry - 5.6 * risk

def format_message(symbol: str, entry: float, sl: float, tp1: float, tp2: float, tp3: float, side: str) -> str:
    five_digits  = ["EURUSD", "GBPUSD", "GBPJPY"]
    three_digits = ["USDJPY"]
    two_digits   = ["BTCUSD", "NAS100", "XAUUSD", "SILVER", "US30", "US500", "GER40"]

    if symbol in five_digits:
        digits = 5
    elif symbol in three_digits:
        digits = 3
    elif symbol in two_digits:
        digits = 2
    else:
        digits = 4

    fmt = f"{{:.{digits}f}}"
    direction = "🟢 *LONG* 📈" if side == "long" else "🔴 *SHORT* 📉"

    return f"""\
🔔 *RT-Trading VIP* 🔔  
📊 *{symbol}*  
{direction}

📍 *Entry*: `{fmt.format(entry)}`  
🛑 *SL*: `{fmt.format(sl)}`

🎯 *TP 1*: `{fmt.format(tp1)}`  
🎯 *TP 2*: `{fmt.format(tp2)}`  
🎯 *Full TP*: `{fmt.format(tp3)}`

⚠️ *Keine Finanzberatung!*  
📌 Achtet auf *Money Management*!  
🔀 TP1 erreicht → *Breakeven setzen*.
"""

def send_telegram(text: str, retry: bool = True):
    try:
        if not BOT_TOKEN or not CHAT_ID:
            raise Exception("TELEGRAM_BOT_TOKEN oder TELEGRAM_CHAT_ID fehlt")

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }
        r = requests.post(url, data=payload, timeout=10)
        print("📱 Telegram Response:", r.status_code, r.text)
        if r.status_code != 200:
            raise Exception("Telegram-Fehler")
    except Exception as e:
        print(f"Telegram Fehler: {e}")
        if retry:
            send_telegram(text, retry=False)

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

def save_trade(symbol, entry, sl, tp1, tp2, tp3, side, meta=None):
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
        "closed": False,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "meta": meta or {}
    }
    trades = load_trades()
    trades.append(trade)
    save_trades(trades)

def log_error(text: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open("errors.log", "a") as f:
            f.write(f"[{now}] {text}\n")
    except Exception:
        pass
    print(f"⚠️ {text}")

# =============================================================================
# SYMBOL-MAPPING FÜR TWELVE DATA (ALT)
# =============================================================================
def convert_symbol_for_twelve(symbol: str) -> str:
    symbol_map = {
        "XAUUSD": "XAU/USD",
        "XAGUSD": "XAG/USD",
        "SILVER": "XAG/USD",
        "GOLD": "XAU/USD",
        "BTCUSD": "BTC/USD",
        "ETHUSD": "ETH/USD",
        "US30": "DJI",
        "US500": "SPX",
        "NAS100": "NDX",
        "GER40": "DAX"
    }
    return symbol_map.get(symbol.upper(), symbol)

# =============================================================================
# PREISABFRAGE (ALT)
# =============================================================================
def get_price(symbol: str) -> float:
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
            if METALS_API_KEY:
                try:
                    r = requests.get(
                        f"https://metals-api.com/api/latest?access_key={METALS_API_KEY}&base={base}&symbols=USD",
                        timeout=10
                    )
                    data = r.json()
                    if data.get("success") and "rates" in data and "USD" in data["rates"]:
                        return float(data["rates"]["USD"])
                    else:
                        raise Exception(f"MetalsAPI Fehler: {data}")
                except Exception as e:
                    log_error(f"⚠️ MetalsAPI Fallback für {symbol}: {e}")

        if not TWELVE_API_KEY:
            raise Exception("TWELVE_API_KEY fehlt (Fallback nicht möglich)")

        symbol_twelve = convert_symbol_for_twelve(symbol)
        r = requests.get(
            f"https://api.twelvedata.com/price?symbol={symbol_twelve}&apikey={TWELVE_API_KEY}",
            timeout=10
        )
        data = r.json()
        if "price" in data and isinstance(data["price"], str):
            return float(data["price"])
        raise Exception(f"Twelve Data Fehler: {data}")

    except Exception as e:
        log_error(f"❌ Preisabruf Fehler für {symbol}: {e}")
        return 0.0

# =============================================================================
# MONITOR LOGIK (ALT)
# =============================================================================
def check_trades():
    trades = load_trades()
    updated = []

    for t in trades:
        if t.get("closed"):
            updated.append(t)
            continue

        symbol = (t.get("symbol", "") or "").upper()
        entry  = t.get("entry")
        sl     = t.get("sl")
        side   = t.get("side")
        tp1    = t.get("tp1")
        tp2    = t.get("tp2")
        tp3    = t.get("tp3")

        t.setdefault("tp1_hit", False)
        t.setdefault("tp2_hit", False)
        t.setdefault("tp3_hit", False)
        t.setdefault("sl_hit", False)

        price = get_price(symbol)
        print(f"🔍 {symbol} Preis: {price}")
        if price == 0:
            updated.append(t)
            continue

        def alert(msg: str):
            text = f"*{symbol}* | *{str(side).upper()}*\n{msg}"
            send_telegram(text)

        if side == "long":
            if not t["tp1_hit"] and price >= tp1:
                t["tp1_hit"] = True
                alert("💶 *TP1 erreicht – BE setzen oder Trade managen. Wir machen uns auf den Weg zu TP2!* 🚀")
            elif t["tp1_hit"] and not t["tp2_hit"] and price >= tp2:
                t["tp2_hit"] = True
                alert("💶 *TP2 erreicht – weiter geht’s! Full TP in Sicht!* ✨")
            elif t["tp2_hit"] and not t["tp3_hit"] and price >= tp3:
                t["tp3_hit"] = True
                alert("🏆 *Full TP erreicht – Glückwunsch an alle! 💶💶💰🥳*")
                t["closed"] = True
            elif not t["tp1_hit"] and not t["sl_hit"] and price <= sl:
                t["sl_hit"] = True
                alert("🛑 *SL erreicht – schade. Wir bewerten neu und kommen stärker zurück.*")
                t["closed"] = True
            elif t["tp1_hit"] and not t["closed"] and price <= entry:
                alert("💰 *Trade teilweise im Gewinn geschlossen – TP1/TP2 wurden erreicht, Rest auf Entry beendet.*")
                t["closed"] = True

        elif side == "short":
            if not t["tp1_hit"] and price <= tp1:
                t["tp1_hit"] = True
                alert("💶 *TP1 erreicht – BE setzen oder Trade managen. Wir machen uns auf den Weg zu TP2!* 🚀")
            elif t["tp1_hit"] and not t["tp2_hit"] and price <= tp2:
                t["tp2_hit"] = True
                alert("💶 *TP2 erreicht – weiter geht’s! Full TP in Sicht!* ✨")
            elif t["tp2_hit"] and not t["tp3_hit"] and price <= tp3:
                t["tp3_hit"] = True
                alert("🏆 *Full TP erreicht – Glückwunsch an alle! 💶💶💰🥳*")
                t["closed"] = True
            elif not t["tp1_hit"] and not t["sl_hit"] and price >= sl:
                t["sl_hit"] = True
                alert("🛑 *SL erreicht – schade. Wir bewerten neu und kommen stärker zurück.*")
                t["closed"] = True
            elif t["tp1_hit"] and not t["closed"] and price >= entry:
                alert("💰 *Trade teilweise im Gewinn geschlossen – TP1/TP2 wurden erreicht, Rest auf Entry beendet.*")
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
        time.sleep(180)

def start_monitor_delayed():
    time.sleep(3)
    monitor_loop()

# =============================================================================
# FLASK ROUTES
# =============================================================================
@app.route("/")
def health():
    return "✅ Monitor läuft", 200

@app.route("/trades", methods=["GET"])
def show_trades():
    try:
        trades = load_trades()
        return json.dumps(trades, indent=2), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return f"Fehler beim Laden: {e}", 500

# ✅ ALT /webhook bleibt unverändert (VIP / Telegram)
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True) or {}
        print("📬 Empfangen:", data)

        if RT_SECRET:
            if str(data.get("key", "")).strip() != RT_SECRET:
                return "❌ Unauthorized", 401

        cmd = (data.get("cmd") or "").strip().upper()
        if cmd and cmd != "ENTRY":
            return "✅ Ignored (cmd)", 200

        symbol = str(data.get("symbol", "")).strip().upper()
        side   = normalize_side(data.get("side") or data.get("direction"))
        entry  = parse_entry(data)

        if not symbol or side not in ["long", "short"] or entry <= 0:
            raise ValueError("❌ Ungültige Daten (symbol/side/entry)")

        sl = calc_sl(entry, side)
        tp1, tp2, tp3 = calc_tp(entry, sl, side, symbol)

        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)
        send_telegram(msg)

        meta = {
            "tf": data.get("tf"),
            "time": data.get("time"),
            "raw": {"cmd": cmd}
        }
        save_trade(symbol, entry, sl, tp1, tp2, tp3, side, meta=meta)

        return "✅ OK", 200

    except Exception as e:
        print("❌ Fehler:", str(e))
        return f"❌ Fehler: {str(e)}", 400

@app.route("/add_manual", methods=["POST"])
def add_manual():
    try:
        data = request.get_json(force=True) or {}

        symbol = str(data.get("symbol", "")).strip().upper()
        side   = normalize_side(data.get("side"))
        entry  = float(data.get("entry", 0) or 0)

        sl  = float(data.get("sl", 0) or 0)
        tp1 = float(data.get("tp1", 0) or 0)
        tp2 = float(data.get("tp2", 0) or 0)
        tp3 = float(data.get("tp3", 0) or 0)

        if not all([symbol, entry, side, sl, tp1, tp2, tp3]) or side not in ["long", "short"]:
            return "❌ Ungültige Daten", 400

        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)
        send_telegram(msg)

        save_trade(symbol, entry, sl, tp1, tp2, tp3, side, meta={"manual": True})
        return "✅ Manuell hinzugefügt", 200

    except Exception as e:
        log_error(f"❌ Fehler beim manuellen Import: {e}")
        return f"❌ Fehler: {e}", 500

# =============================================================================
# NEU: BOT ROUTES
# =============================================================================
@app.route("/bot_signals", methods=["GET"])
def bot_signals_get():
    try:
        signals = load_bot_signals()
        # optional: ?limit=200
        try:
            limit = int(request.args.get("limit", "200"))
        except Exception:
            limit = 200
        limit = max(1, min(5000, limit))
        out = signals[-limit:]
        return json.dumps(out, indent=2), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return f"Fehler: {e}", 500

@app.route("/bot_webhook", methods=["POST"])
def bot_webhook():
    try:
        data = request.get_json(force=True) or {}
        print("🤖 BOT Webhook empfangen:", data)

        # gleiche Security wie VIP (du wolltest nichts ändern -> wir nutzen RT_SECRET)
        if RT_SECRET:
            if str(data.get("key", "")).strip() != RT_SECRET:
                return "❌ Unauthorized", 401

        cmd = (data.get("cmd") or "").strip().upper()
        if cmd and cmd != "ENTRY":
            return "✅ Ignored (cmd)", 200

        symbol = str(data.get("symbol", "")).strip().upper()
        side   = normalize_side(data.get("side") or data.get("direction"))
        entry  = parse_entry(data)
        tf     = str(data.get("tf") or data.get("timeframe") or "").strip()
        tv_time = str(data.get("time") or "").strip()
        slf    = parse_float(data.get("slf"))

        if not symbol or side not in ["long", "short"] or entry <= 0:
            return "❌ Ungültige Daten (symbol/side/entry)", 400

        ok, why = save_bot_signal(
            symbol=symbol,
            side=side,
            entry=entry,
            tf=tf,
            slf=slf,
            tv_time=tv_time,
            raw=data
        )

        if why == "duplicate":
            return "✅ Duplicate ignored", 200

        # absichtlich KEIN Telegram hier (damit VIP nicht doppelt spamt)
        return "✅ OK", 200

    except Exception as e:
        print("❌ BOT Fehler:", str(e))
        return f"❌ Fehler: {str(e)}", 400

# =============================================================================
# STARTUP (ALT Monitor bleibt)
# =============================================================================
threading.Thread(target=start_monitor_delayed, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
