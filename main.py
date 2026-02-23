import os
import time
import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# =============================================================================
# ENV
# =============================================================================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
METALS_API_KEY = os.environ.get("METALS_API_KEY", "").strip()
TWELVE_API_KEY = os.environ.get("TWELVE_API_KEY", "").strip()

# MetalsAPI bei 429 temporär aussetzen
METALS_API_COOLDOWN_UNTIL = 0.0

# Security
RT_SECRET = os.environ.get("RT_SECRET", "").strip()
VIP_SECRET = os.environ.get("VIP_SECRET", "").strip() or RT_SECRET
BOT_SECRET = os.environ.get("BOT_SECRET", "").strip() or RT_SECRET

# Files
TRADES_FILE = os.environ.get("TRADES_FILE", "trades.json").strip()
ERRORS_FILE = os.environ.get("ERRORS_FILE", "errors.log").strip()

BOT_SIGNALS_FILE = os.environ.get("BOT_SIGNALS_FILE", "bot_signals.json").strip()
BOT_SIGNALS_MAX = int(os.environ.get("BOT_SIGNALS_MAX", "3000"))
BOT_STATE_FILE = os.environ.get("BOT_STATE_FILE", "bot_state.json").strip()
BOT_CLIENTS_FILE = os.environ.get("BOT_CLIENTS_FILE", "bot_clients.json").strip()

RUN_MONITOR = os.environ.get("RUN_MONITOR", "1").strip() != "0"

# =============================================================================
# MONITOR TUNING (VIP TELEGRAM)
# =============================================================================
# Polling für VIP-Trade-Monitor (wichtig für TP3/BE Erkennung)
MONITOR_POLL_SEC = max(1, int(os.environ.get("MONITOR_POLL_SEC", "3")))

# Debug-Logs für Monitor (Preis/TP/Flags)
MONITOR_DEBUG = os.environ.get("MONITOR_DEBUG", "1").strip() != "0"

# Kleine Toleranz gegen Rundung/Feed-Unterschiede (relativ zum Zielpreis)
# Beispiel 0.00005 = 0.005%
TRIGGER_EPS_PCT = float(os.environ.get("TRIGGER_EPS_PCT", "0.00005"))

# =============================================================================
# BOT DELIVERY BEHAVIOR (für cTrader-Hub, bleibt drin)
# =============================================================================
BOT_NEW_CLIENT_BASELINE = os.environ.get("BOT_NEW_CLIENT_BASELINE", "1").strip() != "0"
BOT_AUTO_ACK_ON_GET = os.environ.get("BOT_AUTO_ACK_ON_GET", "1").strip() != "0"
BOT_BASELINE_GRACE_SEC = int(os.environ.get("BOT_BASELINE_GRACE_SEC", "120"))

# =============================================================================
# LOCKS
# =============================================================================
_lock_trades = threading.RLock()
_lock_bot = threading.RLock()
_lock_state = threading.RLock()
_lock_clients = threading.RLock()

# requests Session (leichter/stabiler)
_http = requests.Session()

