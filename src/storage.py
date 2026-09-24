import sqlite3
from pathlib import Path
SCHEMA="""
CREATE TABLE IF NOT EXISTS seen_activity (fingerprint TEXT PRIMARY KEY, seen_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS raw_fills (
 id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at REAL NOT NULL, trade_ts INTEGER NOT NULL,
 latency_seconds REAL NOT NULL, leader TEXT NOT NULL, wallet TEXT NOT NULL, transaction_hash TEXT,
 market TEXT NOT NULL, event TEXT, outcome TEXT, side TEXT NOT NULL, token_id TEXT NOT NULL,
 leader_price REAL NOT NULL, leader_usdc REAL NOT NULL);
CREATE TABLE IF NOT EXISTS paper_builds (
 id INTEGER PRIMARY KEY AUTOINCREMENT, decided_at REAL NOT NULL, leader TEXT NOT NULL, wallet TEXT NOT NULL,
 market TEXT NOT NULL, event TEXT, outcome TEXT, side TEXT NOT NULL, token_id TEXT NOT NULL,
 fill_count INTEGER NOT NULL, build_usdc REAL NOT NULL, leader_vwap REAL NOT NULL,
 build_duration_seconds REAL NOT NULL, avg_latency_seconds REAL NOT NULL,
 current_price REAL, slippage REAL, action TEXT NOT NULL, reason TEXT NOT NULL, simulated_size REAL NOT NULL);
"""
class Store:
    def __init__(self,path="data/paper.db"):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.db.executescript(SCHEMA); self.db.commit()
    def seen(self,fp):
        return self.db.execute("SELECT 1 FROM seen_activity WHERE fingerprint=?",(fp,)).fetchone() is not None
    def mark_seen(self,fp,ts):
        self.db.execute("INSERT OR IGNORE INTO seen_activity VALUES (?,?)",(fp,ts)); self.db.commit()
    def insert(self,table,row):
        cols=",".join(row.keys()); qs=",".join(["?"]*len(row))
        self.db.execute("INSERT INTO "+table+" ("+cols+") VALUES ("+qs+")",tuple(row.values())); self.db.commit()
