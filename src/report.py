import sqlite3, math
from collections import defaultdict

DB_PATH = "data/paper.db"


def pct(n, d):
    return 100.0 * n / d if d else 0.0


def percentile(values, p):
    if not values:
        return 0.0
    xs = sorted(float(x) for x in values)
    k = (len(xs) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return xs[lo] if lo == hi else xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def count_slip(db, leader, where):
    return db.execute(
        "SELECT COUNT(*) FROM paper_builds WHERE leader=? AND slippage IS NOT NULL AND " + where,
        (leader,),
    ).fetchone()[0]


def latest_open_marks(db, leader, strategy):
    return db.execute("""
        SELECT pt.stake_usd, pm.value_usd, pm.pnl_usd
        FROM paper_trades pt
        LEFT JOIN settlements st ON st.trade_id=pt.id
        LEFT JOIN paper_marks pm ON pm.id=(
            SELECT id FROM paper_marks
            WHERE trade_id=pt.id
            ORDER BY marked_at DESC,id DESC LIMIT 1
        )
        WHERE pt.leader=? AND pt.strategy=? AND st.trade_id IS NULL
    """, (leader, strategy)).fetchall()


def strategy_stats(db, leader, strategy):
    trades, invested = db.execute(
        "SELECT COUNT(*),COALESCE(SUM(stake_usd),0) FROM paper_trades WHERE leader=? AND strategy=?",
        (leader, strategy),
    ).fetchone()

    settled_rows = db.execute("""
        SELECT pt.id,pt.opened_at,pt.stake_usd,st.settled_at,st.realized_pnl_usd
        FROM paper_trades pt
        JOIN settlements st ON st.trade_id=pt.id
        WHERE pt.leader=? AND pt.strategy=?
        ORDER BY st.settled_at,pt.id
    """, (leader, strategy)).fetchall()

    settled = len(settled_rows)
    open_count = trades - settled
    settled_invested = sum(float(r[2]) for r in settled_rows)
    realized = sum(float(r[4]) for r in settled_rows)
    wins = [float(r[4]) for r in settled_rows if float(r[4]) > 1e-9]
    losses = [float(r[4]) for r in settled_rows if float(r[4]) < -1e-9]
    pushes = settled - len(wins) - len(losses)
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    settled_roi = pct(realized, settled_invested)

    open_rows = latest_open_marks(db, leader, strategy)
    open_exposure = sum(float(r[0] or 0) for r in open_rows)
    marked_open = sum(1 for r in open_rows if r[1] is not None)
    unrealized = sum(float(r[2] or 0) for r in open_rows if r[2] is not None)

    # Closed-trade equity curve. Since every paper trade is independently funded,
    # drawdown is measured from cumulative realized-PnL peaks, starting at $0.
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    max_dd_pct_of_settled_capital = 0.0
    capital_seen = 0.0
    equity_points = []
    for trade_id, opened_at, stake, settled_at, pnl in settled_rows:
        capital_seen += float(stake)
        equity += float(pnl)
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)
        if capital_seen > 0:
            max_dd_pct_of_settled_capital = max(max_dd_pct_of_settled_capital, 100.0 * dd / capital_seen)
        equity_points.append((settled_at, equity))

    return {
        "trades": trades, "invested": invested, "settled": settled, "open": open_count,
        "settled_invested": settled_invested, "realized": realized,
        "wins": len(wins), "losses": len(losses), "pushes": pushes,
        "win_rate": pct(len(wins), len(wins) + len(losses)),
        "avg_win": gross_profit / len(wins) if wins else 0.0,
        "avg_loss": (-gross_loss / len(losses)) if losses else 0.0,
        "profit_factor": profit_factor, "settled_roi": settled_roi,
        "open_exposure": open_exposure, "marked_open": marked_open,
        "unrealized": unrealized, "max_dd": max_dd,
        "max_dd_pct": max_dd_pct_of_settled_capital,
        "equity": equity, "equity_points": equity_points,
    }


def pf_text(x):
    return "inf" if math.isinf(x) else "{:.2f}".format(x)


