import httpx,json
DATA_API="https://data-api.polymarket.com"
CLOB_API="https://clob.polymarket.com"
GAMMA_API="https://gamma-api.polymarket.com"
class PolymarketPublicClient:
    def __init__(self,timeout=10.0): self.client=httpx.Client(timeout=timeout,headers={"User-Agent":"polymarket-copy-engine/0.6.1"})
    def activity(self,wallet,limit=100):
        r=self.client.get(DATA_API+"/activity",params={"user":wallet,"type":"TRADE","limit":limit,"sortBy":"TIMESTAMP","sortDirection":"DESC"}); r.raise_for_status(); return r.json()
    def order_book(self,token_id):
        r=self.client.get(CLOB_API+"/book",params={"token_id":token_id}); r.raise_for_status(); return r.json()
    def executable_price(self,token_id,side):
        try: book=self.order_book(token_id)
        except Exception: return None
        levels=book.get("asks" if side.upper()=="BUY" else "bids",[])
        if not levels:return None
        prices=[float(level["price"]) for level in levels]; return min(prices) if side.upper()=="BUY" else max(prices)
    def market_resolution(self,condition_id,token_id):
        """Return verified resolution metadata, or None unless Gamma says closed and token payout is unambiguous 0/1."""
        if not condition_id or not token_id:return None
        try:
            r=self.client.get(GAMMA_API+"/markets",params={"condition_ids":condition_id,"limit":10}); r.raise_for_status(); rows=r.json()
            if isinstance(rows,dict): rows=rows.get("markets") or rows.get("data") or []
            for m in rows:
                if str(m.get("conditionId") or m.get("condition_id") or "").lower()!=str(condition_id).lower(): continue
                if not bool(m.get("closed")): return None
                tids=m.get("clobTokenIds") or m.get("clob_token_ids"); outcomes=m.get("outcomes"); prices=m.get("outcomePrices") or m.get("outcome_prices")
                if isinstance(tids,str): tids=json.loads(tids)
                if isinstance(outcomes,str): outcomes=json.loads(outcomes)
                if isinstance(prices,str): prices=json.loads(prices)
                if not isinstance(tids,list) or not isinstance(prices,list) or len(tids)!=len(prices): return None
                vals=[float(x) for x in prices]
                if any(v not in (0.0,1.0) for v in vals) or vals.count(1.0)!=1:return None
                token=str(token_id)
                if token not in [str(x) for x in tids]:return None
                idx=[str(x) for x in tids].index(token); winner_idx=vals.index(1.0)
                return {"market_id":str(m.get("id") or ""),"question":str(m.get("question") or ""),"token_id":token,"token_outcome":str(outcomes[idx]) if isinstance(outcomes,list) and idx<len(outcomes) else "","winning_outcome":str(outcomes[winner_idx]) if isinstance(outcomes,list) and winner_idx<len(outcomes) else "","settlement_price":vals[idx]}
        except Exception:return None
        return None
    def close(self): self.client.close()
