from dataclasses import dataclass
from .models import Signal

@dataclass(slots=True)
class Decision:
    action: str
    size_usd: float
    reason: str
    slippage: float

def decide(signal: Signal, min_leader_trade: float, max_slippage: float, base_trade: float = 50) -> Decision:
    if signal.leader_size_usd < min_leader_trade:
        return Decision("SKIP", 0, "leader_position_too_small", 0)
    slippage = signal.current_price - signal.leader_vwap if signal.side.upper() == "BUY" else signal.leader_vwap - signal.current_price
    if slippage > max_slippage:
        return Decision("SKIP", 0, "price_moved", slippage)
    return Decision("COPY", base_trade, "paper_fill", slippage)
