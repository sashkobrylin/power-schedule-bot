"""Перевіряє графіки й надсилає картинку в Telegram, коли з'являється новий графік або змінюється наявний.

Запуск:
  python bot.py            — звичайна перевірка (так запускає GitHub Actions)
  python bot.py --dry-run  — нічого не надсилає й не зберігає, лише кладе картинки в out/
  python bot.py --init     — запам'ятовує поточні графіки без надсилання (для першого запуску)
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from config import QUEUES, TIMEZONE, TITLE_NEW, TITLE_UPDATED, NO_OUTAGES_TEXT
from render import build_svg, svg_to_png
from scrape import fetch_all, off_intervals

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"
OUT_DIR = ROOT / "out"


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def send_photo(png_path, caption=None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    with open(png_path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                          data={"chat_id": chat_id, **({"caption": caption} if caption else {})},
                          files={"photo": f}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Telegram: {r.status_code} {r.text}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    state = load_state()
    queue_ids = [q["queue"] for q in QUEUES]

    scraped = fetch_all()
    print("На сайті:", {d: {q: off_intervals(h) for q, h in qs.items()} for d, qs in sorted(scraped.items())})

    for day in sorted(scraped):
        if date.fromisoformat(day) < today:
            continue  # вчорашній графік (якщо раптом ще висить) не публікуємо
        queues = scraped[day]
        missing = [q for q in queue_ids if q not in queues]
        if missing:
            print(f"{day}: ще немає графіка для черг {missing}, чекаємо")
            continue

        current = {q: off_intervals(queues[q]) for q in queue_ids}
        previous = state.get(day)
        if previous == current:
            print(f"{day}: без змін")
            continue

        title = TITLE_NEW if previous is None else TITLE_UPDATED
        print(f"{day}: {title} -> {current}")

        if mode == "--init":
            state[day] = current
            continue

        svg = build_svg(title, date.fromisoformat(day), current[queue_ids[0]], current[queue_ids[1]], NO_OUTAGES_TEXT)
        OUT_DIR.mkdir(exist_ok=True)
        png = OUT_DIR / f"{day}{'-updated' if previous else ''}.png"
        svg_to_png(svg, png)
        print(f"   картинка: {png}")

        if mode == "--dry-run":
            continue
        send_photo(png)
        state[day] = current  # зберігаємо лише після успішного надсилання
        save_state(state)

    # прибираємо старі дати, щоб state.json не ріс
    cutoff = (today - timedelta(days=2)).isoformat()
    state = {d: v for d, v in state.items() if d >= cutoff}
    if mode != "--dry-run":
        save_state(state)


if __name__ == "__main__":
    main()
