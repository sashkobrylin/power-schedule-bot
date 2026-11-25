"""Зчитує графіки з poweron.toe.com.ua через headless-браузер (так само, як людина шукає за адресою)."""
import re
from datetime import datetime

from playwright.sync_api import sync_playwright, Page

from config import SITE_URL, QUEUES

# У кожної години на сайті є атрибут title на кшталт "21:00 - 10/1":
# перша/друга половина години: 0 — світло є, 10 — перемикання, 1 — вимкнення.
HOUR_RE = re.compile(r"^(\d{2}):00\s*-\s*(\d+)/(\d+)$")


def _pick(page: Page, container_id: str, text: str):
    box = page.locator(f"#{container_id}")
    box.locator("input").click()
    box.locator("input").fill(text)
    option = page.get_by_role("option", name=text, exact=True)
    try:
        option.first.wait_for(timeout=15000)
    except Exception:
        # на сайті назва населеного пункту має суфікс, наприклад "Копичинці (Копичинецька ОТГ)"
        option = page.locator('[role="option"]', has_text=text)
        option.first.wait_for(timeout=15000)
    option.first.click()


def _read_cards(page: Page):
    """Повертає {дата 'YYYY-MM-DD': {'queue': '3.1', 'asof': '...', 'halves': [48 станів]}}."""
    result = {}
    for card in page.locator(".queue-card").all():
        date_str = card.locator(".queue-card__title:not(.sub) .queue-card__date").inner_text().strip()
        queue = card.locator(".queue-card__title:not(.sub) .queue-card__cherg").inner_text().strip()
        asof = card.locator(".queue-card__title.sub .queue-card__cherg").inner_text().strip()
        halves = [None] * 48
        for title in card.locator(".queue-hour.color").evaluate_all("els => els.map(e => e.getAttribute('title'))"):
            m = HOUR_RE.match((title or "").strip())
            if not m:
                continue
            h = int(m.group(1))
            halves[2 * h], halves[2 * h + 1] = m.group(2), m.group(3)
        if None in halves:
            raise RuntimeError(f"Неповний графік у картці {date_str} {queue}")
        date = datetime.strptime(date_str, "%d.%m.%Y").date().isoformat()
        result[date] = {"queue": queue.replace("Черга", "").strip(), "asof": asof, "halves": halves}
    return result


def fetch_all():
    """Повертає ({дата: {черга: [48 станів]}}, {дата: datetime «станом на»}) для всіх дат на сайті
    (сьогодні і, можливо, завтра). «Станом на» — найпізніше з оновлень обох черг."""
    by_date, asof = {}, {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="uk-UA", viewport={"width": 1280, "height": 1600})
        for q in QUEUES:
            page.goto(SITE_URL, wait_until="networkidle")
            _pick(page, "city", q["city"])
            _pick(page, "street", q["street"])
            _pick(page, "building", q["building"])
            page.get_by_text("Знайти", exact=True).click()
            page.locator(".queue-card").first.wait_for(timeout=30000)
            page.wait_for_timeout(1500)  # друга картка (на завтра) може з'явитися трохи пізніше
            cards = _read_cards(page)
            for date, card in cards.items():
                if card["queue"] != q["queue"]:
                    raise RuntimeError(
                        f"Адреса {q['city']}, {q['street']} {q['building']} тепер у черзі {card['queue']}, "
                        f"а не {q['queue']}. Оновіть config.py.")
                by_date.setdefault(date, {})[q["queue"]] = card["halves"]
                try:
                    stamp = datetime.strptime(card["asof"], "%d.%m.%Y %H:%M:%S")
                    asof[date] = max(asof.get(date, stamp), stamp)
                except ValueError:
                    pass  # формат змінився — просто покажемо час перевірки
        browser.close()
    return by_date, asof


def off_intervals(halves):
    """48 станів -> список рядків 'з 21:30 по 00:00' (лише повне вимкнення, без перемикання)."""
    out, start = [], None
    for i, v in enumerate(halves + ["0"]):
        if v == "1" and start is None:
            start = i
        elif v != "1" and start is not None:
            out.append((start, i))
            start = None
    fmt = lambda i: f"{(i // 2) % 24:02d}:{30 * (i % 2):02d}"
    return [f"з {fmt(a)} по {fmt(b)}" for a, b in out]


if __name__ == "__main__":
    import json
    data, _ = fetch_all()
    print(json.dumps({d: {q: off_intervals(h) for q, h in qs.items()} for d, qs in data.items()},
                     ensure_ascii=False, indent=2))
