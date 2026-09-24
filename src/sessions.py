from dataclasses import dataclass, field

@dataclass
class PositionSession:
    key: tuple
    fills: list = field(default_factory=list)
    first_seen: float = 0.0
    last_seen: float = 0.0

    @property
    def total_usd(self): return sum(f.size_usd for f in self.fills)
    @property
    def vwap(self):
        total=self.total_usd
        return sum(f.price*f.size_usd for f in self.fills)/total if total else 0.0

class SessionAggregator:
    def __init__(self,gap_seconds=300):
        self.gap_seconds=float(gap_seconds); self.sessions={}
    @staticmethod
    def key(fill): return (fill.wallet.lower(),fill.market,fill.outcome,fill.side)
    def add(self,fill,observed_at):
        key=self.key(fill); old=self.sessions.get(key); closed=None
        if old is not None and observed_at-old.last_seen>=self.gap_seconds:
            closed=old; old=None
        if old is None:
            old=PositionSession(key=key,first_seen=observed_at,last_seen=observed_at); self.sessions[key]=old
        old.fills.append(fill); old.last_seen=observed_at
        return closed
    def pop_ready(self,now):
        ready=[]
        for key,s in list(self.sessions.items()):
            if now-s.last_seen>=self.gap_seconds:
                ready.append(self.sessions.pop(key))
        return ready