# =============================================================================
# BASICS
# =============================================================================
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso_utc(s: str):
    try:
        if not s:
            return None
        s = str(s).strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def log_error(text: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{now}] {text}"
    try:
        with open(ERRORS_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(f"⚠️ {line}")


def log_info(text: str):
    print(text)


def _safe_read_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_error(f"JSON Read Fehler {path}: {e}")
        return default


def _safe_write_json_atomic(path: str, data) -> bool:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        log_error(f"JSON Write Fehler {path}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def require_secret(data: dict, purpose: str) -> bool:
    secret = VIP_SECRET if purpose == "vip" else BOT_SECRET
    if secret:
        if str(data.get("key", "")).strip() != secret:
            return False
    return True


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
        s = str(v).strip().replace(",", ".")
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def parse_entry(data: dict) -> float:
    # unterstützt entry / price / close
    return (
        parse_float(data.get("entry"))
        or parse_float(data.get("price"))
        or parse_float(data.get("close"))
        or 0.0
    )


def normalize_symbol_tv(symbol: str) -> str:
    s = (symbol or "").strip()
    if ":" in s:
        s = s.split(":")[-1]
    s = s.upper().replace(" ", "")

    syn = {
        "GOLD": "XAUUSD",
        "SILVER": "XAGUSD",
        "XAUUSD": "XAUUSD",
        "XAGUSD": "XAGUSD",
        "NAS100": "NAS100",
        "US100": "NAS100",
        "US30": "US30",
        "GER40": "GER40",
    }
    return syn.get(s, s)


def num_digits_for_symbol(symbol: str) -> int:
    symbol = (symbol or "").upper()
    five_digits = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF"}
    three_digits = {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY"}
    two_digits = {"BTCUSD", "NAS100", "XAUUSD", "XAGUSD", "SILVER", "US30", "US500", "GER40"}
    if symbol in five_digits:
        return 5
    if symbol in three_digits:
        return 3
    if symbol in two_digits:
        return 2
    return 4


def fmt_price(symbol: str, value: float) -> str:
    d = num_digits_for_symbol(symbol)
    return f"{float(value):.{d}f}"


def trigger_eps_abs(target: float) -> float:
    if target is None:
        return 0.0
    try:
        return abs(float(target)) * max(0.0, TRIGGER_EPS_PCT)
    except Exception:
        return 0.0


def hit_tp_long(price: float, target: float) -> bool:
    return price >= (target - trigger_eps_abs(target))


def hit_tp_short(price: float, target: float) -> bool:
    return price <= (target + trigger_eps_abs(target))


def hit_sl_long(price: float, sl: float) -> bool:
    return price <= (sl + trigger_eps_abs(sl))


def hit_sl_short(price: float, sl: float) -> bool:
    return price >= (sl - trigger_eps_abs(sl))


def back_to_entry_long(price: float, entry: float) -> bool:
    return price <= (entry + trigger_eps_abs(entry))


def back_to_entry_short(price: float, entry: float) -> bool:
    return price >= (entry - trigger_eps_abs(entry))

# =============================================================================
# TELEGRAM
# =============================================================================
def send_telegram(text: str, retries: int = 1):
    if not BOT_TOKEN or not CHAT_ID:
        log_error("Telegram nicht konfiguriert (BOT_TOKEN/CHAT_ID fehlt)")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}

    last_err = None
    attempts = max(1, int(retries) + 1)
    for attempt in range(1, attempts + 1):
        try:
            r = _http.post(url, data=payload, timeout=10)
            print("📱 Telegram Response:", r.status_code, r.text)
            if r.status_code == 200:
                return True
            last_err = f"HTTP {r.status_code}: {r.text}"
        except Exception as e:
            last_err = str(e)

        if attempt < attempts:
            time.sleep(1)

    log_error(f"Telegram Fehler: {last_err}")
    return False

# =============================================================================
# TRADES (VIP-Monitor)
# =============================================================================
def load_trades() -> List[Dict[str, Any]]:
    with _lock_trades:
        data = _safe_read_json(TRADES_FILE, [])
        return data if isinstance(data, list) else []


def save_trades(trades: List[Dict[str, Any]]):
    with _lock_trades:
        _safe_write_json_atomic(TRADES_FILE, trades)


def save_trade(symbol, entry, sl, tp1, tp2, tp3, side, meta=None):
    trade = {
        "symbol": symbol,
        "entry": float(entry),
        "sl": float(sl),
        "tp1": float(tp1),
        "tp2": float(tp2),
        "tp3": float(tp3),
        "side": side,
        "tp1_hit": False,
        "tp2_hit": False,
        "tp3_hit": False,
        "sl_hit": False,
        "closed": False,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "last_price": None,
        "last_check_at": None,
        "close_reason": None,
        "meta": meta or {},
    }
    trades = load_trades()
    trades.append(trade)
    save_trades(trades)

# =============================================================================
# VIP: SL/TP/MSG
# =============================================================================
def calc_sl(entry: float, side: str) -> float:
    risk_pct = 0.005
    return entry * (1 - risk_pct) if side == "long" else entry * (1 + risk_pct)


def calc_tp(entry: float, sl: float, side: str, symbol: str):
    metals = {"XAUUSD", "XAGUSD", "SILVER", "GOLD"}
    risk = abs(entry - sl)
    if symbol in metals:
        tp_pct = [0.004, 0.008, 0.012]
        if side == "long":
            return entry * (1 + tp_pct[0]), entry * (1 + tp_pct[1]), entry * (1 + tp_pct[2])
        return entry * (1 - tp_pct[0]), entry * (1 - tp_pct[1]), entry * (1 - tp_pct[2])

    if side == "long":
        return entry + 2 * risk, entry + 3.6 * risk, entry + 5.6 * risk
    return entry - 2 * risk, entry - 3.6 * risk, entry - 5.6 * risk


def format_message(symbol: str, entry: float, sl: float, tp1: float, tp2: float, tp3: float, side: str) -> str:
    direction = "🟢 *LONG* 📈" if side == "long" else "🔴 *SHORT* 📉"
    return f"""\
🔔 *RT-Trading VIP* 🔔
📊 *{symbol}*
{direction}

📍 *Entry*: `{fmt_price(symbol, entry)}`
🛑 *SL*: `{fmt_price(symbol, sl)}`

🎯 *TP 1*: `{fmt_price(symbol, tp1)}`
🎯 *TP 2*: `{fmt_price(symbol, tp2)}`
🎯 *Full TP*: `{fmt_price(symbol, tp3)}`

⚠️ *Keine Finanzberatung!*
📌 Achtet auf *Money Management*!
🔀 TP1 erreicht → *Breakeven setzen*.
"""

# =============================================================================
# SYMBOL-MAPPING FÜR TWELVE DATA
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
        "GER40": "DAX",
    }
    return symbol_map.get(symbol.upper(), symbol)

# =============================================================================
# PREISABFRAGE (VIP-Monitor)
# =============================================================================
def get_price(symbol: str) -> float:
    global METALS_API_COOLDOWN_UNTIL

    symbol = symbol.upper()
    coingecko_map = {
        "BTCUSD": "bitcoin",
        "ETHUSD": "ethereum",
        "XRPUSD": "ripple",
        "DOGEUSD": "dogecoin",
    }

    try:
        # Crypto via Coingecko
        if symbol in coingecko_map:
            r = _http.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_map[symbol]}&vs_currencies=usd",
                timeout=10,
            )
            data = r.json()
            return float(data[coingecko_map[symbol]]["usd"])

        # Metals via metals-api (mit Cooldown)
        if symbol in {"XAUUSD", "SILVER", "XAGUSD"}:
            base = "XAU" if "XAU" in symbol else "XAG"

            if METALS_API_KEY and time.time() >= METALS_API_COOLDOWN_UNTIL:
                try:
                    r = _http.get(
                        f"https://metals-api.com/api/latest?access_key={METALS_API_KEY}&base={base}&symbols=USD",
                        timeout=10,
                    )
                    data = r.json()

                    if data.get("success") and "rates" in data and "USD" in data["rates"]:
                        val = float(data["rates"]["USD"])
                        if val < 1:
                            val = 1 / val
                        return val

                    err = data.get("error", {}) if isinstance(data, dict) else {}
                    if isinstance(err, dict) and int(err.get("code", 0) or 0) == 429:
                        METALS_API_COOLDOWN_UNTIL = time.time() + 3600
                        log_error("MetalsAPI Limit erreicht (429) – 1h nur Fallback (TwelveData).")

                    raise Exception(f"MetalsAPI Fehler: {data}")
                except Exception as e:
                    log_error(f"MetalsAPI Fallback für {symbol}: {e}")

        # Fallback TwelveData
        if not TWELVE_API_KEY:
            raise Exception("TWELVE_API_KEY fehlt (Fallback nicht möglich)")

        symbol_twelve = convert_symbol_for_twelve(symbol)
        r = _http.get(
            f"https://api.twelvedata.com/price?symbol={symbol_twelve}&apikey={TWELVE_API_KEY}",
            timeout=10,
        )
        data = r.json()
        if "price" in data and str(data["price"]).strip():
            return float(data["price"])
        raise Exception(f"Twelve Data Fehler: {data}")

    except Exception as e:
        log_error(f"Preisabruf Fehler für {symbol}: {e}")
        return 0.0

