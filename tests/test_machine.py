import pytest

from tindabot.cli import DEMO
from tindabot.machine import transition
from tindabot.messages import COPY

VIEW = {
    "products": [{**p, "image_url": ""} for p in DEMO["products"]],
    "faq": DEMO["faq"],
    "catalog_fresh": True,
    "tracking": "TB-1: pending",
    "shop_name": "Demo",
    "privacy_url": "",
    "new_id": "checkout-1",
    "now": 0,
    "payments": ["cod", "gcash"],
}
FAQ = {f["keywords"].split(",")[0]: f["answer"] for f in DEMO["faq"]}


def say(value, state="IDLE", **ctx):
    result = transition(state, ctx, value, VIEW)
    return result, " ".join(r.get("text", "") for r in result.replies)


@pytest.mark.parametrize(
    "message",
    ["pa order po", "order po", "i want to order", "pabili po", "mine", "kuha ako"],
)
def test_buying_words_open_the_shop(message):
    result, _ = say(message)
    assert result.state == "BROWSING"


@pytest.mark.parametrize(
    ("message", "sku", "qty"),
    [("2 ube pandesal po", "UBE-01", 2), ("kuha ako tatlo choco crinkle", "CHOCO-01", 3)],
)
def test_product_and_quantity_go_straight_to_the_cart(message, sku, qty):
    result, body = say(message)
    assert result.state == "CART" and result.context["cart"] == {sku: qty}
    assert body.startswith("Your cart")


def test_product_without_quantity_asks_how_many():
    result, body = say("ube pandesal")
    assert result.state == "QTY" and result.context["selected"] == "UBE-01"
    assert body == COPY["qty"]


@pytest.mark.parametrize(
    "message", ["pakausap sa seller", "may tao ba dito?", "real person please"]
)
def test_asking_for_a_person_hands_over(message):
    result, _ = say(message)
    assert result.actions == ["pause"]


@pytest.mark.parametrize("message", ["san na order ko?", "na ship na po ba?", "status ng order"])
def test_order_questions_get_tracking(message):
    assert say(message)[1] == VIEW["tracking"]


def test_greeting_thanks_and_cancel():
    assert say("good morning po")[1].startswith("Welcome to Demo!")
    assert say("salamat po")[1] == COPY["thanks"]
    # Cancelling a placed order is not a request to shop.
    assert say("cancel my order")[0].state == "IDLE"


@pytest.mark.parametrize(
    ("message", "topic"),
    [
        ("magkano shipping sa qc?", "shipping"),
        ("how much delivery fee", "shipping"),
        ("hm po", "hm"),
    ],
)
def test_the_topic_later_in_the_message_wins(message, topic):
    assert say(message)[1] == FAQ[topic]


def test_faq_button_lists_topics_that_answer_when_tapped():
    _, body = say("FAQ")
    result = transition("IDLE", {}, "FAQ", VIEW)
    payloads = [q["payload"] for q in result.replies[-1]["quick_replies"]]
    assert body == COPY["faq_topics"] and len(payloads) == len(DEMO["faq"])
    assert say(payloads[1])[1] == DEMO["faq"][1]["answer"]


@pytest.mark.parametrize(
    ("state", "ctx", "typed", "next_state"),
    [
        ("QTY", {"selected": "UBE-01"}, "2 pcs", "CART"),
        ("QTY", {"selected": "UBE-01"}, "dalawa", "CART"),
        ("DELIVERY", {}, "pickup po", "NAME"),
        ("DELIVERY", {}, "deliver po", "NAME"),
        ("PHONE", {"delivery": "delivery"}, "09171234567 po", "ADDRESS"),
        ("PAYMENT", {"delivery": "delivery", "cart": {"UBE-01": 1}}, "gcash", "CONFIRMING"),
        (
            "PAYMENT",
            {"delivery": "delivery", "cart": {"UBE-01": 1}},
            "cash on delivery",
            "CONFIRMING",
        ),
    ],
)
def test_typed_checkout_answers_advance(state, ctx, typed, next_state):
    assert say(typed, state, **{"cart": {}, **ctx})[0].state == next_state


def test_question_mid_checkout_is_answered_not_saved_as_a_name():
    result, body = say("magkano shipping?", "NAME")
    assert result.state == "NAME" and "name" not in result.context
    assert body == FAQ["shipping"] + "\n\n" + COPY["name"]


def test_intents_never_hijack_checkout_answers():
    result, _ = say("Juan Seller", "NAME")
    assert result.state == "PHONE" and result.context["name"] == "Juan Seller"
    assert not result.actions


SHOP = {
    **VIEW,
    "products": [
        *VIEW["products"],
        {
            "sku": "L50",
            "name": "Aloe Lotion 50ml",
            "price_minor": 100,
            "stock": 80,
            "image_url": "",
        },
        {"sku": "JAM", "name": "Mango Jam", "price_minor": 100, "stock": 0, "image_url": ""},
    ],
}


@pytest.mark.parametrize(
    "message", ["pabili po ng Human Nature oil", "good for 2 person ba", "ilang tao kasya?"]
)
def test_words_like_person_or_brand_names_do_not_hand_over_a_buyer(message):
    assert not transition("IDLE", {}, message, SHOP).actions


def test_sizes_in_product_names_are_not_quantities():
    result = transition("IDLE", {}, "aloe lotion 50ml", SHOP)
    assert result.state == "QTY" and result.context["selected"] == "L50"
    assert "cart" not in result.context or not result.context["cart"]


def test_a_quantity_for_an_out_of_stock_product_does_not_strand_the_customer():
    result = transition("IDLE", {}, "2 mango jam", SHOP)
    assert (
        result.state == "IDLE"
        and " ".join(r["text"] for r in result.replies) == COPY["unavailable"]
    )


@pytest.mark.parametrize("typed", ["labing-isa", "sampu't lima", "dalawampu"])
def test_compound_tagalog_numbers_are_asked_again_not_guessed_low(typed):
    result = transition("QTY", {"selected": "UBE-01", "cart": {}}, typed, VIEW)
    assert result.state == "QTY" and result.context["cart"] == {}


def test_linker_number_words_count():
    result = transition("IDLE", {}, "isang ube pandesal po", VIEW)
    assert result.state == "CART" and result.context["cart"] == {"UBE-01": 1}


def test_faq_rows_without_keywords_never_crash_the_topic_list():
    view = {**VIEW, "faq": [{"keywords": " , ", "answer": "x"}, *VIEW["faq"]]}
    result = transition("IDLE", {}, "FAQ", view)
    assert len(result.replies[-1]["quick_replies"]) == len(VIEW["faq"])


def test_catalog_import_rejects_faq_rows_without_keywords():
    from pydantic import ValidationError

    from tindabot.catalog import FAQ

    with pytest.raises(ValidationError):
        FAQ(keywords=",", answer="x")


def test_a_seller_faq_about_orders_beats_the_tracking_shortcut():
    view = {**VIEW, "faq": [{"keywords": "order status", "answer": "We ship in 2 days."}]}
    assert transition("IDLE", {}, "order status?", view).replies[0]["text"] == "We ship in 2 days."


@pytest.mark.parametrize("message", ["gusto ko kausapin seller", "need agent", "seller po"])
def test_common_ways_to_ask_for_the_seller_still_hand_over(message):
    assert transition("IDLE", {}, message, VIEW).actions == ["pause"]
