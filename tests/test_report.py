import sqlite3
import unittest
from src.report import strategy_stats

class ReportStatsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE paper_trades(id INTEGER PRIMARY KEY, leader TEXT, strategy TEXT,
                opened_at REAL, stake_usd REAL);
            CREATE TABLE settlements(trade_id INTEGER PRIMARY KEY, settled_at REAL,
                realized_pnl_usd REAL);
            CREATE TABLE paper_marks(id INTEGER PRIMARY KEY, trade_id INTEGER,
                marked_at REAL, value_usd REAL, pnl_usd REAL);
        """)

    def trade(self, ident, pnl=None, settled_at=None, leader="A", strategy="S"):
        self.db.execute("INSERT INTO paper_trades VALUES(?,?,?,?,?)", (ident, leader, strategy, ident, 50))
        if pnl is not None:
            self.db.execute("INSERT INTO settlements VALUES(?,?,?)", (ident, ident if settled_at is None else settled_at, pnl))

    def stats(self):
        return strategy_stats(self.db, "A", "S")

    def test_empty_and_open_only(self):
        for add_open in (False, True):
            if add_open:
                self.trade(1)
            x = self.stats()
            self.assertIsNone(x["expectancy"])
            self.assertEqual(x["settled_pct"], 0)
            self.assertEqual((x["max_win_streak"], x["max_loss_streak"]), (0, 0))

    def test_pushes_break_streaks_and_count_in_expectancy(self):
        for ident, pnl in enumerate([10, 20, 0, 30, -50, -50, -50, 0, -20], 1):
            self.trade(ident, pnl)
        self.trade(10)
        self.db.execute("INSERT INTO paper_marks VALUES(1,10,1,9999,9949)")
        x = self.stats()
        self.assertEqual((x["max_win_streak"], x["max_loss_streak"]), (2, 3))
        self.assertAlmostEqual(x["expectancy"], -110 / 9)
        self.assertEqual(x["settled_pct"], 90)
        self.assertEqual(x["max_dd"], 170)
        self.assertEqual(x["realized"], -110)
        self.assertEqual(x["settled_invested"], 450)
        self.assertEqual((x["wins"], x["losses"], x["pushes"]), (3, 4, 2))

    def test_settlement_order_and_tie_break_by_trade_id(self):
        for ident, pnl, when in [(4, -10, 3), (3, 10, 2), (2, 10, 2), (1, -10, 4)]:
            self.trade(ident, pnl, when)
        x = self.stats()
        self.assertEqual((x["max_win_streak"], x["max_loss_streak"]), (2, 2))
        self.assertEqual(x["max_dd"], 20)

    def test_tied_settlements_use_id_not_insertion_order(self):
        for ident, pnl in [(3, 10), (1, 10), (2, -10)]:
            self.trade(ident, pnl, 1)
        x = self.stats()
        self.assertEqual((x["max_win_streak"], x["max_loss_streak"]), (1, 1))

    def test_leaders_and_strategies_are_isolated(self):
        self.trade(1, 10)
        self.trade(2, -100, leader="B")
        self.trade(3, -100, strategy="OTHER")
        x = self.stats()
        self.assertEqual(x["expectancy"], 10)
        self.assertEqual(x["settled_pct"], 100)
        self.assertEqual((x["max_win_streak"], x["max_loss_streak"]), (1, 0))

    def test_loss_only_and_push_tolerance(self):
        for ident, pnl in enumerate([-10, -20, 1e-10, -5, -1e-10, -5], 1):
            self.trade(ident, pnl)
        x = self.stats()
        self.assertEqual((x["max_win_streak"], x["max_loss_streak"]), (0, 2))
        self.assertEqual(x["pushes"], 2)
        self.assertAlmostEqual(x["expectancy"], -40 / 6)

if __name__ == "__main__":
    unittest.main()