# =============================================================================
# MONITOR LOGIK (VIP)
# =============================================================================
def _alert_trade(symbol: str, side: str, msg: str):
    text = f"*{symbol}* | *{str(side).upper()}*\n{msg}"
    send_telegram(text, retries=1)


def _debug_trade_state(t: Dict[str, Any], price: float):
    if not MONITOR_DEBUG:
        return
    symbol = (t.get("symbol") or "").upper()
    side = t.get("side")
    print(
        "DEBUG "
        f"{symbol} {side} | price={price} entry={t.get('entry')} sl={t.get('sl')} "
        f"tp1={t.get('tp1')} tp2={t.get('tp2')} tp3={t.get('tp3')} | "
        f"tp1_hit={t.get('tp1_hit')} tp2_hit={t.get('tp2_hit')} tp3_hit={t.get('tp3_hit')} "
        f"sl_hit={t.get('sl_hit')} closed={t.get('closed')}"
    )


def check_trades():
    trades = load_trades()
    updated: List[Dict[str, Any]] = []

    # Preis pro Symbol nur 1x pro Durchlauf
    price_cache: Dict[str, float] = {}

    for t in trades:
        if t.get("closed"):
            updated.append(t)
            continue

        symbol = (t.get("symbol", "") or "").upper()
        side = (t.get("side", "") or "").lower()
        entry = parse_float(t.get("entry")) or 0.0
        sl = parse_float(t.get("sl")) or 0.0
        tp1 = parse_float(t.get("tp1")) or 0.0
        tp2 = parse_float(t.get("tp2")) or 0.0
        tp3 = parse_float(t.get("tp3")) or 0.0

        t.setdefault("tp1_hit", False)
        t.setdefault("tp2_hit", False)
        t.setdefault("tp3_hit", False)
        t.setdefault("sl_hit", False)
        t.setdefault("closed", False)

        if symbol not in price_cache:
            price_cache[symbol] = get_price(symbol)
        price = price_cache[symbol]

        t["last_price"] = price
        t["last_check_at"] = utc_now_iso()
        t["updated_at"] = utc_now_iso()

        log_info(f"🔍 {symbol} Preis: {price}")
        _debug_trade_state(t, price)

        if price == 0:
            updated.append(t)
            continue

        # LONG
        if side == "long":
            # TP-Kette separat, damit mehrere Ziele in einem Poll verarbeitet werden
            if (not t["tp1_hit"]) and hit_tp_long(price, tp1):
                t["tp1_hit"] = True
                _alert_trade(symbol, side, "💶 *TP1 erreicht – BE setzen oder Trade managen. Wir machen uns auf den Weg zu TP2!* 🚀")

            if (not t["tp2_hit"]) and hit_tp_long(price, tp2):
                t["tp1_hit"] = True
                t["tp2_hit"] = True
                _alert_trade(symbol, side, "💶 *TP2 erreicht – weiter geht’s! Full TP in Sicht!* ✨")

            if (not t["tp3_hit"]) and hit_tp_long(price, tp3):
                t["tp1_hit"] = True
                t["tp2_hit"] = True
                t["tp3_hit"] = True
                t["closed"] = True
                t["close_reason"] = "tp3"
                _alert_trade(symbol, side, "🏆 *Full TP erreicht – Glückwunsch an alle! 💶💶💰🥳*")

            # Nur wenn noch offen
            if not t["closed"]:
                if (not t["tp1_hit"]) and (not t["sl_hit"]) and hit_sl_long(price, sl):
                    t["sl_hit"] = True
                    t["closed"] = True
                    t["close_reason"] = "sl"
                    _alert_trade(symbol, side, "🛑 *SL erreicht – schade. Wir bewerten neu und kommen stärker zurück.*")
                elif t["tp1_hit"] and back_to_entry_long(price, entry):
                    t["closed"] = True
                    t["close_reason"] = "be_after_tp"
                    if t.get("tp2_hit"):
                        _alert_trade(symbol, side, "💰 *Trade teilweise im Gewinn geschlossen – TP1 + TP2 wurden erreicht, Rest auf Entry beendet.*")
                    else:
                        _alert_trade(symbol, side, "💰 *Trade teilweise im Gewinn geschlossen – TP1 wurde erreicht, Rest auf Entry beendet.*")

        # SHORT
        elif side == "short":
            if (not t["tp1_hit"]) and hit_tp_short(price, tp1):
                t["tp1_hit"] = True
                _alert_trade(symbol, side, "💶 *TP1 erreicht – BE setzen oder Trade managen. Wir machen uns auf den Weg zu TP2!* 🚀")

            if (not t["tp2_hit"]) and hit_tp_short(price, tp2):
                t["tp1_hit"] = True
                t["tp2_hit"] = True
                _alert_trade(symbol, side, "💶 *TP2 erreicht – weiter geht’s! Full TP in Sicht!* ✨")

            if (not t["tp3_hit"]) and hit_tp_short(price, tp3):
                t["tp1_hit"] = True
                t["tp2_hit"] = True
                t["tp3_hit"] = True
                t["closed"] = True
                t["close_reason"] = "tp3"
                _alert_trade(symbol, side, "🏆 *Full TP erreicht – Glückwunsch an alle! 💶💶💰🥳*")

            if not t["closed"]:
                if (not t["tp1_hit"]) and (not t["sl_hit"]) and hit_sl_short(price, sl):
                    t["sl_hit"] = True
                    t["closed"] = True
                    t["close_reason"] = "sl"
                    _alert_trade(symbol, side, "🛑 *SL erreicht – schade. Wir bewerten neu und kommen stärker zurück.*")
                elif t["tp1_hit"] and back_to_entry_short(price, entry):
                    t["closed"] = True
                    t["close_reason"] = "be_after_tp"
                    if t.get("tp2_hit"):
                        _alert_trade(symbol, side, "💰 *Trade teilweise im Gewinn geschlossen – TP1 + TP2 wurden erreicht, Rest auf Entry beendet.*")
                    else:
                        _alert_trade(symbol, side, "💰 *Trade teilweise im Gewinn geschlossen – TP1 wurde erreicht, Rest auf Entry beendet.*")

        else:
            log_error(f"Ungültige Trade-Side in trades.json: {side} ({symbol})")

        updated.append(t)

    save_trades(updated)


