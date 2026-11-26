"""Telegram transport: Bot API calls, sending, long polling. Standard library only.
The token lives only in the environment. Two uvicorn workers share a container, so a file lock lets exactly one run the bot."""
import contextvars
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


def profile_photo(tg_id) -> bytes | None:
    """The person's current profile photo (a small size) or None: no photo, hidden by privacy settings, or no connection. The token stays here."""
    try:
        r = api("getUserProfilePhotos", {"user_id": int(tg_id), "limit": 1})
        if not r.get("total_count") or not r.get("photos"):
            return None
        sizes = r["photos"][0]
        pick = next((x for x in sizes if x.get("width", 0) >= 160), sizes[-1])          # about 160 px: sharp enough for a 40 px avatar, a few kilobytes
        f = api("getFile", {"file_id": pick["file_id"]})
        with urllib.request.urlopen(f"{API}/file/bot{token()}/{f['file_path']}", timeout=15) as resp:
            data = resp.read(1_000_001)
        return data if 0 < len(data) <= 1_000_000 else None
    except (TgError, KeyError, ValueError, OSError):
        return None


# While a button under a message is being handled, the answer goes into that very message (it is edited), so that the chat does not fill up with a new message at every press:
# set_edit_target() is called by the handler of the buttons, the first send() of the answer edits the message, later ones are new messages. A reply keyboard cannot be put by an
# edit: then the buttons of the old message are removed (nobody can press them twice) and the answer is a new message.
_EDIT: contextvars.ContextVar = contextvars.ContextVar("tg_edit", default=None)


def set_edit_target(chat_id, message_id):
    return _EDIT.set({"chat": str(chat_id), "id": message_id, "used": False} if chat_id and message_id else None)


def reset_edit_target(token) -> None:
    _EDIT.reset(token)


def _edit_in_place(chat_id, text: str, markup: dict | None) -> bool:
    """True when the answer was put into the message of the pressed button."""
    tgt = _EDIT.get()
    if not tgt or tgt["used"] or str(chat_id) != tgt["chat"]:
        return False
    tgt["used"] = True
    inline = not markup or "inline_keyboard" in markup
    try:
        if inline:
            api("editMessageText", {"chat_id": tgt["chat"], "message_id": tgt["id"], "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True,
                                    "reply_markup": markup or {"inline_keyboard": []}})
            return True
        api("editMessageReplyMarkup", {"chat_id": tgt["chat"], "message_id": tgt["id"], "reply_markup": {"inline_keyboard": []}})
    except TgError as e:
        if inline and "not modified" in e.description:
            return True                                    # the same text and buttons: nothing to change, nothing to add
    return False


def send(chat_id, text: str, markup: dict | None = None) -> tuple[bool, str]:
    """(ok, error). A person who blocked the bot is marked inactive for reminders instead of failing every morning."""
    if _edit_in_place(chat_id, text, markup):
        return True, ""
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


def send_document(chat_id, data: bytes, filename: str, caption: str = "") -> tuple[bool, str]:
    """Sends a file (multipart upload). (ok, error)."""
    import uuid
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", str(chat_id)), ("caption", caption[:1000]), ("parse_mode", "HTML")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    safe = filename.replace('"', "")
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{safe}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"{API}/bot{token()}/sendDocument", b"".join(parts), {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.load(r)
        return (True, "") if body.get("ok") else (False, body.get("description", "ошибка Telegram"))
    except urllib.error.HTTPError as e:
        try:
            return False, json.load(e).get("description", f"HTTP {e.code}")
        except ValueError:
            return False, f"HTTP {e.code}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, "нет связи с Telegram: " + str(getattr(e, "reason", e)).replace(token(), "***")


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
