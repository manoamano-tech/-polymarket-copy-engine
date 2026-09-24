import sqlite3
from .config import setting

DB_PATH="data/paper.db"

def pct(n,d): return 100.0*n/d if d else 0.0

def main():
    db=sqlite3.connect(DB_PATH)
    leaders=[r[0] for r in db.execute("SELECT DISTINCT leader FROM raw_fills ORDER BY leader")]
    print("=== POLYMARKET PAPER REPORT ===")
    for leader in leaders:
        fills=db.execute("SELECT COUNT(*),COALESCE(AVG(latency_seconds),0),COALESCE(MIN(latency_seconds),0),COALESCE(MAX(latency_seconds),0) FROM raw_fills WHERE leader=?",(leader,)).fetchone()
        builds=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=?",(leader,)).fetchone()[0]
        print("\n=== {} ===".format(leader))
        print("fills={} builds={} api_latency avg={:.1f}s min={:.1f}s max={:.1f}s".format(fills[0],builds,fills[1],fills[2],fills[3]))
        if not builds: continue
        for limit in (0.01,0.02,0.03,0.05):
            n=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND slippage IS NOT NULL AND slippage<=?",(leader,limit)).fetchone()[0]
            print("slippage <= {:d}c: {:5.1f}% ({}/{})".format(int(limit*100),pct(n,builds),n,builds))
        buckets=[("<$500",0,500),("$500-1k",500,1000),("$1k-2k",1000,2000),("$2k-5k",2000,5000),("$5k-10k",5000,10000),(">=$10k",10000,None)]
        print("build sizes:")
        for name,lo,hi in buckets:
            if hi is None: n=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND build_usdc>=?",(leader,lo)).fetchone()[0]
            else: n=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND build_usdc>=? AND build_usdc<?",(leader,lo,hi)).fetchone()[0]
            print("  {:9s} {:5.1f}% ({})".format(name,pct(n,builds),n))
        print("strategy pass rates:")
        rows=db.execute("SELECT sd.strategy,SUM(CASE WHEN sd.action='COPY' THEN 1 ELSE 0 END),COUNT(*) FROM strategy_decisions sd JOIN paper_builds pb ON pb.id=sd.build_id WHERE pb.leader=? GROUP BY sd.strategy ORDER BY sd.min_build_usd,sd.max_slippage",(leader,)).fetchall()
        for name,copies,total in rows:
            print("  {:16s} {:5.1f}% ({}/{})".format(name,pct(copies,total),copies,total))

if __name__=="__main__": main()
