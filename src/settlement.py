import time
class SettlementScanner:
    def __init__(self,client,store,interval=300): self.client=client; self.store=store; self.interval=float(interval); self.last_run=0.0
    def maybe_run(self,now=None):
        now=now or time.time()
        if now-self.last_run<self.interval:return 0
        self.last_run=now; settled=0; recovered=0; counts={"ACTIVE":0,"NOT_FOUND":0,"AMBIGUOUS":0,"TOKEN_MISMATCH":0,"ERROR":0}
        for condition_id,token,event_slug,legacy_event_recovered in self.store.unsettled_markets():
            recovered += int(bool(legacy_event_recovered))
            resolution=self.client.market_resolution(condition_id,token,event_slug)
            status=(resolution or {}).get("status","ERROR")
            if status!="VERIFIED": counts[status]=counts.get(status,0)+1; continue
            price=float(resolution["settlement_price"])
            trades=self.store.unsettled_trades_for_token(token)
            for trade_id,side,entry,stake,shares in trades:
                value=shares*price
                pnl=(price-entry)*shares if side=="BUY" else (entry-price)*shares
                self.store.settle_trade_verified(trade_id,now,price,value,pnl,pnl/stake if stake else 0.0,condition_id,token,resolution.get("token_outcome",""),resolution.get("winning_outcome",""),resolution.get("question","")); settled+=1
                print("[SETTLED] trade={} event={} source={} token_outcome={!r} winner={!r} payout={} entry={:.4f} pnl=${:.2f}".format(trade_id,event_slug,resolution.get("source",""),resolution.get("token_outcome",""),resolution.get("winning_outcome",""),price,entry,pnl),flush=True)
        print("[SETTLEMENT] verified={} active={} not_found={} ambiguous={} token_mismatch={} errors={} legacy_event_recovered={}".format(settled,counts.get("ACTIVE",0),counts.get("NOT_FOUND",0),counts.get("AMBIGUOUS",0),counts.get("TOKEN_MISMATCH",0),counts.get("ERROR",0),recovered),flush=True)
        return settled
