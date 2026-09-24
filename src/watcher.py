import hashlib,time
from datetime import datetime,timezone
from .models import LeaderFill
from .aggregator import FillAggregator
from .risk import decide

def fingerprint(row):
    raw="|".join(str(row.get(k,"")) for k in ("transactionHash","asset","side","price","size","timestamp"))
    return hashlib.sha256(raw.encode()).hexdigest()

class WalletWatcher:
    def __init__(self,client,store,leaders,base_trade=50):
        self.client,self.store,self.leaders=client,store,leaders
        self.base_trade=base_trade
        self.aggregator=FillAggregator()
    def bootstrap(self):
        marked=0
        for leader in self.leaders:
            for row in self.client.activity(leader.wallet,100):
                fp=fingerprint(row)
                if not self.store.seen(fp):
                    self.store.mark_seen(fp,int(row.get("timestamp") or time.time()))
                    marked+=1
        return marked
    def poll_once(self):
        handled=0
        for leader in self.leaders:
            for row in reversed(self.client.activity(leader.wallet,100)):
                fp=fingerprint(row)
                if self.store.seen(fp):
                    continue
                self.store.mark_seen(fp,int(row.get("timestamp") or time.time()))
                self._handle(leader,row)
                handled+=1
        return handled
    def _handle(self,leader,row):
        token=str(row.get("asset") or "")
        if not token:
            return
        side=str(row.get("side") or "BUY").upper()
        price=float(row.get("price") or 0)
        usdc=float(row.get("usdcSize") or (float(row.get("size") or 0)*price))
        ts=int(row.get("timestamp") or time.time())
        fill=LeaderFill(leader.name,leader.wallet,str(row.get("conditionId") or ""),str(row.get("eventSlug") or ""),str(row.get("outcome") or ""),side,price,usdc,datetime.fromtimestamp(ts,tz=timezone.utc),token,str(row.get("transactionHash") or ""))
        self.aggregator.add(fill)
        current=self.client.executable_price(token,side)
        if current is None:
            action,reason,slip,size="SKIP","empty_order_book",None,0.0
        else:
            key=(fill.wallet.lower(),fill.market,fill.outcome,fill.side)
            signal=self.aggregator.signal(key,current)
            d=decide(signal,leader.min_trade_usd,leader.max_slippage,self.base_trade)
            action,reason,slip,size=d.action,d.reason,d.slippage,d.size_usd
        self.store.save({"observed_at":int(time.time()),"leader":leader.name,"wallet":leader.wallet,"transaction_hash":fill.transaction_hash,"market":fill.market,"event":fill.event,"outcome":fill.outcome,"side":side,"token_id":token,"leader_price":price,"leader_usdc":usdc,"current_price":current,"slippage":slip,"action":action,"reason":reason,"simulated_size":size})
        print("[{}] {} {} {} leader=${:.2f} @ {:.4f} current={} reason={}".format(action,leader.name,side,fill.outcome,usdc,price,current,reason),flush=True)
