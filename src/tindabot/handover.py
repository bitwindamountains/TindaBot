"""Small handover marker stored alongside the existing conversation state."""

from tindabot.db import Conversation


def set_pause(conversation, paused, reason="operator", now=0):
    context = dict(conversation.context)
    if paused:
        context["handover"] = {"reason": reason, "since": now}
    else:
        context.pop("handover", None)
    conversation.context = context
    conversation.paused = paused
    conversation.version += 1


def waiting():
    return (
        Conversation.paused.is_(True),
        Conversation.context["handover"]["reason"]
        .as_string()
        .in_(["customer", "stop", "page_reply", "operator"]),
    )
