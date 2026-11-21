"""Показує ID груп, де бот бачив повідомлення.

1. Додайте бота в групу і напишіть у групі будь-яке повідомлення (наприклад /start@ім'я_бота).
2. Запустіть:  TELEGRAM_BOT_TOKEN=... python get_chat_id.py
"""
import os
import requests

token = os.environ["TELEGRAM_BOT_TOKEN"]
updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30).json()
seen = {}
for u in updates.get("result", []):
    msg = u.get("message") or u.get("my_chat_member") or u.get("channel_post") or {}
    chat = msg.get("chat")
    if chat:
        seen[chat["id"]] = chat.get("title") or chat.get("username") or chat.get("first_name")
if not seen:
    print("Нічого не знайдено. Напишіть повідомлення в групі (де є бот) і запустіть ще раз.")
for cid, name in seen.items():
    print(f"{cid}\t{name}")
