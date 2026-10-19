"""Pure transition function. Services implement the returned actions transactionally."""

import copy
import re
from dataclasses import dataclass, field

from tindabot.messages import COPY, MENU, catalog_messages, money, summary, text


@dataclass
class Transition:
    state: str
    context: dict
    replies: list[dict] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


# Plain-language intents, checked only outside checkout so a name or address is never misread.
INTENTS = (
    ("SELLER", re.compile(r"\b(seller|admin|human|person|agent|tao|kausap|makausap)\b")),
    ("TRACK", re.compile(r"\b(track\w*|status|nasaan|asan|san na|na ?ship\w*|shipped)\b")),
)
BUY = re.compile(r"\b(order\w*|pa ?order|bili|pabili|bibili|mine|kuha|kukuha|checkout)\b")
GREETING = re.compile(r"^(hi|hello|hey|good (morning|afternoon|evening|day)|magandang \w+)\b")
THANKS = re.compile(r"\b(thank\w*|salamat|ty|tysm)\b")
NUMBER_WORDS = {
    **dict.fromkeys(("isa", "one"), 1),
    **dict.fromkeys(("dalawa", "two"), 2),
    **dict.fromkeys(("tatlo", "three"), 3),
    **dict.fromkeys(("apat", "four"), 4),
    **dict.fromkeys(("lima", "five"), 5),
    **dict.fromkeys(("anim", "six"), 6),
    **dict.fromkeys(("pito", "seven"), 7),
    **dict.fromkeys(("walo", "eight"), 8),
    **dict.fromkeys(("siyam", "nine"), 9),
    **dict.fromkeys(("sampu", "ten"), 10),
}
CHECKOUT_STEPS = {"QTY", "DELIVERY", "NAME", "PHONE", "ADDRESS", "PAYMENT"}


def normalize(value):
    return " ".join(re.sub(r"[^\w\s]", " ", value.casefold()).split())


def quantity(value):
    """First 1–2 digit number ("2 pcs", "2pcs po") or a number word ("dalawa")."""
    match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", value)
    if match:
        return int(match.group(1))
    return next((NUMBER_WORDS[w] for w in normalize(value).split() if w in NUMBER_WORDS), 0)


def faq_answer(normalized, faqs):
    """The keyword ending latest wins ("magkano shipping" is about shipping); longer breaks ties."""
    best, score = None, (-1, -1)
    for faq in faqs:
        for keyword in (k.strip().casefold() for k in faq["keywords"].split(",")):
            match = keyword and re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", normalized)
            if match and (match.end(), len(keyword)) > score:
                best, score = faq["answer"], (match.end(), len(keyword))
    return best


def find_product(normalized, products):
    """A product whose name words appear in the message, ignoring a plural "s"."""
    stem = lambda word: word[:-1] if word.endswith("s") else word  # noqa: E731
    words = {stem(w) for w in normalized.split()}
    hits = []
    for product in products.values():
        name = [stem(w) for w in normalize(product["name"]).split() if len(w) >= 3]
        found = sum(w in words for w in name)
        if name and found >= min(2, len(name)):
            hits.append((found, product["sku"]))
    hits.sort(reverse=True)
    return hits[0][1] if hits and (len(hits) == 1 or hits[0][0] > hits[1][0]) else None


