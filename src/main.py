import time
from .config import load_leaders,setting
from .polymarket import PolymarketPublicClient
from .storage import Store
from .watcher import WalletWatcher

def main():
    leaders=load_leaders(); mode=setting("MODE","PAPER").upper()
    if mode!="PAPER": raise RuntimeError("v0.2 refuses to run outside PAPER mode")
    poll=float(setting("POLL_SECONDS","2")); base=float(setting("BASE_TRADE_USD","50")); window=float(setting("BUILD_WINDOW_SECONDS","30"))
    client=PolymarketPublicClient(); store=Store("data/paper.db")
    watcher=WalletWatcher(client,store,leaders,base,window)
    print("Polymarket Copy Engine v0.2 | PAPER | leaders={} | build_window={}s".format(len(leaders),window),flush=True)
    marked=watcher.bootstrap(); print("Bootstrap complete: {} existing activity rows ignored.".format(marked),flush=True)
    while True:
        try:
            n=watcher.poll_once()
            if n: print("Collected {} new leader fills.".format(n),flush=True)
        except Exception as exc:
            print("poll error: {!r}".format(exc),flush=True)
        time.sleep(poll)

if __name__=="__main__": main()
