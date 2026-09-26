import sqlite3
from pathlib import Path
SCHEMA="""
CREATE TABLE IF NOT EXISTS seen_activity (fingerprint TEXT PRIMARY KEY, seen_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS raw_fills (id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at REAL NOT NULL, trade_ts INTEGER NOT NULL, latency_seconds REAL NOT NULL, leader TEXT NOT NULL, wallet TEXT NOT NULL, transaction_hash TEXT, market TEXT NOT NULL, event TEXT, outcome TEXT, side TEXT NOT NULL, token_id TEXT NOT NULL, leader_price REAL NOT NULL, leader_usdc REAL NOT NULL, sport TEXT, league TEXT);
CREATE TABLE IF NOT EXISTS fill_price_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, fill_id INTEGER NOT NULL, target_delay_seconds REAL NOT NULL, sampled_at REAL NOT NULL, actual_delay_seconds REAL NOT NULL, executable_price REAL, FOREIGN KEY(fill_id) REFERENCES raw_fills(id), UNIQUE(fill_id,target_delay_seconds));
CREATE TABLE IF NOT EXISTS paper_builds (id INTEGER PRIMARY KEY AUTOINCREMENT, decided_at REAL NOT NULL, leader TEXT NOT NULL, wallet TEXT NOT NULL, market TEXT NOT NULL, event TEXT, outcome TEXT, side TEXT NOT NULL, token_id TEXT NOT NULL, fill_count INTEGER NOT NULL, build_usdc REAL NOT NULL, leader_vwap REAL NOT NULL, build_duration_seconds REAL NOT NULL, avg_latency_seconds REAL NOT NULL, current_price REAL, slippage REAL, action TEXT NOT NULL, reason TEXT NOT NULL, simulated_size REAL NOT NULL);
CREATE TABLE IF NOT EXISTS strategy_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, build_id INTEGER NOT NULL, strategy TEXT NOT NULL, min_build_usd REAL NOT NULL, max_slippage REAL NOT NULL, action TEXT NOT NULL, reason TEXT NOT NULL, simulated_size REAL NOT NULL, FOREIGN KEY(build_id) REFERENCES paper_builds(id));
CREATE TABLE IF NOT EXISTS position_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, closed_at REAL NOT NULL, leader TEXT NOT NULL, wallet TEXT NOT NULL, market TEXT NOT NULL, event TEXT, outcome TEXT, side TEXT NOT NULL, token_id TEXT NOT NULL, fill_count INTEGER NOT NULL, session_usdc REAL NOT NULL, leader_vwap REAL NOT NULL, session_duration_seconds REAL NOT NULL, current_price REAL, mark_pnl_pct REAL);
CREATE TABLE IF NOT EXISTS paper_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, opened_at REAL NOT NULL, build_id INTEGER NOT NULL, strategy TEXT NOT NULL, leader TEXT NOT NULL, wallet TEXT NOT NULL, market TEXT NOT NULL, event TEXT, outcome TEXT, side TEXT NOT NULL, token_id TEXT NOT NULL, entry_price REAL NOT NULL, stake_usd REAL NOT NULL, shares REAL NOT NULL, FOREIGN KEY(build_id) REFERENCES paper_builds(id));
CREATE TABLE IF NOT EXISTS paper_marks (id INTEGER PRIMARY KEY AUTOINCREMENT, marked_at REAL NOT NULL, trade_id INTEGER NOT NULL, mark_price REAL NOT NULL, value_usd REAL NOT NULL, pnl_usd REAL NOT NULL, pnl_pct REAL NOT NULL, FOREIGN KEY(trade_id) REFERENCES paper_trades(id));
CREATE TABLE IF NOT EXISTS settlements (trade_id INTEGER PRIMARY KEY, settled_at REAL NOT NULL, settlement_price REAL NOT NULL, value_usd REAL NOT NULL, realized_pnl_usd REAL NOT NULL, realized_pnl_pct REAL NOT NULL, FOREIGN KEY(trade_id) REFERENCES paper_trades(id));
CREATE TABLE IF NOT EXISTS settlement_audit (trade_id INTEGER PRIMARY KEY, condition_id TEXT NOT NULL, token_id TEXT NOT NULL, token_outcome TEXT, winning_outcome TEXT, question TEXT, verified_at REAL NOT NULL, settlement_price REAL NOT NULL, FOREIGN KEY(trade_id) REFERENCES paper_trades(id));
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS user_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, token_hash TEXT NOT NULL UNIQUE, created_at REAL NOT NULL, expires_at REAL NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS copy_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, leader TEXT NOT NULL, stake_usd REAL NOT NULL DEFAULT 1.0, sport_filter TEXT NOT NULL DEFAULT '*', league_filter TEXT NOT NULL DEFAULT '*', max_slippage REAL NOT NULL DEFAULT 0.03, enabled INTEGER NOT NULL DEFAULT 0, execution_mode TEXT NOT NULL DEFAULT 'DRY_RUN', created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS copy_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER NOT NULL, fill_id INTEGER NOT NULL, decided_at REAL NOT NULL, leader TEXT NOT NULL, token_id TEXT NOT NULL, sport TEXT, league TEXT, leader_price REAL NOT NULL, requested_usd REAL NOT NULL, executable_price REAL, slippage REAL, status TEXT NOT NULL, reason TEXT, order_id TEXT, filled_usd REAL, fill_price REAL, FOREIGN KEY(profile_id) REFERENCES copy_profiles(id), FOREIGN KEY(fill_id) REFERENCES raw_fills(id), UNIQUE(profile_id,fill_id));
CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_snapshot_fill ON fill_price_snapshots(fill_id); CREATE INDEX IF NOT EXISTS idx_strategy_name ON strategy_decisions(strategy); CREATE INDEX IF NOT EXISTS idx_build_leader ON paper_builds(leader); CREATE INDEX IF NOT EXISTS idx_fill_leader ON raw_fills(leader); CREATE INDEX IF NOT EXISTS idx_session_leader ON position_sessions(leader); CREATE INDEX IF NOT EXISTS idx_paper_trade_strategy ON paper_trades(strategy); CREATE INDEX IF NOT EXISTS idx_paper_trade_token ON paper_trades(token_id); CREATE INDEX IF NOT EXISTS idx_paper_mark_trade ON paper_marks(trade_id);
"""
class Store:
    def __init__(self,path="data/paper.db"):
        Path(path).parent.mkdir(parents=True,exist_ok=True); self.db=sqlite3.connect(path); self.db.executescript(SCHEMA); self._migrate(); self.db.commit()
    def _ensure_column(self,table,column,decl):
        cols={r[1] for r in self.db.execute("PRAGMA table_info("+table+")")}
        if column not in cols: self.db.execute("ALTER TABLE "+table+" ADD COLUMN "+column+" "+decl)
    def _migrate(self):
        self._ensure_column("raw_fills","sport","TEXT"); self._ensure_column("raw_fills","league","TEXT"); self._ensure_column("copy_profiles","user_id","INTEGER")
        name="reset_legacy_settlements_v061"
        if not self.db.execute("SELECT 1 FROM schema_migrations WHERE name=?",(name,)).fetchone():
            old=self.db.execute("SELECT COUNT(*) FROM settlements").fetchone()[0]; self.db.execute("DELETE FROM settlements"); self.db.execute("DELETE FROM settlement_audit"); self.db.execute("INSERT INTO schema_migrations(name,applied_at) VALUES(?,strftime('%s','now'))",(name,)); print("[MIGRATION] cleared {} legacy unverified settlements for safe recalculation".format(old),flush=True)
    def seen(self,fp): return self.db.execute("SELECT 1 FROM seen_activity WHERE fingerprint=?",(fp,)).fetchone() is not None
    def mark_seen(self,fp,ts): self.db.execute("INSERT OR IGNORE INTO seen_activity VALUES (?,?)",(fp,ts)); self.db.commit()
    def insert(self,table,row):
        cols=",".join(row.keys()); qs=",".join(["?"]*len(row)); cur=self.db.execute("INSERT INTO "+table+" ("+cols+") VALUES ("+qs+")",tuple(row.values())); self.db.commit(); return cur.lastrowid
    def paper_trades_for_token(self,token_id): return self.db.execute("SELECT id,side,entry_price,stake_usd,shares FROM paper_trades WHERE token_id=?",(token_id,)).fetchall()
    def unsettled_markets(self):
        # Prefer the event slug stored on the paper trade. Legacy v0.6/v0.7 rows may
        # have an empty event even though the original raw fill has the official slug.
        # Recover only by exact market+token match; never guess a slug.
        return self.db.execute("""
            SELECT pt.market, pt.token_id,
                   CASE WHEN MAX(COALESCE(pt.event,''))<>''
                        THEN MAX(COALESCE(pt.event,''))
                        ELSE COALESCE((SELECT rf.event FROM raw_fills rf
                                       WHERE rf.market=pt.market AND rf.token_id=pt.token_id
                                         AND COALESCE(rf.event,'')<>''
                                       ORDER BY rf.id DESC LIMIT 1),'') END AS event_slug,
                   CASE WHEN MAX(COALESCE(pt.event,''))='' AND EXISTS
                             (SELECT 1 FROM raw_fills rf WHERE rf.market=pt.market
                              AND rf.token_id=pt.token_id AND COALESCE(rf.event,'')<>'')
                        THEN 1 ELSE 0 END AS legacy_event_recovered
            FROM paper_trades pt LEFT JOIN settlements s ON s.trade_id=pt.id
            WHERE s.trade_id IS NULL GROUP BY pt.market,pt.token_id
        """).fetchall()
    def unsettled_trades_for_token(self,token_id): return self.db.execute("SELECT pt.id,pt.side,pt.entry_price,pt.stake_usd,pt.shares FROM paper_trades pt LEFT JOIN settlements s ON s.trade_id=pt.id WHERE pt.token_id=? AND s.trade_id IS NULL",(token_id,)).fetchall()
    def settle_trade_verified(self,trade_id,ts,price,value,pnl,pct,condition_id,token_id,token_outcome,winning_outcome,question):
        self.db.execute("INSERT OR IGNORE INTO settlements(trade_id,settled_at,settlement_price,value_usd,realized_pnl_usd,realized_pnl_pct) VALUES(?,?,?,?,?,?)",(trade_id,ts,price,value,pnl,pct)); self.db.execute("INSERT OR REPLACE INTO settlement_audit(trade_id,condition_id,token_id,token_outcome,winning_outcome,question,verified_at,settlement_price) VALUES(?,?,?,?,?,?,?,?)",(trade_id,condition_id,token_id,token_outcome,winning_outcome,question,ts,price)); self.db.commit()
    def summary(self):
        fills=self.db.execute("SELECT COUNT(*),COALESCE(AVG(latency_seconds),0),COALESCE(MIN(latency_seconds),0),COALESCE(MAX(latency_seconds),0) FROM raw_fills").fetchone(); builds=self.db.execute("SELECT COUNT(*) FROM paper_builds").fetchone()[0]; sessions=self.db.execute("SELECT COUNT(*) FROM position_sessions").fetchone()[0]; trades=self.db.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]; settled=self.db.execute("SELECT COUNT(*) FROM settlements").fetchone()[0]
        return {"fills":fills[0],"avg_latency":fills[1],"min_latency":fills[2],"max_latency":fills[3],"builds":builds,"sessions":sessions,"paper_trades":trades,"settled":settled}