def main():
    db = sqlite3.connect(DB_PATH)
    leaders = [r[0] for r in db.execute("SELECT DISTINCT leader FROM raw_fills ORDER BY leader")]
    print("=== POLYMARKET PAPER REPORT v0.7 ===")
    print("Closed performance is separated from open mark-to-market. Rankings are not implied.")

    for leader in leaders:
        latency = [r[0] for r in db.execute("SELECT latency_seconds FROM raw_fills WHERE leader=?", (leader,))]
        fills = len(latency)
        builds = db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=?", (leader,)).fetchone()[0]
        sessions = db.execute("SELECT COUNT(*) FROM position_sessions WHERE leader=?", (leader,)).fetchone()[0]
        print("\n=== {} ===".format(leader))
        print("fills={} builds={} sessions={}".format(fills, builds, sessions))
        if latency:
            print("api_latency avg={:.1f}s median={:.1f}s p90={:.1f}s".format(
                sum(latency) / fills, percentile(latency, .5), percentile(latency, .9)))
        priced = db.execute("SELECT COUNT(*) FROM paper_builds WHERE leader=? AND slippage IS NOT NULL", (leader,)).fetchone()[0]
        if priced:
            improved = count_slip(db, leader, "slippage<0")
            over5 = count_slip(db, leader, "slippage>0.05")
            print("entry improved: {:.1f}% | worse >5c: {:.1f}%".format(pct(improved, priced), pct(over5, priced)))

        strategies = [r[0] for r in db.execute(
            "SELECT DISTINCT strategy FROM paper_trades WHERE leader=? ORDER BY strategy", (leader,))]
        if not strategies:
            print("no paper trades yet")
            continue

        print("\nCLOSED / SETTLED PERFORMANCE:")
        print("  {:16s} {:>6s} {:>7s} {:>9s} {:>9s} {:>8s} {:>9s} {:>9s} {:>7s} {:>9s}".format(
            "strategy", "settld", "W-L-P", "realized", "ROI", "win%", "avg_win", "avg_loss", "PF", "max_DD"))
        stats = {}
        for s in strategies:
            x = strategy_stats(db, leader, s)
            stats[s] = x
            wlp = "{}-{}-{}".format(x["wins"], x["losses"], x["pushes"])
            print("  {:16s} {:6d} {:>7s} ${:8.2f} {:8.2f}% {:7.1f}% ${:8.2f} ${:8.2f} {:>7s} ${:8.2f}".format(
                s, x["settled"], wlp, x["realized"], x["settled_roi"], x["win_rate"],
                x["avg_win"], x["avg_loss"], pf_text(x["profit_factor"]), x["max_dd"]))

        print("\nOPEN EXPOSURE (NOT INCLUDED IN CLOSED ROI):")
        print("  {:16s} {:>6s} {:>7s} {:>11s} {:>11s}".format(
            "strategy", "open", "marked", "exposure", "unreal_PnL"))
        for s in strategies:
            x = stats[s]
            print("  {:16s} {:6d} {:7d} ${:10.2f} ${:10.2f}".format(
                s, x["open"], x["marked_open"], x["open_exposure"], x["unrealized"]))

        print("\nSAMPLE / RISK DETAILS:")
        for s in strategies:
            x = stats[s]
            print("  {:16s} trades={:4d} settled_cap=${:8.2f} closed_equity=${:8.2f} maxDD=${:8.2f} maxDD/settled_cap={:6.2f}%".format(
                s, x["trades"], x["settled_invested"], x["equity"], x["max_dd"], x["max_dd_pct"]))

    print("\nNOTES:")
    print("  settled ROI = realized PnL / stake of settled trades only.")
    print("  open exposure and unrealized PnL are shown separately and never mixed into settled ROI.")
    print("  PF = gross settled profits / absolute gross settled losses.")
    print("  max_DD = maximum peak-to-trough drawdown of cumulative realized PnL in settlement order.")
    print("  maxDD/settled_cap is a diagnostic ratio, not an account-level drawdown percentage.")


if __name__ == "__main__":
    main()
