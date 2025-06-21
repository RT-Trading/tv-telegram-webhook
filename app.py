WEBHOOK_TOKEN = os.environ.get('WEBHOOK_TOKEN')

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    # 🔒 Sicherheitsprüfung
    if data.get('token') != WEBHOOK_TOKEN:
        return 'Unauthorized', 403

    entry = float(data['entry'])
    sl = float(data['sl'])
    side = data['side']
    symbol = data['symbol']

    tp1, tp2, tp3 = calc_tp(entry, sl, side)

    msg = f"""📈 *Signal*: {symbol}
*Richtung*: {side.upper()}
*Entry*: {entry}
*SL*: {sl}
*TP1 (1:1)*: {tp1}
*TP2 (1:3)*: {tp2}
*Full TP (1:5)*: {tp3}
"""
    send_to_telegram(msg)
    return 'OK', 200
