"""Telegram transport: Bot API calls, sending, long polling. Standard library only.
The token lives only in the environment. Two uvicorn workers share a container, so a file lock lets exactly one run the bot."""
import json
import os
import threading
import time
import urllib.error
import urllib.request

from .db import DATA_DIR, connect, now

API = os.environ.get("TELEGRAM_API", "https://api.telegram.org")
_lock_file = None
_handler = None


def token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def configured() -> bool:
    return bool(token())


class TgError(Exception):
    def __init__(self, code: int, description: str, retry_after: int = 0):
        super().__init__(description)
        self.code, self.description, self.retry_after = code, description, retry_after


def api(method: str, payload: dict | None = None, timeout: int = 15):
    req = urllib.request.Request(f"{API}/bot{token()}/{method}", json.dumps(payload or {}).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
        except ValueError:
            body = {}
        raise TgError(e.code, body.get("description", f"HTTP {e.code}"), (body.get("parameters") or {}).get("retry_after", 0)) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise TgError(0, "нет связи с Telegram: " + str(getattr(e, "reason", e)).replace(token(), "***")) from None
    if not data.get("ok"):
        raise TgError(data.get("error_code", 0), data.get("description", "ошибка Telegram"))
    return data["result"]


def send(chat_id, text: str, markup: dict | None = None) -> tuple[bool, str]:
    """(ok, error). A person who blocked the bot is marked inactive for reminders instead of failing every morning."""
    for attempt in (1, 2):
        try:
            payload = {"chat_id": str(chat_id), "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True}
            if markup:
                payload["reply_markup"] = markup
            api("sendMessage", payload)
            return True, ""
        except TgError as e:
            if e.code == 429 and attempt == 1:
                time.sleep(min(e.retry_after or 2, 20))
                continue
            return False, e.description
    return False, "не удалось отправить"


def edit(chat_id, message_id, text: str, markup: dict | None = None) -> None:
    try:
        api("editMessageText", {"chat_id": str(chat_id), "message_id": message_id, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True,
                                "reply_markup": markup or {"inline_keyboard": []}})
    except TgError as e:
        if "not modified" not in e.description:
            raise


def answer(callback_id: str, text: str = "") -> None:
    try:
        api("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:190]})
    except TgError:
        pass


def _setting(key: str, default: str = "") -> str:
    c = connect()
    try:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default
    finally:
        c.close()


def _put(key: str, value: str) -> None:
    c = connect()
    try:
        c.execute("INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        c.commit()
    finally:
        c.close()


def bot_username() -> str:
    u = _setting("tg_bot")
    if u or not configured():
        return u
    try:
        u = api("getMe").get("username", "")
        _put("tg_bot", u)
    except TgError:
        return ""
    return u


def poll_once(timeout: int = 0) -> int:
    offset = int(_setting("tg_offset", "0") or 0)
    updates = api("getUpdates", {"offset": offset, "timeout": timeout, "allowed_updates": ["message", "callback_query"]}, timeout=timeout + 10)
    for u in updates:
        try:
            if _handler:
                _handler(u)
        except Exception:   # one bad message must not stop the bot
            pass
        offset = u["update_id"] + 1
        _put("tg_offset", str(offset))
    return len(updates)


def _poll_loop() -> None:
    bot_username()
    while True:
        try:
            poll_once(25)
            _put("tg_error", "")
            _put("tg_seen", now())
        except TgError as e:
            _put("tg_error", "токен используется другим приложением: нужен отдельный бот" if e.code == 409 else e.description)
            time.sleep(30 if e.code == 409 else 10)
        except Exception:
            time.sleep(10)


def _schedule_loop() -> None:
    from . import notify
    while True:
        try:
            notify.run_due()
        except Exception:
            pass
        time.sleep(30)


def start(handler) -> None:
    global _lock_file, _handler
    _handler = handler
    if not configured() or os.environ.get("FLU_NO_TELEGRAM") == "1":
        return
    try:
        import fcntl
        os.makedirs(DATA_DIR, exist_ok=True)
        _lock_file = open(os.path.join(DATA_DIR, "telegram.lock"), "w")
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ImportError):
        _lock_file = None
        return
    threading.Thread(target=_poll_loop, daemon=True, name="tg-poll").start()
    threading.Thread(target=_schedule_loop, daemon=True, name="tg-schedule").start()