def monitor_loop():
    send_telegram("✅ *Trade-Monitor gestartet*", retries=1)
    log_info(f"🔁 VIP Monitor aktiv (Intervall {MONITOR_POLL_SEC}s)")
    while True:
        try:
            check_trades()
        except Exception as e:
            log_error(f"Hauptfehler Monitor: {e}")
        time.sleep(MONITOR_POLL_SEC)


def start_monitor_delayed():
    time.sleep(3)
    monitor_loop()

# =============================================================================
# BOT SIGNAL HUB (für cTrader-Hub, unverändert drin)
# =============================================================================
def load_bot_signals():
    with _lock_bot:
        data = _safe_read_json(BOT_SIGNALS_FILE, [])
        return data if isinstance(data, list) else []


def save_bot_signals(signals):
    with _lock_bot:
        _safe_write_json_atomic(BOT_SIGNALS_FILE, signals)


def build_signal_id(symbol: str, side: str, tf: str, t: str) -> str:
    base = f"{symbol}_{side}_{tf}_{t}"
    return base.replace(" ", "").replace(":", "").replace("-", "").replace(".", "")


def load_bot_state():
    with _lock_state:
        st = _safe_read_json(BOT_STATE_FILE, {})
        if not isinstance(st, dict):
            st = {}
        st.setdefault("enabled", True)
        st.setdefault("updated_at", utc_now_iso())
        return st


