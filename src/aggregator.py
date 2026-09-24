from dataclasses import dataclass, field
from datetime import datetime
from .models import LeaderFill, Signal

@dataclass
class PositionBuild:
    key: tuple
    fills: list[LeaderFill] = field(default_factory=list)
    first_seen: float = 0.0
    last_seen: float = 0.0

    @property
    def total_usd(self):
        return sum(f.size_usd for f in self.fills)

    @property
    def vwap(self):
        total=self.total_usd
        return sum(f.price*f.size_usd for f in self.fills)/total if total else 0.0

class TimedFillAggregator:
    def __init__(self, window_seconds=30.0):
        self.window_seconds=float(window_seconds)
        self._builds={}

    @staticmethod
    def key(fill):
        return (fill.wallet.lower(),fill.market,fill.outcome,fill.side)

    def add(self,fill,observed_at):
        key=self.key(fill)
        build=self._builds.get(key)
        if build is None:
            build=PositionBuild(key=key,first_seen=observed_at,last_seen=observed_at)
            self._builds[key]=build
        build.fills.append(fill)
        build.last_seen=observed_at

    def pop_ready(self,now):
        ready=[]
        for key,build in list(self._builds.items()):
            if now-build.last_seen >= self.window_seconds:
                ready.append(self._builds.pop(key))
        return ready

    def to_signal(self,build,current_price):
        f=build.fills[-1]
        return Signal(f.leader,f.market,f.event,f.outcome,f.side,build.vwap,build.total_usd,current_price)
