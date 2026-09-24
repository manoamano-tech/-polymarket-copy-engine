import time
from .config import load_leaders,setting
from .polymarket import PolymarketPublicClient
from .storage import Store
from .watcher import WalletWatcher
from .settlement import SettlementScanner

def main():
    leaders=load_leaders(); mode=setting("MODE","PAPER").upper()
    if mode!="PAPER": raise RuntimeError("v0.6.2 refuses to run outside PAPER mode")
    poll=float(setting("POLL_SECONDS","2")); base=float(setting("BASE_TRADE_USD","50")); window=float(setting("BUILD_WINDOW_SECONDS","30")); session_gap=float(setting("SESSION_GAP_SECONDS","300")); settlement_interval=float(setting("SETTLEMENT_CHECK_SECONDS","300"))
    client=PolymarketPublicClient(); store=Store("data/paper.db"); watcher=WalletWatcher(client,store,leaders,base,window,session_gap); scanner=SettlementScanner(client,store,settlement_interval)
    print("Polymarket Copy Engine v0.6.2 | PAPER | leaders={} | build_window={}s | session_gap={}s | settlement_check={}s | strategies=24".format(len(leaders),window,session_gap,settlement_interval),flush=True)
    marked=watcher.bootstrap(); print("Bootstrap complete: {} existing activity rows ignored.".format(marked),flush=True)
    stats=store.summary(); print("DB stats: fills={} builds={} sessions={} paper_trades={} settled={} api_latency avg={:.1f}s min={:.1f}s max={:.1f}s".format(stats["fills"],stats["builds"],stats["sessions"],stats["paper_trades"],stats["settled"],stats["avg_latency"],stats["min_latency"],stats["max_latency"]),flush=True)
    while True:
        try:
            n=watcher.poll_once(); scanner.maybe_run()
            if n: print("Collected {} new leader fills.".format(n),flush=True)
        except Exception as exc: print("poll error: {!r}".format(exc),flush=True)
        time.sleep(poll)
if __name__=="__main__": main()