def save_bot_state(state: dict):
    with _lock_state:
        state["updated_at"] = utc_now_iso()
        _safe_write_json_atomic(BOT_STATE_FILE, state)


def load_clients():
    with _lock_clients:
        d = _safe_read_json(BOT_CLIENTS_FILE, {})
        return d if isinstance(d, dict) else {}


def save_clients(d: dict):
    with _lock_clients:
        _safe_write_json_atomic(BOT_CLIENTS_FILE, d)


def remember_client_ack(client_id: str, sig_id: str):
    if not client_id:
        return
    d = load_clients()
    d[client_id] = {"last_ack_id": sig_id, "acked_at": utc_now_iso()}
    save_clients(d)


def get_client_last_ack(client_id: str):
    if not client_id:
        return None
    d = load_clients()
    rec = d.get(client_id)
    if not isinstance(rec, dict):
        return None
    return rec.get("last_ack_id")


def save_bot_signal(symbol, side, entry, tf, slf=None, tv_time=None, raw=None):
    signals = load_bot_signals()

    tv_time = (tv_time or "").strip()
    tf = (tf or "-").strip()

    sig_id = build_signal_id(symbol, side, tf, tv_time or utc_now_iso())

    # Dedup (letzte 500 prüfen)
    for s in reversed(signals[-500:]):
        if s.get("id") == sig_id:
            return False, "duplicate", sig_id

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
        "raw": raw or {},
    }

    signals.append(sig)
    if BOT_SIGNALS_MAX > 0 and len(signals) > BOT_SIGNALS_MAX:
        signals = signals[-BOT_SIGNALS_MAX:]

    save_bot_signals(signals)
    return True, "saved", sig_id


