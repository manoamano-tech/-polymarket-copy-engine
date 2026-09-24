import sqlite3
import math

DB_PATH="data/paper.db"


def pct(n,d):
    return 100.0*n/d if d else 0.0


def percentile(values,p):
    if not values:
        return 0.0
    xs=sorted(float(x) for x in values)
    if len(xs)==1:
        return xs[0]
    k=(len(xs)-1)*p
    lo=int(math.floor(k)); hi=int(math.ceil(k))
    if lo==hi:
        return xs[lo]
    return xs[lo]+(xs[hi]-xs[lo])*(k-lo)


def count_slip(db,leader,where,params=()):
    q="SELECT COUNT(*) FROM paper_builds WHERE leader=? AND slippage IS NOT NULL AND "+where
    return db.execute(q,(leader,)+tuple(params)).fetchone()[0]


def main():
    db=sqlite3.connect(DB_PATH)
    leaders=[r[0] for r in db.execute("SELECT DISTINCT leader FROM raw_fills ORDER BY leader")]
    print("=== POLYMARKET PAPER REPORT v0.3 ===")
    for leader in leaders:
        latency=[r[0] for r in db.execute("SELECT latency_seconds FROM raw_fills WHERE leader=? ORDER BY latency_seconds",(leader,))]
        fills=len(latency)
        builds=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=?",(leader,)).fetchone()[0]
        evaluated=db.execute("SELECT COUNT(DISTINCT pb.id) FROM paper_builds pb JOIN strategy_decisions sd ON sd.build_id=pb.id WHERE pb.leader=?",(leader,)).fetchone()[0]
        priced=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND slippage IS NOT NULL",(leader,)).fetchone()[0]
        print("\n=== {} ===".format(leader))
        print("fills={} builds={} strategy_evaluated={} priced_builds={}".format(fills,builds,evaluated,priced))
        if latency:
            print("api_latency avg={:.1f}s median={:.1f}s p90={:.1f}s min={:.1f}s max={:.1f}s".format(sum(latency)/fills,percentile(latency,.5),percentile(latency,.9),min(latency),max(latency)))
        if not builds:
            continue

        improved=count_slip(db,leader,"slippage < 0")
        flat=count_slip(db,leader,"slippage = 0")
        worse_1=count_slip(db,leader,"slippage > 0 AND slippage <= 0.01")
        worse_2=count_slip(db,leader,"slippage > 0.01 AND slippage <= 0.02")
        worse_3=count_slip(db,leader,"slippage > 0.02 AND slippage <= 0.03")
        worse_5=count_slip(db,leader,"slippage > 0.03 AND slippage <= 0.05")
        worse_over=count_slip(db,leader,"slippage > 0.05")
        avg_improve=db.execute("SELECT COALESCE(AVG(-slippage),0) FROM paper_builds WHERE leader=? AND slippage<0",(leader,)).fetchone()[0]
        avg_worse=db.execute("SELECT COALESCE(AVG(slippage),0) FROM paper_builds WHERE leader=? AND slippage>0",(leader,)).fetchone()[0]
        print("entry quality (denominator={} priced builds):".format(priced))
        print("  improved:       {:5.1f}% ({}) avg_improvement={:.2f}c".format(pct(improved,priced),improved,avg_improve*100))
        print("  same price:     {:5.1f}% ({})".format(pct(flat,priced),flat))
        print("  worse 0-1c:     {:5.1f}% ({})".format(pct(worse_1,priced),worse_1))
        print("  worse 1-2c:     {:5.1f}% ({})".format(pct(worse_2,priced),worse_2))
        print("  worse 2-3c:     {:5.1f}% ({})".format(pct(worse_3,priced),worse_3))
        print("  worse 3-5c:     {:5.1f}% ({})".format(pct(worse_5,priced),worse_5))
        print("  worse >5c:      {:5.1f}% ({})".format(pct(worse_over,priced),worse_over))
        print("  avg worse entry: {:.2f}c".format(avg_worse*100))

        buckets=[("<$500",0,500),("$500-1k",500,1000),("$1k-2k",1000,2000),("$2k-5k",2000,5000),("$5k-10k",5000,10000),(">=$10k",10000,None)]
        print("build sizes (denominator={} all builds):".format(builds))
        for name,lo,hi in buckets:
            if hi is None:
                n=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND build_usdc>=?",(leader,lo)).fetchone()[0]
            else:
                n=db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND build_usdc>=? AND build_usdc<?",(leader,lo,hi)).fetchone()[0]
            print("  {:9s} {:5.1f}% ({})".format(name,pct(n,builds),n))

        print("strategy pass rates (denominator={} evaluated builds):".format(evaluated))
        rows=db.execute("SELECT sd.strategy,SUM(CASE WHEN sd.action='COPY' THEN 1 ELSE 0 END),COUNT(*) FROM strategy_decisions sd JOIN paper_builds pb ON pb.id=sd.build_id WHERE pb.leader=? GROUP BY sd.strategy ORDER BY sd.min_build_usd,sd.max_slippage",(leader,)).fetchall()
        for name,copies,total in rows:
            print("  {:16s} {:5.1f}% ({}/{})".format(name,pct(copies,total),copies,total))

if __name__=="__main__":
    main()
