from tirekick.models import ChatMessage, ChatRole, Listing
from tirekick.verify.scam import scan_chat

L = Listing(listing_id="L", asking_price=4800)


def seller(text="", media_type=None):
    return ChatMessage(role=ChatRole.SELLER, text=text, media_type=media_type)


def reasons(msgs):
    return [e.summary for e in scan_chat(msgs, L, None)]


def test_deposit_before_video_is_flagged():
    assert any("deposit" in r for r in reasons([seller("Send a $500 deposit to hold it for you")]))


def test_deposit_after_video_is_not_flagged():
    assert reasons([seller(media_type="video/mp4"), seller("you can pay a deposit when you see it")]) == []


def test_gift_cards_and_shipping():
    rs = reasons([seller("I'm deployed, the car is with a shipping company, pay with gift cards")])
    assert len(rs) == 3


def test_zelle_alone_is_fine_but_not_with_shipping():
    assert reasons([seller("I take Zelle or cash")]) == []
    assert len(reasons([seller("Zelle me and the transport company delivers")])) == 2


def test_buyer_messages_ignored():
    assert scan_chat([ChatMessage(role=ChatRole.BUYER, text="should I send a deposit?")], L, None) == []