def next_signal_for_client(client_id: str):
    signals = load_bot_signals()
    if not signals:
        return None

    last_ack = get_client_last_ack(client_id)

    if not last_ack:
        if BOT_NEW_CLIENT_BASELINE and client_id:
            newest = signals[-1]
            newest_dt = parse_iso_utc(newest.get("received_at") or newest.get("time"))
            if newest_dt:
                age = (datetime.now(timezone.utc) - newest_dt).total_seconds()
                if age <= float(BOT_BASELINE_GRACE_SEC):
                    return newest

            try:
                last_id = str(newest.get("id", "")).strip()
                if last_id:
                    remember_client_ack(client_id, last_id)
            except Exception:
                pass
            return None

        return signals[-1]

    idx = -1
    for i, s in enumerate(signals):
        if s.get("id") == last_ack:
            idx = i
            break

    if idx < 0:
        return signals[-1]

    if idx + 1 < len(signals):
        return signals[idx + 1]

    return None

# =============================================================================
# ROUTES
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


@app.route("/monitor_status", methods=["GET"])
def monitor_status():
    return jsonify(
        {
            "run_monitor": RUN_MONITOR,
            "monitor_poll_sec": MONITOR_POLL_SEC,
            "monitor_debug": MONITOR_DEBUG,
            "trigger_eps_pct": TRIGGER_EPS_PCT,
            "metals_cooldown_until": METALS_API_COOLDOWN_UNTIL,
        }
    ), 200

# ---------------------------------------------------------------------
# VIP: /webhook
# ---------------------------------------------------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True) or {}
        print("📬 VIP Webhook empfangen:", data)

        if not require_secret(data, "vip"):
            return "❌ Unauthorized", 401

        cmd = (data.get("cmd") or "").strip().upper()
        if cmd and cmd != "ENTRY":
            return "✅ Ignored (cmd)", 200

        symbol = normalize_symbol_tv(str(data.get("symbol", "")).strip())
        side = normalize_side(data.get("side") or data.get("direction"))
        entry = parse_entry(data)

        if not symbol or side not in {"long", "short"} or entry <= 0:
            return "❌ Ungültige Daten (symbol/side/entry)", 400

        sl = calc_sl(entry, side)
        tp1, tp2, tp3 = calc_tp(entry, sl, side, symbol)

        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)
        send_telegram(msg, retries=1)

        meta = {"tf": data.get("tf"), "time": data.get("time"), "raw": {"cmd": cmd}}
        save_trade(symbol, entry, sl, tp1, tp2, tp3, side, meta=meta)

        return "✅ OK", 200

    except Exception as e:
        print("❌ VIP Fehler:", str(e))
        return f"❌ Fehler: {str(e)}", 400


@app.route("/add_manual", methods=["POST"])
def add_manual():
    try:
        data = request.get_json(force=True) or {}

        symbol = normalize_symbol_tv(str(data.get("symbol", "")).strip())
        side = normalize_side(data.get("side"))
        entry = parse_float(data.get("entry")) or 0.0

        sl = parse_float(data.get("sl")) or 0.0
        tp1 = parse_float(data.get("tp1")) or 0.0
        tp2 = parse_float(data.get("tp2")) or 0.0
        tp3 = parse_float(data.get("tp3")) or 0.0

        if not all([symbol, entry, side, sl, tp1, tp2, tp3]) or side not in {"long", "short"}:
            return "❌ Ungültige Daten", 400

        msg = format_message(symbol, entry, sl, tp1, tp2, tp3, side)
        send_telegram(msg, retries=1)

        save_trade(symbol, entry, sl, tp1, tp2, tp3, side, meta={"manual": True})
        return "✅ Manuell hinzugefügt", 200

    except Exception as e:
        log_error(f"Fehler beim manuellen Import: {e}")
        return f"❌ Fehler: {e}", 500

# ---------------------------------------------------------------------
# BOT: Status / Toggle
# ---------------------------------------------------------------------
@app.route("/bot_status", methods=["GET"])
def bot_status():
    return jsonify(load_bot_state()), 200


