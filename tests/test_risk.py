from src.models import Signal
from src.risk import decide

def test_copy_when_price_is_close():
    signal = Signal("x", "m", "e", "YES", "BUY", 0.50, 5000, 0.51)
    decision = decide(signal, 2000, 0.02)
    assert decision.action == "COPY"
    assert decision.size_usd == 50

def test_skip_when_price_moved():
    signal = Signal("x", "m", "e", "YES", "BUY", 0.50, 5000, 0.54)
    assert decide(signal, 2000, 0.02).reason == "price_moved"

def test_skip_small_leader_build():
    signal = Signal("x", "m", "e", "YES", "BUY", 0.50, 500, 0.50)
    assert decide(signal, 2000, 0.02).reason == "leader_position_too_small"
