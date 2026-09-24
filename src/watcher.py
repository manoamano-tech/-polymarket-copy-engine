import hashlib,time
from datetime import datetime,timezone
from .models import LeaderFill
from .aggregator import TimedFillAggregator

def fingerprint(row):
    raw="|".join(str(row.get(k,"")) for k in ("transactionHash","asset","side","price","size","timestamp"))
    return hashlib.sha256(raw.encode()).hexdigest()

class WalletWatcher:
    def __init__(self,client,store,leaders,base_trade=50,build_window=30):
        self.client,self.store,self.leaders=client,store,leaders
        self.leader_by_wallet={x.wallet.lower():x for x in leaders}
        self.base_trade=float(base_trade)
        self.aggregator=TimedFillAggregator(build_window)

    def bootstrap(self):
        marked=0
        for leader in self.leaders:
            for row in self.client.activity(leader.wallet,100):
                fp=fingerprint(row)
                if not self.store.seen(fp):
                    self.store.mark_seen(fp,int(row.get("timestamp") or time.time())); marked+=1
        return marked

    def poll_once(self):
        handled=0
        for leader in self.leaders:
            for row in reversed(self.client.activity(leader.wallet,100)):
                fp=fingerprint(row)
                if self.store.seen(fp): continue
                now=time.time(); ts=int(row.get("timestamp") or now)
                self.store.mark_seen(fp,ts)
                self._collect(leader,row,now,ts); handled+=1
        self.flush_ready(time.time())
        return handled

    def _collect(self,leader,row,now,ts):
        token=str(row.get("asset") or "")
        if not token: return
        side=str(row.get("side") or "BUY").upper(); price=float(row.get("price") or 0)
        usdc=float(row.get("usdcSize") or (float(row.get("size") or 0)*price))
        fill=LeaderFill(leader.name,leader.wallet,str(row.get("conditionId") or ""),str(row.get("eventSlug") or ""),str(row.get("outcome") or ""),side,price,usdc,datetime.fromtimestamp(ts,tz=timezone.utc),token,str(row.get("transactionHash") or ""))
        self.aggregator.add(fill,now)
        self.store.insert("raw_fills",{"observed_at":now,"trade_ts":ts,"latency_seconds":max(0,now-ts),"leader":leader.name,"wallet":leader.wallet,"transaction_hash":fill.transaction_hash,"market":fill.market,"event":fill.event,"outcome":fill.outcome,"side":side,"token_id":token,"leader_price":price,"leader_usdc":usdc})
        print("[FILL] {} {} {} ${:.2f} @ {:.4f} latency={:.1f}s".format(leader.name,side,fill.outcome,usdc,price,max(0,now-ts)),flush=True)

    def flush_ready(self,now):
        for build in self.aggregator.pop_ready(now):
            fill=build.fills[-1]; leader=self.leader_by_wallet[fill.wallet.lower()]
            current=self.client.executable_price(fill.token_id,fill.side)
            if current is None:
                action,reason,slip,size="SKIP","empty_order_book",None,0.0
            else:
                signal=self.aggregator.to_signal(build,current)
                slip=current-build.vwap if fill.side=="BUY" else build.vwap-current
                action="COPY" if slip <= leader.max_slippage else "SKIP"
                reason="paper_fill" if action=="COPY" else "price_moved"
                size=self.base_trade if action=="COPY" else 0.0
            latencies=[max(0,build.last_seen-f.observed_at.timestamp()) for f in build.fills]
            duration=max(0,(build.fills[-1].observed_at-build.fills[0].observed_at).total_seconds())
            self.store.insert("paper_builds",{"decided_at":now,"leader":leader.name,"wallet":leader.wallet,"market":fill.market,"event":fill.event,"outcome":fill.outcome,"side":fill.side,"token_id":fill.token_id,"fill_count":len(build.fills),"build_usdc":build.total_usd,"leader_vwap":build.vwap,"build_duration_seconds":duration,"avg_latency_seconds":sum(latencies)/len(latencies),"current_price":current,"slippage":slip,"action":action,"reason":reason,"simulated_size":size})
            print("[BUILD {}] {} {} {} fills={} total=${:.2f} VWAP={:.4f} current={} slip={} -> {} ${:.2f}".format(reason,leader.name,fill.side,fill.outcome,len(build.fills),build.total_usd,build.vwap,current,None if slip is None else round(slip,4),action,size),flush=True)
