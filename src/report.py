import sqlite3,math
DB_PATH="data/paper.db"
def pct(n,d): return 100.0*n/d if d else 0.0
def percentile(values,p):
    if not values:return 0.0
    xs=sorted(float(x) for x in values); k=(len(xs)-1)*p; lo=int(math.floor(k)); hi=int(math.ceil(k)); return xs[lo] if lo==hi else xs[lo]+(xs[hi]-xs[lo])*(k-lo)
def count_slip(db,leader,where): return db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND slippage IS NOT NULL AND "+where,(leader,)).fetchone()[0]
def main():
    db=sqlite3.connect(DB_PATH); leaders=[r[0] for r in db.execute("SELECT DISTINCT leader FROM raw_fills ORDER BY leader")]; print("=== POLYMARKET PAPER REPORT v0.6 ===")
    for leader in leaders:
        latency=[r[0] for r in db.execute("SELECT latency_seconds FROM raw_fills WHERE leader=?",(leader,))]; fills=len(latency); builds=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=?",(leader,)).fetchone()[0]; sessions=db.execute("SELECT COUNT(*) FROM position_sessions WHERE leader=?",(leader,)).fetchone()[0]
        print("\n=== {} ===".format(leader)); print("fills={} builds={} sessions={}".format(fills,builds,sessions))
        if latency: print("api_latency avg={:.1f}s median={:.1f}s p90={:.1f}s".format(sum(latency)/fills,percentile(latency,.5),percentile(latency,.9)))
        priced=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND slippage IS NOT NULL",(leader,)).fetchone()[0]
        if priced:
            improved=count_slip(db,leader,"slippage<0"); over5=count_slip(db,leader,"slippage>0.05"); print("entry improved: {:.1f}% | worse >5c: {:.1f}%".format(pct(improved,priced),pct(over5,priced)))
        print("paper portfolio by strategy:")
        strategies=[r[0] for r in db.execute("SELECT DISTINCT strategy FROM paper_trades WHERE leader=? ORDER BY strategy",(leader,))]
        if not strategies: print("  no paper trades yet")
        for s in strategies:
            trades,invested=db.execute("SELECT COUNT(*),COALESCE(SUM(stake_usd),0) FROM paper_trades WHERE leader=? AND strategy=?",(leader,s)).fetchone(); settled,realized,wins=db.execute("SELECT COUNT(*),COALESCE(SUM(st.realized_pnl_usd),0),COALESCE(SUM(CASE WHEN st.realized_pnl_usd>0 THEN 1 ELSE 0 END),0) FROM paper_trades pt JOIN settlements st ON st.trade_id=pt.id WHERE pt.leader=? AND pt.strategy=?",(leader,s)).fetchone()
            unrealized=db.execute("""SELECT COALESCE(SUM(pm.pnl_usd),0) FROM paper_trades pt LEFT JOIN settlements st ON st.trade_id=pt.id LEFT JOIN paper_marks pm ON pm.id=(SELECT id FROM paper_marks WHERE trade_id=pt.id ORDER BY marked_at DESC,id DESC LIMIT 1) WHERE pt.leader=? AND pt.strategy=? AND st.trade_id IS NULL""",(leader,s)).fetchone()[0]
            total=realized+unrealized; roi=100*total/invested if invested else 0; win=100*wins/settled if settled else 0
            print("  {:16s} trades={:3d} settled={:3d} invested=${:8.2f} realized=${:8.2f} unreal=${:8.2f} total=${:8.2f} roi={:7.2f}% settled_win={:5.1f}%".format(s,trades,settled,invested,realized,unrealized,total,roi,win))
    print("\nNOTE: realized = resolved markets; unreal = latest available mark for unresolved trades.")
if __name__=="__main__": main()
