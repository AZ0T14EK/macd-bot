import json
import os
import time
import urllib.parse
import urllib.request

TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

FAST, SLOW, SIG = 12, 26, 9
TF_MS = 15 * 60 * 1000
STATE_FILE = "state.json"

ZERO_CROSS = True      # MACD пересекает 0
SIGNAL_CROSS = True    # MACD пересекает сигнальную линию


def http_json(url, data=None):
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def bybit(host):
    url = (
        f"https://{host}/v5/market/kline"
        "?category=spot&symbol=ETHUSDT&interval=15&limit=500"
    )
    rows = http_json(url)["result"]["list"]
    return [(int(r[0]), float(r[4])) for r in rows]


def okx():
    url = "https://www.okx.com/api/v5/market/candles?instId=ETH-USDT&bar=15m&limit=300"
    rows = http_json(url)["data"]
    return [(int(r[0]), float(r[4])) for r in rows]


SOURCES = [
    ("Bybit", lambda: bybit("api.bybit.com")),
    ("Bybit (bytick)", lambda: bybit("api.bytick.com")),
    ("OKX", okx),
]


def get_candles():
    for name, fn in SOURCES:
        try:
            rows = fn()
            if len(rows) > 100:
                return name, sorted(rows)
        except Exception as e:
            print(f"{name} failed: {e}")
    raise SystemExit("Ни один источник данных не ответил")


def ema(vals, n):
    k = 2 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def send(text):
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    http_json(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data)


def main():
    source, rows = get_candles()
    now_ms = int(time.time() * 1000)
    closed = [(t, c) for t, c in rows if t + TF_MS <= now_ms]  # только закрытые

    closes = [c for _, c in closed]
    macd = [f - s for f, s in zip(ema(closes, FAST), ema(closes, SLOW))]
    signal = ema(macd, SIG)
    hist = [m - s for m, s in zip(macd, signal)]

    newest = closed[-1][0]
    if os.path.exists(STATE_FILE):
        last = json.load(open(STATE_FILE))["last_time"]
    else:
        last = None

    if last is None:
        send(f"✅ Бот запущен: ETH/USDT, 15m, MACD (источник: {source}).")
    else:
        for i in range(1, len(closed)):
            if closed[i][0] <= last:
                continue
            msgs = []
            if ZERO_CROSS:
                if macd[i - 1] < 0 <= macd[i]:
                    msgs.append("🟢 MACD пересёк ноль снизу вверх (стал положительным)")
                elif macd[i - 1] > 0 >= macd[i]:
                    msgs.append("🔴 MACD пересёк ноль сверху вниз (стал отрицательным)")
            if SIGNAL_CROSS:
                if hist[i - 1] < 0 <= hist[i]:
                    msgs.append("🟢 MACD пересёк сигнальную линию снизу вверх")
                elif hist[i - 1] > 0 >= hist[i]:
                    msgs.append("🔴 MACD пересёк сигнальную линию сверху вниз")
            for m in msgs:
                send(
                    f"{m}\n\nETH/USDT · 15m\n"
                    f"Цена закрытия: {closed[i][1]:.2f}\n"
                    f"MACD: {macd[i]:.3f} | Signal: {signal[i]:.3f}\n"
                    f"Источник: {source}"
                )

    json.dump({"last_time": newest}, open(STATE_FILE, "w"))


main()
