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
    if state == "QTY":
        qty_text = raw.split(":", 1)[1] if command.startswith("QTY:") else raw
        qty = int(qty_text) if re.fullmatch(r"\d{1,2}", qty_text) else 0
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
        phone = re.sub(r"[\s()-]", "", raw)
        if not re.fullmatch(r"(?:09[0-9]{9}|\+?639[0-9]{9})", phone):
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
        normalized = re.sub(r"[^\w\s]", " ", raw.casefold())
        for faq in view["faq"]:
            if command == "FAQ" or any(
                re.search(r"(?<!\w)" + re.escape(k.strip().casefold()) + r"(?!\w)", normalized)
                for k in faq["keywords"].split(",")
                if k.strip()
            ):
                return reply(faq["answer"])
    ctx["misses"] = ctx.get("misses", 0) + 1
    return reply(COPY["fallback"])
