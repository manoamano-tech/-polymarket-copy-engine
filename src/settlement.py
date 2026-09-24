import time
class SettlementScanner:
    def __init__(self,client,store,interval=300): self.client=client; self.store=store; self.interval=float(interval); self.last_run=0.0
    def maybe_run(self,now=None):
        now=now or time.time()
        if now-self.last_run<self.interval:return 0
        self.last_run=now; settled=0
        for token in self.store.unsettled_tokens():
            price=self.client.settlement_price(token)
            if price is None:continue
            for trade_id,side,entry,stake,shares in self.store.unsettled_trades_for_token(token):
                value=shares*price
                pnl=(price-entry)*shares if side=="BUY" else (entry-price)*shares
                self.store.settle_trade(trade_id,now,price,value,pnl,pnl/stake if stake else 0.0); settled+=1
        if settled: print("[SETTLEMENT] realized {} paper trades".format(settled),flush=True)
        return settled
