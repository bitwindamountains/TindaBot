"""Small handover marker stored alongside the existing conversation state."""

from sqlalchemy import select

from tindabot.db import Conversation, Inbox


def set_pause(conversation, paused, reason="operator", now=0):
    context = dict(conversation.context)
    if paused:
        previous = context.get("handover", {}) if conversation.paused else {}
        # A seller reply or another pause is not customer consent to resume.
        context["handover"] = {
            "reason": "stop" if previous.get("reason") == "stop" else reason,
            "since": previous.get("since", now),
        }
    else:
        context.pop("handover", None)
    conversation.context = context
    conversation.paused = paused
    conversation.version += 1


def has_unread(session, conversation_key):
    """Customer activity the operator has not seen yet blocks a resume."""
    return session.scalar(
        select(Inbox.id)
        .where(
            Inbox.conversation_key == conversation_key,
            Inbox.status.in_(["pending", "failed"]),
        )
        .limit(1)
    )


def waiting():
    return (
        Conversation.paused.is_(True),
        Conversation.context["handover"]["reason"]
        .as_string()
        .in_(["customer", "stop", "page_reply", "operator"]),
    )
