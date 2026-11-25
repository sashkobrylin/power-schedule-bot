"""Перевіряє графіки й надсилає картинку в Telegram (у всі чати з TELEGRAM_CHAT_ID через кому),
коли з'являється новий графік або змінюється наявний. Якщо задано VIBER_AUTH_TOKEN — ще й готує
JPEG для Viber-каналу (публікує його viber.py після того, як workflow запушить картинку в репозиторій).

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
from render import MONTHS, build_svg, diff_lines, svg_to_png
from scrape import fetch_all, off_intervals

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"
OUT_DIR = ROOT / "out"
PUBLISHED_DIR = ROOT / "published"          # JPEG для Viber (Viber бере картинку лише за посиланням)
VIBER_QUEUE = OUT_DIR / "viber_queue.json"  # що має опублікувати viber.py


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def telegram_chats():
    return [c.strip() for c in os.environ["TELEGRAM_CHAT_ID"].split(",") if c.strip()]


def send_photo(png_path, chat_id):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    with open(png_path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto",
                          data={"chat_id": chat_id}, files={"photo": f}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Telegram {chat_id}: {r.status_code} {r.text}")


def send_everywhere(png_path):
    """Надсилає в усі чати. Повертає список помилок (порожній — усе гаразд)."""
    errors = []
    for chat_id in telegram_chats():
        try:
            send_photo(png_path, chat_id)
            print(f"   надіслано в Telegram {chat_id}")
        except Exception as e:  # один зламаний чат не повинен блокувати інші
            errors.append(str(e))
            print(f"   ПОМИЛКА: {e}")
    return errors


def drop_finished(intervals, day, now):
    """Для сьогоднішнього графіка прибирає проміжки, які вже закінчилися ('по 00:00' — це кінець доби)."""
    if day != now.date():
        return list(intervals)
    def end_minutes(t):
        hh, mm = map(int, t.rsplit(" ", 1)[1].split(":"))
        return 24 * 60 if (hh, mm) == (0, 0) else hh * 60 + mm
    now_min = now.hour * 60 + now.minute
    return [t for t in intervals if end_minutes(t) > now_min]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    now = datetime.now(ZoneInfo(TIMEZONE))
    today = now.date()
    state = load_state()
    queue_ids = [q["queue"] for q in QUEUES]

    use_viber = bool(os.environ.get("VIBER_AUTH_TOKEN")) and mode != "--init"
    viber_queue = []
    failures = []

    scraped, asof = fetch_all()
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

        # на картинці лише проміжки, які ще не закінчилися
        d = date.fromisoformat(day)
        shown = {q: drop_finished(current[q], d, now) for q in queue_ids}
        if previous is not None:
            was_shown = {q: drop_finished(previous.get(q, []), d, now) for q in queue_ids}
            if was_shown == shown:
                print("   змінилися лише години, що вже минули — не публікуємо")
                if mode != "--dry-run":
                    state[day] = current
                    save_state(state)
                continue

        # в оновленому графіку виділяємо нові й змінені проміжки
        lines = [diff_lines(shown[q], None if previous is None else previous.get(q, [])) for q in queue_ids]
        updated_at = asof.get(day) or datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)
        svg = build_svg(title, date.fromisoformat(day), lines[0], lines[1], NO_OUTAGES_TEXT, updated_at=updated_at)
        OUT_DIR.mkdir(exist_ok=True)
        png = OUT_DIR / f"{day}{'-updated' if previous else ''}.png"
        jpeg = None
        if use_viber or mode == "--dry-run":
            folder = OUT_DIR if mode == "--dry-run" else PUBLISHED_DIR
            folder.mkdir(exist_ok=True)
            # унікальна назва, щоб Viber не взяв закешовану стару картинку
            jpeg = folder / f"{day}-{datetime.now(ZoneInfo(TIMEZONE)):%H%M%S}.jpeg"
        svg_to_png(svg, png, jpeg_path=jpeg)
        print(f"   картинка: {png}")

        if mode == "--dry-run":
            continue
        errors = send_everywhere(png)
        if len(errors) == len(telegram_chats()):
            # не вдалося нікуди — не запам'ятовуємо, наступний запуск спробує знову
            if jpeg:
                jpeg.unlink(missing_ok=True)
            raise RuntimeError("Не вдалося надіслати в жоден Telegram-чат")
        failures += errors
        if jpeg:
            d = date.fromisoformat(day)
            viber_queue.append({"file": jpeg.relative_to(ROOT).as_posix(),
                                "text": f"{title} відключень на {d.day} {MONTHS[d.month - 1]}"})
            VIBER_QUEUE.write_text(json.dumps(viber_queue, ensure_ascii=False), encoding="utf-8")
        state[day] = current  # зберігаємо після надсилання хоча б в один чат (щоб не дублювати)
        save_state(state)

    # прибираємо старі дати, щоб state.json не ріс
    cutoff = (today - timedelta(days=2)).isoformat()
    state = {d: v for d, v in state.items() if d >= cutoff}
    if mode != "--dry-run":
        save_state(state)
    # старі JPEG прибираємо з репозиторію (посилання на вже опубліковані лишаються робочими, бо ведуть на коміт)
    if PUBLISHED_DIR.exists() and mode != "--dry-run":
        for f in PUBLISHED_DIR.glob("*.jpeg"):
            if f.name[:10] < cutoff:
                f.unlink()
    if failures:
        sys.exit("Частину повідомлень не надіслано:\n" + "\n".join(failures))


if __name__ == "__main__":
    main()
