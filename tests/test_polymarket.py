from src.polymarket import PolymarketPublicClient

class FakeClient(PolymarketPublicClient):
    def __init__(self, book):
        self._book = book
    def order_book(self, token_id):
        return self._book

def test_buy_uses_lowest_ask_even_if_book_is_descending():
    c=FakeClient({"asks":[{"price":"0.99"},{"price":"0.62"},{"price":"0.60"}],"bids":[]})
    assert c.executable_price("x","BUY")==0.60

def test_sell_uses_highest_bid_even_if_book_is_ascending():
    c=FakeClient({"asks":[],"bids":[{"price":"0.01"},{"price":"0.55"},{"price":"0.58"}]})
    assert c.executable_price("x","SELL")==0.58

def test_empty_side_returns_none():
    c=FakeClient({"asks":[],"bids":[]})
    assert c.executable_price("x","BUY") is None
