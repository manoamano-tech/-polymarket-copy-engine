import httpx,json
DATA_API="https://data-api.polymarket.com"
CLOB_API="https://clob.polymarket.com"
GAMMA_API="https://gamma-api.polymarket.com"
class PolymarketPublicClient:
    def __init__(self,timeout=10.0): self.client=httpx.Client(timeout=timeout,headers={"User-Agent":"polymarket-copy-engine/0.6.2"})
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
    def _parse_list(self,value):
        if isinstance(value,list): return value
        if isinstance(value,str):
            try: return json.loads(value)
            except Exception: return []
        return []
    def _resolution_from_market(self,m,token_id,source):
        token=str(token_id); tids=[str(x) for x in self._parse_list(m.get("clobTokenIds") or m.get("clob_token_ids"))]
        outcomes=self._parse_list(m.get("outcomes")); prices=self._parse_list(m.get("outcomePrices") or m.get("outcome_prices"))
        if token not in tids: return {"status":"TOKEN_MISMATCH","source":source}
        if not bool(m.get("closed")): return {"status":"ACTIVE","source":source}
        if len(tids)!=len(prices) or not prices: return {"status":"AMBIGUOUS","source":source}
        try: vals=[float(x) for x in prices]
        except Exception: return {"status":"AMBIGUOUS","source":source}
        # Normal binary resolution is 1/0. Also permit explicit 50/50 resolution.
        valid_binary=all(v in (0.0,1.0) for v in vals) and vals.count(1.0)==1
        valid_half=len(vals)==2 and all(abs(v-0.5)<1e-9 for v in vals)
        if not (valid_binary or valid_half): return {"status":"AMBIGUOUS","source":source}
        idx=tids.index(token); winner_idx=vals.index(1.0) if valid_binary else None
        return {"status":"VERIFIED","source":source,"market_id":str(m.get("id") or ""),"question":str(m.get("question") or ""),"token_id":token,"token_outcome":str(outcomes[idx]) if idx<len(outcomes) else "","winning_outcome":str(outcomes[winner_idx]) if winner_idx is not None and winner_idx<len(outcomes) else "50/50","settlement_price":vals[idx]}
    def market_resolution(self,condition_id,token_id,event_slug=None):
        """Resolve conservatively. Try condition id first, then official Gamma event-by-slug fallback."""
        token=str(token_id); condition=str(condition_id or "").lower(); diagnostics=[]
        try:
            if condition:
                r=self.client.get(GAMMA_API+"/markets",params={"condition_ids":condition,"limit":10}); r.raise_for_status(); rows=r.json()
                if isinstance(rows,dict): rows=rows.get("markets") or rows.get("data") or []
                exact=[m for m in rows if str(m.get("conditionId") or m.get("condition_id") or "").lower()==condition]
                for m in exact:
                    result=self._resolution_from_market(m,token,"condition_id")
                    if result["status"] in ("VERIFIED","ACTIVE","AMBIGUOUS"): return result
                    diagnostics.append(result["status"])
            if event_slug:
                r=self.client.get(GAMMA_API+"/events/slug/"+str(event_slug));
                if r.status_code==200:
                    event=r.json(); markets=event.get("markets") or []
                    token_matches=[]
                    for m in markets:
                        tids=[str(x) for x in self._parse_list(m.get("clobTokenIds") or m.get("clob_token_ids"))]
                        if token in tids: token_matches.append(m)
                    if len(token_matches)==1: return self._resolution_from_market(token_matches[0],token,"event_slug")
                    if len(token_matches)>1: return {"status":"AMBIGUOUS","source":"event_slug"}
                elif r.status_code not in (404,422): r.raise_for_status()
        except Exception as exc:
            return {"status":"ERROR","source":"api","error":type(exc).__name__}
        return {"status":"NOT_FOUND" if not diagnostics else diagnostics[-1],"source":"none"}
    def close(self): self.client.close()
