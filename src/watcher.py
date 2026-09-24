import hashlib,time
from datetime import datetime,timezone
from .models import LeaderFill
from .aggregator import TimedFillAggregator
from .sessions import SessionAggregator
from .strategies import evaluate_matrix

def fingerprint(row):
    raw="|".join(str(row.get(k,"")) for k in ("transactionHash","asset","side","price","size","timestamp"))
    return hashlib.sha256(raw.encode()).hexdigest()

class WalletWatcher:
    def __init__(self,client,store,leaders,base_trade=50,build_window=30,session_gap=300):
        self.client,self.store,self.leaders=client,store,leaders; self.base_trade=float(base_trade)
        self.aggregator=TimedFillAggregator(build_window); self.sessions=SessionAggregator(session_gap)
    def bootstrap(self):
        marked=0
        for leader in self.leaders:
            for row in self.client.activity(leader.wallet,100):
                fp=fingerprint(row)
                if not self.store.seen(fp): self.store.mark_seen(fp,int(row.get("timestamp") or time.time())); marked+=1
        return marked
    def poll_once(self):
        handled=0
        for leader in self.leaders:
            for row in reversed(self.client.activity(leader.wallet,100)):
                fp=fingerprint(row)
                if self.store.seen(fp): continue
                now=time.time(); ts=int(row.get("timestamp") or now); self.store.mark_seen(fp,ts); self._collect(leader,row,now,ts); handled+=1
        now=time.time(); self.flush_ready(now); self.flush_sessions(now); return handled
    def _collect(self,leader,row,now,ts):
        token=str(row.get("asset") or "")
        if not token: return
        side=str(row.get("side") or "BUY").upper(); price=float(row.get("price") or 0); usdc=float(row.get("usdcSize") or (float(row.get("size") or 0)*price))
        fill=LeaderFill(leader.name,leader.wallet,str(row.get("conditionId") or ""),str(row.get("eventSlug") or ""),str(row.get("outcome") or ""),side,price,usdc,datetime.fromtimestamp(ts,tz=timezone.utc),token,str(row.get("transactionHash") or ""))
        self.aggregator.add(fill,now); closed=self.sessions.add(fill,now)
        if closed: self._store_session(closed,now)
        latency=max(0,now-ts); self.store.insert("raw_fills",{"observed_at":now,"trade_ts":ts,"latency_seconds":latency,"leader":leader.name,"wallet":leader.wallet,"transaction_hash":fill.transaction_hash,"market":fill.market,"event":fill.event,"outcome":fill.outcome,"side":side,"token_id":token,"leader_price":price,"leader_usdc":usdc})
        print("[FILL] {} {} {} ${:.2f} @ {:.4f} api_latency={:.1f}s".format(leader.name,side,fill.outcome,usdc,price,latency),flush=True)
    def flush_ready(self,now):
        for build in self.aggregator.pop_ready(now):
            fill=build.fills[-1]; current=self.client.executable_price(fill.token_id,fill.side); slip=None if current is None else (current-build.vwap if fill.side=="BUY" else build.vwap-current)
            latencies=[max(0,build.last_seen-f.observed_at.timestamp()) for f in build.fills]; duration=max(0,(build.fills[-1].observed_at-build.fills[0].observed_at).total_seconds())
            build_id=self.store.insert("paper_builds",{"decided_at":now,"leader":fill.leader,"wallet":fill.wallet,"market":fill.market,"event":fill.event,"outcome":fill.outcome,"side":fill.side,"token_id":fill.token_id,"fill_count":len(build.fills),"build_usdc":build.total_usd,"leader_vwap":build.vwap,"build_duration_seconds":duration,"avg_latency_seconds":sum(latencies)/len(latencies),"current_price":current,"slippage":slip,"action":"OBSERVE","reason":"strategy_matrix","simulated_size":0.0})
            results=evaluate_matrix(build.total_usd,slip,self.base_trade); copied=0
            for r in results:
                self.store.insert("strategy_decisions",{"build_id":build_id,"strategy":r.strategy,"min_build_usd":r.min_build_usd,"max_slippage":r.max_slippage,"action":r.action,"reason":r.reason,"simulated_size":r.simulated_size})
                if r.action=="COPY" and current is not None and current>0:
                    shares=r.simulated_size/current
                    self.store.insert("paper_trades",{"opened_at":now,"build_id":build_id,"strategy":r.strategy,"leader":fill.leader,"wallet":fill.wallet,"market":fill.market,"event":fill.event,"outcome":fill.outcome,"side":fill.side,"token_id":fill.token_id,"entry_price":current,"stake_usd":r.simulated_size,"shares":shares}); copied+=1
            print("[BUILD] {} {} {} fills={} total=${:.2f} VWAP={:.4f} current={} slip={} paper_trades={}/24".format(fill.leader,fill.side,fill.outcome,len(build.fills),build.total_usd,build.vwap,current,None if slip is None else round(slip,4),copied),flush=True)
    def flush_sessions(self,now):
        for session in self.sessions.pop_ready(now): self._store_session(session,now)
    def _store_session(self,session,now):
        fill=session.fills[-1]; current=self.client.executable_price(fill.token_id,fill.side); mark=None
        if current is not None and session.vwap>0: mark=(current-session.vwap)/session.vwap if fill.side=="BUY" else (session.vwap-current)/session.vwap
        duration=max(0,(session.fills[-1].observed_at-session.fills[0].observed_at).total_seconds())
        self.store.insert("position_sessions",{"closed_at":now,"leader":fill.leader,"wallet":fill.wallet,"market":fill.market,"event":fill.event,"outcome":fill.outcome,"side":fill.side,"token_id":fill.token_id,"fill_count":len(session.fills),"session_usdc":session.total_usd,"leader_vwap":session.vwap,"session_duration_seconds":duration,"current_price":current,"mark_pnl_pct":mark})
        marked=0
        if current is not None:
            for trade_id,side,entry,stake,shares in self.store.paper_trades_for_token(fill.token_id):
                value=shares*current
                pnl=(current-entry)*shares if side=="BUY" else (entry-current)*shares
                self.store.insert("paper_marks",{"marked_at":now,"trade_id":trade_id,"mark_price":current,"value_usd":value,"pnl_usd":pnl,"pnl_pct":pnl/stake if stake else 0.0}); marked+=1
        print("[SESSION] {} {} {} fills={} total=${:.2f} VWAP={:.4f} mark={} leader_mark_pnl={} paper_marks={}".format(fill.leader,fill.side,fill.outcome,len(session.fills),session.total_usd,session.vwap,current,None if mark is None else round(mark*100,2),marked),flush=True)
