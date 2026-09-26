import hashlib,time
from datetime import datetime,timezone
from .models import LeaderFill
from .aggregator import TimedFillAggregator
from .sessions import SessionAggregator
from .strategies import evaluate_matrix
from .classification import classify_sport
from .copy_engine import evaluate_fill
from types import SimpleNamespace

def fingerprint(row):
    raw="|".join(str(row.get(k,"")) for k in ("transactionHash","asset","side","price","size","timestamp"))
    return hashlib.sha256(raw.encode()).hexdigest()

class WalletWatcher:
    def __init__(self,client,store,leaders,base_trade=50,build_window=30,session_gap=300):
        self.client,self.store,self.leaders=client,store,leaders; self.base_trade=float(base_trade)
        self.aggregator=TimedFillAggregator(build_window); self.sessions=SessionAggregator(session_gap); self.snapshot_queue=[]; self.snapshot_delays=(0,5,10,15,30,60)
    def bootstrap(self):
        marked=0
        for leader in self.leaders:
            for row in self.client.trades(leader.wallet,100):
                fp=fingerprint(row)
                if not self.store.seen(fp): self.store.mark_seen(fp,int(row.get("timestamp") or time.time())); marked+=1
        return marked
    def private_profiles(self):
        rows=self.store.db.execute("SELECT id,leader,source_wallet FROM copy_profiles WHERE enabled=1 AND source_type='PRIVATE' AND source_wallet IS NOT NULL AND source_wallet!=''").fetchall()
        return rows
    def _poll_private(self):
        handled=0
        for pid,label,wallet in self.private_profiles():
            try: rows=self.client.trades(wallet,100)
            except Exception as e:
                print("[PRIVATE] poll failed profile={} {}".format(pid,e),flush=True);continue
            for row in reversed(rows):
                fp=fingerprint(row)
                if self.store.db.execute("SELECT 1 FROM private_raw_fills WHERE profile_id=? AND fingerprint=?",(pid,fp)).fetchone():continue
                now=time.time();ts=int(row.get("timestamp") or now)
                # First observation is a cursor/bootstrap only: never copy historical catch-up fills.
                newest=self.store.db.execute("SELECT 1 FROM private_raw_fills WHERE profile_id=? LIMIT 1",(pid,)).fetchone()
                token=str(row.get("asset") or "");side=str(row.get("side") or "BUY").upper();price=float(row.get("price") or 0);usdc=float(row.get("usdcSize") or (float(row.get("size") or 0)*price));event=str(row.get("eventSlug") or "");sport,league=classify_sport(event)
                cur=self.store.db.execute("INSERT OR IGNORE INTO private_raw_fills(profile_id,fingerprint,observed_at,trade_ts,wallet,transaction_hash,market,event,outcome,side,token_id,leader_price,leader_usdc,sport,league) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(pid,fp,now,ts,wallet,str(row.get('transactionHash') or ''),str(row.get('conditionId') or ''),event,str(row.get('outcome') or ''),side,token,price,usdc,sport,league));self.store.db.commit()
                # Copy only fresh signals after the profile has a cursor; private history stays private.
                if newest and side=='BUY' and now-ts<=30 and token:
                    book=self.client.executable_price(token,side);evaluate_fill(self.store,-cur.lastrowid,label,token,sport,league,price,book,profile_id=pid)
                handled+=1
        return handled
    def poll_once(self):
        handled=self._poll_private()
        for leader in self.leaders:
            for row in reversed(self.client.trades(leader.wallet,100)):
                fp=fingerprint(row)
                if self.store.seen(fp): continue
                now=time.time(); ts=int(row.get("timestamp") or now); self.store.mark_seen(fp,ts); self._collect(leader,row,now,ts); handled+=1
        now=time.time(); self.flush_price_snapshots(now); self.flush_ready(now); self.flush_sessions(now); return handled
    def _collect(self,leader,row,now,ts):
        token=str(row.get("asset") or "")
        if not token: return
        side=str(row.get("side") or "BUY").upper(); price=float(row.get("price") or 0); usdc=float(row.get("usdcSize") or (float(row.get("size") or 0)*price))
        fill=LeaderFill(leader.name,leader.wallet,str(row.get("conditionId") or ""),str(row.get("eventSlug") or ""),str(row.get("outcome") or ""),side,price,usdc,datetime.fromtimestamp(ts,tz=timezone.utc),token,str(row.get("transactionHash") or ""))
        self.aggregator.add(fill,now); closed=self.sessions.add(fill,now)
        if closed: self._store_session(closed,now)
        sport,league=classify_sport(fill.event)
        latency=max(0,now-ts); fill_id=self.store.insert("raw_fills",{"observed_at":now,"trade_ts":ts,"latency_seconds":latency,"leader":leader.name,"wallet":leader.wallet,"transaction_hash":fill.transaction_hash,"market":fill.market,"event":fill.event,"outcome":fill.outcome,"side":side,"token_id":token,"leader_price":price,"leader_usdc":usdc,"sport":sport,"league":league})
        if leader.name=="RN1":
            for delay in self.snapshot_delays: self.snapshot_queue.append((now+delay,fill_id,now,token,side,delay))
        # The profile/filter pipeline is active now; execution remains DRY_RUN until wallet auth is connected.
        if side=="BUY":
            book_price=self.client.executable_price(token,side)
            evaluate_fill(self.store,fill_id,leader.name,token,sport,league,price,book_price)
        print("[FILL] {} {} {} ${:.2f} @ {:.4f} api_latency={:.1f}s".format(leader.name,side,fill.outcome,usdc,price,latency),flush=True)
    def flush_price_snapshots(self,now,max_per_poll=12):
        # Record actual sample time as well as target delay; delayed samples are never backdated.
        self.snapshot_queue.sort(key=lambda x:x[0]); done=0; keep=[]
        for due,fill_id,observed,token,side,target in self.snapshot_queue:
            if due>now or done>=max_per_poll:
                keep.append((due,fill_id,observed,token,side,target)); continue
            sampled=time.time(); price=self.client.executable_price(token,side)
            self.store.insert("fill_price_snapshots",{"fill_id":fill_id,"target_delay_seconds":target,"sampled_at":sampled,"actual_delay_seconds":sampled-observed,"executable_price":price})
            done+=1
        self.snapshot_queue=keep
    def flush_ready(self,now):
        for build in self.aggregator.pop_ready(now):
            fill=build.fills[-1]; current=self.client.executable_price(fill.token_id,fill.side); slip=None if current is None else (current-build.vwap if fill.side=="BUY" else build.vwap-current)
            latencies=[max(0,build.last_seen-f.observed_at.timestamp()) for f in build.fills]; duration=max(0,(build.fills[-1].observed_at-build.fills[0].observed_at).total_seconds())
            build_id=self.store.insert("paper_builds",{"decided_at":now,"leader":fill.leader,"wallet":fill.wallet,"market":fill.market,"event":fill.event,"outcome":fill.outcome,"side":fill.side,"token_id":fill.token_id,"fill_count":len(build.fills),"build_usdc":build.total_usd,"leader_vwap":build.vwap,"build_duration_seconds":duration,"avg_latency_seconds":sum(latencies)/len(latencies),"current_price":current,"slippage":slip,"action":"OBSERVE","reason":"strategy_matrix","simulated_size":0.0})
            results=evaluate_matrix(build.total_usd,slip,self.base_trade,len(build.fills)); copied=0
            for r in results:
                self.store.insert("strategy_decisions",{"build_id":build_id,"strategy":r.strategy,"min_build_usd":r.min_build_usd,"max_slippage":r.max_slippage,"action":r.action,"reason":r.reason,"simulated_size":r.simulated_size})
                if r.action=="COPY" and current is not None and current>0:
                    shares=r.simulated_size/current
                    self.store.insert("paper_trades",{"opened_at":now,"build_id":build_id,"strategy":r.strategy,"leader":fill.leader,"wallet":fill.wallet,"market":fill.market,"event":fill.event,"outcome":fill.outcome,"side":fill.side,"token_id":fill.token_id,"entry_price":current,"stake_usd":r.simulated_size,"shares":shares}); copied+=1
            print("[BUILD] {} {} {} fills={} total=${:.2f} VWAP={:.4f} current={} slip={} paper_trades={}/25".format(fill.leader,fill.side,fill.outcome,len(build.fills),build.total_usd,build.vwap,current,None if slip is None else round(slip,4),copied),flush=True)
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
