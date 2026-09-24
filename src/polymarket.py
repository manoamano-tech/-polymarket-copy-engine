import httpx
DATA_API="https://data-api.polymarket.com"
CLOB_API="https://clob.polymarket.com"

class PolymarketPublicClient:
    def __init__(self, timeout=10.0):
        self.client=httpx.Client(timeout=timeout,headers={"User-Agent":"polymarket-copy-engine/0.1"})
    def activity(self,wallet,limit=100):
        r=self.client.get(DATA_API+"/activity",params={"user":wallet,"type":"TRADE","limit":limit,"sortBy":"TIMESTAMP","sortDirection":"DESC"})
        r.raise_for_status()
        return r.json()
    def order_book(self,token_id):
        r=self.client.get(CLOB_API+"/book",params={"token_id":token_id})
        r.raise_for_status()
        return r.json()
    def executable_price(self,token_id,side):
        book=self.order_book(token_id)
        levels=book.get("asks" if side.upper()=="BUY" else "bids",[])
        if not levels:
            return None
        prices=[float(level["price"]) for level in levels]
        return min(prices) if side.upper()=="BUY" else max(prices)
    def close(self):
        self.client.close()
