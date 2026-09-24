import sqlite3,math
DB_PATH="data/paper.db"
def pct(n,d): return 100.0*n/d if d else 0.0
def percentile(values,p):
    if not values:return 0.0
    xs=sorted(float(x) for x in values); k=(len(xs)-1)*p; lo=int(math.floor(k)); hi=int(math.ceil(k))
    return xs[lo] if lo==hi else xs[lo]+(xs[hi]-xs[lo])*(k-lo)
def count_slip(db,leader,where): return db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND slippage IS NOT NULL AND "+where,(leader,)).fetchone()[0]
def main():
    db=sqlite3.connect(DB_PATH); leaders=[r[0] for r in db.execute("SELECT DISTINCT leader FROM raw_fills ORDER BY leader")]
    print("=== POLYMARKET PAPER REPORT v0.5 ===")
    for leader in leaders:
        latency=[r[0] for r in db.execute("SELECT latency_seconds FROM raw_fills WHERE leader=?",(leader,))]; fills=len(latency)
        builds=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=?",(leader,)).fetchone()[0]; evaluated=db.execute("SELECT COUNT(DISTINCT pb.id) FROM paper_builds pb JOIN strategy_decisions sd ON sd.build_id=pb.id WHERE pb.leader=?",(leader,)).fetchone()[0]; priced=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND slippage IS NOT NULL",(leader,)).fetchone()[0]; sessions=db.execute("SELECT COUNT(*) FROM position_sessions WHERE leader=?",(leader,)).fetchone()[0]
        print("\n=== {} ===".format(leader)); print("fills={} builds={} sessions={} strategy_evaluated={} priced_builds={}".format(fills,builds,sessions,evaluated,priced))
        if latency: print("api_latency avg={:.1f}s median={:.1f}s p90={:.1f}s min={:.1f}s max={:.1f}s".format(sum(latency)/fills,percentile(latency,.5),percentile(latency,.9),min(latency),max(latency)))
        if priced:
            improved=count_slip(db,leader,"slippage<0"); over5=count_slip(db,leader,"slippage>0.05")
            print("entry improved: {:.1f}% ({}/{}) | worse >5c: {:.1f}% ({}/{})".format(pct(improved,priced),improved,priced,pct(over5,priced),over5,priced))
        print("paper portfolio by strategy (latest available mark per trade):")
        rows=db.execute("""SELECT pt.strategy,COUNT(*),COALESCE(SUM(pt.stake_usd),0),COALESCE(SUM(pm.pnl_usd),0),SUM(CASE WHEN pm.pnl_usd>0 THEN 1 ELSE 0 END),COUNT(pm.id)
        FROM paper_trades pt LEFT JOIN paper_marks pm ON pm.id=(SELECT pm2.id FROM paper_marks pm2 WHERE pm2.trade_id=pt.id ORDER BY pm2.marked_at DESC,pm2.id DESC LIMIT 1)
        WHERE pt.leader=? GROUP BY pt.strategy ORDER BY pt.strategy""",(leader,)).fetchall()
        if not rows: print("  no v0.5 paper trades yet")
        for strategy,trades,invested,pnl,wins,marked in rows:
            roi=100*pnl/invested if invested else 0; winrate=100*wins/marked if marked else 0
            print("  {:16s} trades={:3d} marked={:3d} invested=${:8.2f} mark_pnl=${:8.2f} roi={:7.2f}% win={:5.1f}%".format(strategy,trades,marked,invested,pnl,roi,winrate))
    print("\nNOTE: mark_pnl is unrealized snapshot PnL, not settlement/realized PnL.")
if __name__=="__main__": main()