def transition(state: str, context: dict, value: str, view: dict) -> Transition:
    ctx = copy.deepcopy(context)
    raw = value.strip()
    command = raw.upper()
    result = Transition(state, ctx)
    products = {p["sku"]: p for p in view["products"]}

    def reply(body, choices=MENU):
        result.replies += text(body, choices)
        return result

    if command in {"SELLER", "AGENT", "TAO", "TALK_TO_SELLER", "STOP"}:
        result.actions = ["pause"]
        return reply(COPY["paused"], [])
    if command == "CANCEL":
        return Transition("IDLE", {}, text(COPY["cancel"], MENU))
    if command in {"MENU", "GET_STARTED"} or (state == "IDLE" and command in {"HI", "HELLO"}):
        result.state = "IDLE"
        return reply(
            f"Welcome to {view['shop_name']}!\nOrder details are used to fulfill your order. {view['privacy_url']}"
        )
    if command in {"TRACK", "TRACK ORDER"}:
        return reply(view["tracking"])
    if command in {"SHOP", "ADD_MORE"} or command.startswith("SHOP_PAGE:"):
        if not view["catalog_fresh"]:
            return reply(COPY["catalog_unavailable"])
        page = int(command.split(":")[1]) if re.fullmatch(r"SHOP_PAGE:\d{1,4}", command) else 0
        result.state = "BROWSING"
        result.replies = catalog_messages(view["products"], page)
        return result
    if command.startswith("PRODUCT:"):
        sku = raw.split(":", 1)[1]
        if sku not in products or products[sku]["stock"] < 1:
            return reply(COPY["unavailable"])
        ctx["selected"] = sku
        result.state = "QTY"
        return reply(COPY["qty"], [(str(i), f"QTY:{i}") for i in range(1, 6)])
    if command.startswith("CONFIRM:"):
        token = f"CONFIRM:{ctx.get('checkout_id')}:{ctx.get('version')}"
        if state != "CONFIRMING" or raw != token:
            return reply(COPY["stale"])
        result.actions = ["confirm"]
        return result
    if command == "CHECKOUT":
        if not ctx.get("cart"):
            return reply(COPY["empty"])
        ctx["checkout_id"] = view["new_id"]
        ctx["draft_created_at"] = view["now"]
        ctx["version"] = 1
        ctx.pop("quote", None)
        result.state = "DELIVERY"
        return reply(
            COPY["delivery"], [("Delivery", "DELIVERY:delivery"), ("Pickup", "DELIVERY:pickup")]
        )
    if command == "EDIT" and state == "CONFIRMING":
        ctx["version"] += 1
        result.state = "DELIVERY"
        return reply(
            COPY["delivery"], [("Delivery", "DELIVERY:delivery"), ("Pickup", "DELIVERY:pickup")]
        )
    if state in CHECKOUT_STEPS and "?" in raw:
        # A question mid-checkout is answered, never saved as a name or address.
        answer = faq_answer(normalize(raw), view["faq"])
        prompts = {
            "QTY": (COPY["qty"], [(str(i), f"QTY:{i}") for i in range(1, 6)]),
            "DELIVERY": (
                COPY["delivery"],
                [("Delivery", "DELIVERY:delivery"), ("Pickup", "DELIVERY:pickup")],
            ),
            "NAME": (COPY["name"], []),
            "PHONE": (COPY["phone"], []),
            "ADDRESS": (COPY["address"], []),
            "PAYMENT": (COPY["payment"], [(p.upper(), f"PAY:{p}") for p in view["payments"]]),
        }
        body, choices = prompts[state]
        return reply(f"{answer}\n\n{body}" if answer else body, choices)
    if state == "DELIVERY" and not raw.startswith("DELIVERY:"):
        typed = normalize(raw)
        if re.search(r"\bpick", typed):
            raw = "DELIVERY:pickup"
        elif re.search(r"\b(deliver\w*|ship\w*|padala)\b", typed):
            raw = "DELIVERY:delivery"
    if state == "PAYMENT" and not raw.startswith("PAY:"):
        typed = normalize(raw)
        for method in view["payments"]:
            if method in typed.split() or (method == "cod" and "cash on delivery" in typed):
                raw = f"PAY:{method}"
                break
    if state == "QTY":
        qty = int(raw.split(":", 1)[1]) if re.fullmatch(r"QTY:\d{1,2}", raw) else quantity(raw)
        sku = ctx.get("selected")
        cart = ctx.setdefault("cart", {})
        if sku not in cart and len(cart) >= 20:
            return reply(COPY["cart_limit"])
        if (
            sku not in products
            or not 1 <= qty <= 99
            or cart.get(sku, 0) + qty > min(99, products[sku]["stock"])
        ):
            return reply(COPY["invalid_qty"])
        cart[sku] = cart.get(sku, 0) + qty
        result.state = "CART"
        body = "Your cart\n" + "\n".join(
            f"{q} × {products[s]['name']} — {money(q * products[s]['price_minor'])}"
            for s, q in cart.items()
            if s in products
        )
        return reply(
            body, [("Add more", "ADD_MORE"), ("Checkout", "CHECKOUT"), ("Cancel", "CANCEL")]
        )
    if state == "DELIVERY" and raw in {"DELIVERY:delivery", "DELIVERY:pickup"}:
        ctx["delivery"] = raw.split(":")[1]
        ctx.pop("address", None)
        result.state = "NAME"
        return reply(COPY["name"], [])
    if state == "NAME":
        if (
            not 2 <= len(raw) <= 80
            or not any(c.isalpha() for c in raw)
            or any(ord(c) < 32 for c in raw)
        ):
            return reply(COPY["invalid_name"], [])
        ctx["name"] = raw
        result.state = "PHONE"
        return reply(COPY["phone"], [])
    if state == "PHONE":
        found = re.search(
            r"(?<!\d)(?:09[0-9]{9}|\+?639[0-9]{9})(?!\d)", re.sub(r"[\s()-]", "", raw)
        )
        phone = found.group() if found else ""
        if not phone:
            ctx["phone_failures"] = ctx.get("phone_failures", 0) + 1
            return reply(
                COPY["invalid_phone"],
                [("Talk to seller", "SELLER")] if ctx["phone_failures"] >= 3 else [],
            )
        ctx["phone"] = "0" + phone[-10:]
        result.state = "ADDRESS" if ctx["delivery"] == "delivery" else "PAYMENT"
        return reply(
            COPY["address"] if result.state == "ADDRESS" else COPY["payment"],
            []
            if result.state == "ADDRESS"
            else [(p.upper(), f"PAY:{p}") for p in view["payments"]],
        )
    if state == "ADDRESS":
        if not 10 <= len(raw) <= 300 or any(ord(c) < 32 for c in raw):
            return reply(COPY["invalid_address"], [])
        ctx["address"] = raw
        result.state = "PAYMENT"
        return reply(COPY["payment"], [(p.upper(), f"PAY:{p}") for p in view["payments"]])
    if state == "PAYMENT" and raw.startswith("PAY:") and raw[4:] in view["payments"]:
        ctx["payment"] = raw[4:]
        result.actions = ["quote"]
        result.state = "CONFIRMING"
        return result
    if state == "CONFIRMING" and ctx.get("quote"):
        return reply(
            summary(ctx),
            [
                ("Confirm", f"CONFIRM:{ctx['checkout_id']}:{ctx['version']}"),
                ("Edit", "EDIT"),
                ("Cancel", "CANCEL"),
            ],
        )
    if state in {"IDLE", "BROWSING", "CART"}:
        normalized = normalize(raw)
        if command == "FAQ":
            topics = [
                max((k.strip() for k in f["keywords"].split(",") if k.strip()), key=len)
                for f in view["faq"]
            ]
            if not topics:
                return reply(COPY["no_faq"])
            return reply(COPY["faq_topics"], [(t.capitalize()[:20], t) for t in topics[:12]])
        for intent, pattern in INTENTS:
            if pattern.search(normalized):
                return transition(state, ctx, intent, view)
        answer = faq_answer(normalized, view["faq"])
        if answer:
            return reply(answer)
        sku = find_product(normalized, products)
        if sku:
            qty = quantity(raw)
            if qty:
                return transition("QTY", {**ctx, "selected": sku}, str(qty), view)
            return transition(state, ctx, f"PRODUCT:{sku}", view)
        if BUY.search(normalized) and "cancel" not in normalized:
            return transition(state, ctx, "SHOP", view)
        if GREETING.search(normalized):
            return transition(state, ctx, "MENU", view)
        if THANKS.search(normalized):
            return reply(COPY["thanks"])
    ctx["misses"] = ctx.get("misses", 0) + 1
    return reply(COPY["fallback"])
