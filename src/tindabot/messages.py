"""Customer copy and Messenger message builders. No network or database access."""


def text(body: str, choices=()) -> list[dict]:
    result = [{"text": body[i : i + 1900]} for i in range(0, len(body), 1900)] or [{"text": "Menu"}]
    if choices:
        result[-1]["quick_replies"] = [
            {"content_type": "text", "title": title[:20], "payload": payload}
            for title, payload in choices[:13]
        ]
    return result


MENU = [("Shop", "SHOP"), ("FAQ", "FAQ"), ("Track order", "TRACK"), ("Talk to seller", "SELLER")]
COPY = {
    "cart_limit": "Your cart has reached 20 different products. Please check out or cancel to start again.",
    "name": "What name should we put on your order?",
    "phone": "Your PH mobile number? Example: 09171234567",
    "address": "Your complete delivery address, including city and barangay?",
    "invalid_name": "Please enter a name with 2–80 characters.",
    "invalid_phone": "Please enter a valid PH mobile number, such as 09171234567.",
    "invalid_address": "Please enter a complete address (10–300 characters).",
    "qty": "How many? Enter a number from 1 to 99.",
    "invalid_qty": "That quantity is unavailable. Enter a quantity within the available stock.",
    "empty": "Your cart is empty. Let's find something you like.",
    "cancel": "Checkout cancelled. You can start again any time.",
    "paused": "The seller will take over here. Send MENU when you want to use the bot again.",
    "stale": "That button has expired. Please review your current cart before confirming.",
    "unavailable": "Some items are no longer available. Please update your cart.",
    "changed": "The price or delivery details changed. Please review the updated summary and confirm again.",
    "catalog_unavailable": "The shop list is being updated. Please try again shortly or talk to the seller.",
    "fallback": "I didn't understand that. Use the buttons below, or type MENU, CANCEL, TRACK or SELLER.",
    "none": "You have no orders yet.",
    "payment": "Choose your payment method.",
    "delivery": "Delivery or pickup?",
    "expired": "Your previous checkout expired. Let's start again.",
}


def money(value: int) -> str:
    return f"PHP {value / 100:,.2f}"


def summary(ctx: dict) -> str:
    quote = ctx["quote"]
    lines = ["Order summary"]
    lines.extend(
        f"{p['qty']} × {p['name']} — {money(p['qty'] * p['price_minor'])}" for p in quote["items"]
    )
    lines.extend(
        [
            f"Shipping: {money(quote['shipping_minor'])}",
            f"Total: {money(quote['total_minor'])}",
            f"Method: {ctx['delivery']} / {ctx['payment']}",
            f"Name: {ctx['name']}",
            f"Phone: {ctx['phone']}",
        ]
    )
    if ctx.get("address"):
        lines.append(ctx["address"])
    if ctx["delivery"] == "pickup":
        lines.append(quote["pickup_address"])
    return "\n".join(lines)


def confirmation(code: str, payment: str, instructions: str) -> list[dict]:
    body = f"Salamat! Your order code is {code}. The seller will review your order."
    if payment != "cod":
        body += "\n" + instructions + "\nPayment is verified by the seller."
    return text(body, MENU)


def catalog_messages(products: list[dict], page: int) -> list[dict]:
    selected = products[page * 9 : (page + 1) * 9]
    if not selected:
        return text("No products available on this page.", MENU)
    cards = []
    for p in selected:
        card = {
            "title": p["name"][:80],
            "subtitle": f"{money(p['price_minor'])} · {p['stock']} available",
            "buttons": [
                {"type": "postback", "title": "Add to cart", "payload": f"PRODUCT:{p['sku']}"}
            ],
        }
        if p.get("image_url"):
            card["image_url"] = p["image_url"]
        cards.append(card)
    result = [
        {
            "attachment": {
                "type": "template",
                "payload": {"template_type": "generic", "elements": cards},
            }
        }
    ]
    choices = [("Checkout", "CHECKOUT"), ("Talk to seller", "SELLER")]
    if len(products) > (page + 1) * 9:
        choices.insert(0, ("More products", f"SHOP_PAGE:{page + 1}"))
    result += text("Choose a product to add to your cart.", choices)
    return result