@app.route("/bot_toggle", methods=["POST"])
def bot_toggle():
    data = request.get_json(force=True) or {}
    if not require_secret(data, "bot"):
        return "❌ Unauthorized", 401

    st = load_bot_state()
    if "enabled" in data:
        st["enabled"] = bool(data.get("enabled"))
    save_bot_state(st)
    return jsonify(st), 200

# ---------------------------------------------------------------------
# BOT: Signale lesen
# ---------------------------------------------------------------------
@app.route("/bot_signals", methods=["GET"])
def bot_signals_get():
    try:
        signals = load_bot_signals()
        try:
            limit = int(request.args.get("limit", "200"))
        except Exception:
            limit = 200
        limit = max(1, min(5000, limit))
        return json.dumps(signals[-limit:], indent=2), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return f"Fehler: {e}", 500

# ---------------------------------------------------------------------
# BOT: next/ack
# ---------------------------------------------------------------------
@app.route("/bot_next", methods=["GET"])
def bot_next():
    client_id = str(request.args.get("client", "")).strip()
    sig = next_signal_for_client(client_id)

    payload = {"ok": True, "signal": sig}

    if sig:
        s = dict(sig)

        side_lc = (s.get("side") or "").lower()
        if side_lc == "long":
            side_u = "LONG"
        elif side_lc == "short":
            side_u = "SHORT"
        else:
            side_u = (s.get("side") or "").upper()

        s["side"] = side_u
        s["direction"] = side_u
        s["action"] = "BUY" if side_u == "LONG" else "SELL" if side_u == "SHORT" else ""
        s["sl"] = s.get("slf")
        s["timeframe"] = s.get("tf")

        payload.update(s)
        payload["signal"] = s

        if BOT_AUTO_ACK_ON_GET and client_id:
            try:
                sid = str(s.get("id", "")).strip()
                if sid:
                    remember_client_ack(client_id, sid)
            except Exception:
                pass

    return jsonify(payload), 200


@app.route("/bot_ack", methods=["POST"])
def bot_ack():
    data = request.get_json(force=True) or {}
    if not require_secret(data, "bot"):
        return "❌ Unauthorized", 401

    client_id = str(data.get("client", "")).strip()
    sig_id = str(data.get("id", "")).strip()

    if not client_id or not sig_id:
        return "❌ client/id fehlt", 400

    remember_client_ack(client_id, sig_id)
    return jsonify({"ok": True, "client": client_id, "acked": sig_id}), 200

# ---------------------------------------------------------------------
# BOT: /bot_webhook
# ---------------------------------------------------------------------
@app.route("/bot_webhook", methods=["POST"])
def bot_webhook():
    try:
        data = request.get_json(force=True) or {}
        print("🤖 BOT Webhook empfangen:", data)

        if not require_secret(data, "bot"):
            return "❌ Unauthorized", 401

        st = load_bot_state()
        if not st.get("enabled", True):
            return "✅ Bot disabled (ignored)", 200

        cmd = (data.get("cmd") or "").strip().upper()
        if cmd and cmd != "ENTRY":
            return "✅ Ignored (cmd)", 200

        symbol = normalize_symbol_tv(str(data.get("symbol", "")).strip())
        side = normalize_side(data.get("side") or data.get("direction"))
        entry = parse_entry(data)
        tf = str(data.get("tf") or data.get("timeframe") or "").strip()
        tv_time = str(data.get("time") or "").strip()
        slf = parse_float(data.get("slf"))

        if not symbol or side not in {"long", "short"} or entry <= 0:
            return "❌ Ungültige Daten (symbol/side/entry)", 400

        ok, why, sig_id = save_bot_signal(
            symbol=symbol,
            side=side,
            entry=entry,
            tf=tf,
            slf=slf,
            tv_time=tv_time,
            raw=data,
        )

        if why == "duplicate":
            return "✅ Duplicate ignored", 200

        return jsonify({"ok": True, "saved": ok, "id": sig_id}), 200

    except Exception as e:
        print("❌ BOT Fehler:", str(e))
        return f"❌ Fehler: {str(e)}", 400

# =============================================================================
# STARTUP
# =============================================================================
if RUN_MONITOR:
    threading.Thread(target=start_monitor_delayed, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
