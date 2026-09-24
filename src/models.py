from dataclasses import dataclass
from datetime import datetime

@dataclass(slots=True)
class LeaderFill:
    leader: str
    wallet: str
    market: str
    event: str
    outcome: str
    side: str
    price: float
    size_usd: float
    observed_at: datetime

@dataclass(slots=True)
class Signal:
    leader: str
    market: str
    event: str
    outcome: str
    side: str
    leader_vwap: float
    leader_size_usd: float
    current_price: float
