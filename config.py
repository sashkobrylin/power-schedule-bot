"""Що відстежуємо. Адреси потрібні лише для того, щоб сайт обленерго показав графік потрібної черги."""

SITE_URL = "https://poweron.toe.com.ua/"

# Порядок важливий: перша черга йде в шар hours1 шаблону, друга — в hours2.
QUEUES = [
    {"queue": "3.1", "city": "Копичинці", "street": "Тараса Шевченка", "building": "2"},
    {"queue": "6.1", "city": "Гадинківці", "street": "Івана Франка", "building": "2"},
]

TIMEZONE = "Europe/Kyiv"

TITLE_NEW = "Графік"
TITLE_UPDATED = "Оновлений графік"
NO_OUTAGES_TEXT = "відключень немає"
