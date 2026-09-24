from collections import defaultdict
from .models import LeaderFill, Signal

class FillAggregator:
    def __init__(self):
        self._fills = defaultdict(list)

    def add(self, fill: LeaderFill) -> None:
        key = (fill.wallet.lower(), fill.market, fill.outcome, fill.side)
        self._fills[key].append(fill)

    def signal(self, key, current_price: float) -> Signal:
        fills = self._fills[key]
        total = sum(fill.size_usd for fill in fills)
        vwap = sum(fill.price * fill.size_usd for fill in fills) / total
        fill = fills[-1]
        return Signal(fill.leader, fill.market, fill.event, fill.outcome, fill.side, vwap, total, current_price)
