import time
class SettlementScanner:
    def __init__(self,client,store,interval=300): self.client=client; self.store=store; self.interval=float(interval); self.last_run=0.0
    def maybe_run(self,now=None):
        now=now or time.time()
        if now-self.last_run<self.interval:return 0
        self.last_run=now; settled=0; unresolved=0
        for condition_id,token in self.store.unsettled_markets():
            resolution=self.client.market_resolution(condition_id,token)
            if resolution is None: unresolved+=1; continue
            price=float(resolution["settlement_price"])
            for trade_id,side,entry,stake,shares in self.store.unsettled_trades_for_token(token):
                value=shares*price
                pnl=(price-entry)*shares if side=="BUY" else (entry-price)*shares
                self.store.settle_trade_verified(trade_id,now,price,value,pnl,pnl/stake if stake else 0.0,condition_id,token,resolution.get("token_outcome",""),resolution.get("winning_outcome",""),resolution.get("question","")); settled+=1
                print("[SETTLED] trade={} market={} token_outcome={!r} winner={!r} payout={} entry={:.4f} pnl=${:.2f}".format(trade_id,condition_id,resolution.get("token_outcome",""),resolution.get("winning_outcome",""),price,entry,pnl),flush=True)
        print("[SETTLEMENT] verified={} unresolved_or_ambiguous={}".format(settled,unresolved),flush=True)
        return settled
