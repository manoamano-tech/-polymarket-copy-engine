import sqlite3
from pathlib import Path
SCHEMA="""
CREATE TABLE IF NOT EXISTS seen_activity (fingerprint TEXT PRIMARY KEY, seen_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS raw_fills (id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at REAL NOT NULL, trade_ts INTEGER NOT NULL, latency_seconds REAL NOT NULL, leader TEXT NOT NULL, wallet TEXT NOT NULL, transaction_hash TEXT, market TEXT NOT NULL, event TEXT, outcome TEXT, side TEXT NOT NULL, token_id TEXT NOT NULL, leader_price REAL NOT NULL, leader_usdc REAL NOT NULL);
CREATE TABLE IF NOT EXISTS paper_builds (id INTEGER PRIMARY KEY AUTOINCREMENT, decided_at REAL NOT NULL, leader TEXT NOT NULL, wallet TEXT NOT NULL, market TEXT NOT NULL, event TEXT, outcome TEXT, side TEXT NOT NULL, token_id TEXT NOT NULL, fill_count INTEGER NOT NULL, build_usdc REAL NOT NULL, leader_vwap REAL NOT NULL, build_duration_seconds REAL NOT NULL, avg_latency_seconds REAL NOT NULL, current_price REAL, slippage REAL, action TEXT NOT NULL, reason TEXT NOT NULL, simulated_size REAL NOT NULL);
CREATE TABLE IF NOT EXISTS strategy_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, build_id INTEGER NOT NULL, strategy TEXT NOT NULL, min_build_usd REAL NOT NULL, max_slippage REAL NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, simulated_size REAL NOT NULL, FOREIGN KEY(build_id) REFERENCES paper_builds(id));
CREATE TABLE IF NOT EXISTS position_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, closed_at REAL NOT NULL, leader TEXT NOT NULL, wallet TEXT NOT NULL, market TEXT NOT NULL, event TEXT, outcome TEXT, side TEXT NOT NULL, token_id TEXT NOT NULL, fill_count INTEGER NOT NULL, session_usdc REAL NOT NULL, leader_vwap REAL NOT NULL, session_duration_seconds REAL NOT NULL, current_price REAL, mark_pnl_pct REAL);
CREATE TABLE IF NOT EXISTS paper_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, opened_at REAL NOT NULL, build_id INTEGER NOT NULL, strategy TEXT NOT NULL, leader TEXT NOT NULL, wallet TEXT NOT NULL, market TEXT NOT NULL, event TEXT, outcome TEXT, side TEXT NOT NULL, token_id TEXT NOT NULL, entry_price REAL NOT NULL, stake_usd REAL NOT NULL, shares REAL NOT NULL, FOREIGN KEY(build_id) REFERENCES paper_builds(id));
CREATE TABLE IF NOT EXISTS paper_marks (id INTEGER PRIMARY KEY AUTOINCREMENT, marked_at REAL NOT NULL, trade_id INTEGER NOT NULL, mark_price REAL NOT NULL, value_usd REAL NOT NULL, pnl_usd REAL NOT NULL, pnl_pct REAL NOT NULL, FOREIGN KEY(trade_id) REFERENCES paper_trades(id));
CREATE INDEX IF NOT EXISTS idx_strategy_name ON strategy_decisions(strategy);
CREATE INDEX IF NOT EXISTS idx_build_leader ON paper_builds(leader);
CREATE INDEX IF NOT EXISTS idx_fill_leader ON raw_fills(leader);
CREATE INDEX IF NOT EXISTS idx_session_leader ON position_sessions(leader);
CREATE INDEX IF NOT EXISTS idx_paper_trade_strategy ON paper_trades(strategy);
CREATE INDEX IF NOT EXISTS idx_paper_trade_token ON paper_trades(token_id);
CREATE INDEX IF NOT EXISTS idx_paper_mark_trade ON paper_marks(trade_id);
"""
class Store:
    def __init__(self,path="data/paper.db"):
        Path(path).parent.mkdir(parents=True,exist_ok=True); self.db=sqlite3.connect(path); self.db.executescript(SCHEMA); self.db.commit()
    def seen(self,fp): return self.db.execute("SELECT 1 FROM seen_activity WHERE fingerprint=?",(fp,)).fetchone() is not None
    def mark_seen(self,fp,ts): self.db.execute("INSERT OR IGNORE INTO seen_activity VALUES (?,?)",(fp,ts)); self.db.commit()
    def insert(self,table,row):
        cols=",".join(row.keys()); qs=",".join(["?"]*len(row)); cur=self.db.execute("INSERT INTO "+table+" ("+cols+") VALUES ("+qs+")",tuple(row.values())); self.db.commit(); return cur.lastrowid
    def paper_trades_for_token(self,token_id):
        return self.db.execute("SELECT id,side,entry_price,stake_usd,shares FROM paper_trades WHERE token_id=?",(token_id,)).fetchall()
    def summary(self):
        fills=self.db.execute("SELECT COUNT(*),COALESCE(AVG(latency_seconds),0),COALESCE(MIN(latency_seconds),0),COALESCE(MAX(latency_seconds),0) FROM raw_fills").fetchone(); builds=self.db.execute("SELECT COUNT(*) FROM paper_builds").fetchone()[0]; sessions=self.db.execute("SELECT COUNT(*) FROM position_sessions").fetchone()[0]; trades=self.db.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        return {"fills":fills[0],"avg_latency":fills[1],"min_latency":fills[2],"max_latency":fills[3],"builds":builds,"sessions":sessions,"paper_trades":trades}
