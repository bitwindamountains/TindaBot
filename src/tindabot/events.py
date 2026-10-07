import hashlib
import hmac
import json
import time

from tindabot.db import Conversation, Inbox, insert_once


def valid_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(secret) and hmac.compare_digest(expected.encode(), signature.encode())


def parse_events(document: dict, page_id: str, now: float) -> list[dict]:
    if not isinstance(document, dict) or document.get("object") != "page":
        raise ValueError("invalid_object")
    parsed = []
    for entry in document.get("entry", []):
        if str(entry.get("id")) != page_id:
            raise ValueError("wrong_page")
        for event in entry.get("messaging", []):
            if not isinstance(event, dict):
                raise ValueError("invalid_event")
            message = event.get("message", {})
            postback = event.get("postback", {})
            if not message and not postback:
                continue
            echo = bool(message.get("is_echo"))
            psid = str(event.get("recipient" if echo else "sender", {}).get("id", ""))
            recipient = str(event.get("sender" if echo else "recipient", {}).get("id", ""))
            if recipient != page_id or not psid.isdigit() or len(psid) > 80:
                raise ValueError("invalid_identity")
            occurred = event.get("timestamp")
            if (
                not isinstance(occurred, (int, float))
                or occurred <= 0
                or occurred / 1000 > now + 60
            ):
                raise ValueError("invalid_timestamp")
            mid = message.get("mid") or postback.get("mid")
            if not mid and message:
                raise ValueError("missing_message_id")
            # Postbacks without mid: retain sender, timestamp, payload, recipient in a canonical hash.
            identity = (
                str(mid)
                if mid
                else hashlib.sha256(
                    json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
            )
            value = (
                message.get("quick_reply", {}).get("payload")
                or postback.get("payload")
                or message.get("text", "")
            )
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError("invalid_text")
            payload = {
                "value": value,
                "echo": echo,
                "app_id": str(message.get("app_id", "")),
                "mid": str(mid or ""),
                "postback": bool(postback),
            }
            parsed.append(
                {
                    "event_key": hashlib.sha256(
                        f"{page_id}:{'echo' if echo else 'input'}:{identity}".encode()
                    ).hexdigest(),
                    "conversation_key": f"{page_id}:{psid}",
                    "psid": psid,
                    "payload": payload,
                    "occurred_at": occurred / 1000,
                }
            )
    return parsed


def accept_events(db, settings, document):
    now = time.time()
    events = parse_events(document, settings.meta_page_id, now)
    with db.sessions.begin() as session:
        # Stable lock order avoids deadlocks when two batched deliveries overlap.
        for key, psid in sorted({e["conversation_key"]: e["psid"] for e in events}.items()):
            insert_once(session, Conversation, {"key": key, "psid": psid}, "key")
        for event in events:
            values = {key: value for key, value in event.items() if key != "psid"}
            insert_once(session, Inbox, values, "event_key")
    return len(events)
