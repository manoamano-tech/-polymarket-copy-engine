"""Copy execution policy. LIVE transport is intentionally disabled until wallet auth is connected."""
import time

def evaluate_fill(store, fill_id, leader, token_id, sport, league, leader_price, executable_price=None, min_order_size=None, profile_id=None):
    if profile_id is None:
        profiles=store.db.execute("SELECT id,leader,stake_usd,sport_filter,league_filter,max_slippage,enabled,execution_mode FROM copy_profiles WHERE enabled=1 AND leader=? AND COALESCE(source_type,'PUBLIC')='PUBLIC'",(leader,)).fetchall()
    else:
        profiles=store.db.execute("SELECT id,leader,stake_usd,sport_filter,league_filter,max_slippage,enabled,execution_mode FROM copy_profiles WHERE enabled=1 AND id=?",(profile_id,)).fetchall()
    for p in profiles:
        pid,_,stake,sf,lf,max_slip,_,mode=p
        if sf!='*' and sf!=sport: status,reason='SKIP_SPORT','sport_filter'
        elif lf!='*' and lf!=league: status,reason='SKIP_LEAGUE','league_filter'
        elif executable_price is None: status,reason='SKIP_NO_PRICE','no_executable_price'
        else:
            slip=(executable_price-leader_price)/leader_price if leader_price>0 else float('inf')
            if slip>max_slip: status,reason='SKIP_SLIPPAGE','max_slippage'
            elif min_order_size is not None and executable_price>0 and stake/executable_price < min_order_size: status,reason='SKIP_MIN_ORDER','minimum_shares'
            elif mode!='LIVE': status,reason='DRY_RUN','live_execution_disabled'
            else: status,reason='BLOCKED_NO_WALLET','wallet_not_connected'
        slip=None if executable_price is None or leader_price<=0 else (executable_price-leader_price)/leader_price
        store.db.execute("INSERT OR IGNORE INTO copy_attempts(profile_id,fill_id,decided_at,leader,token_id,sport,league,leader_price,requested_usd,executable_price,slippage,status,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(pid,fill_id,time.time(),leader,token_id,sport,league,leader_price,stake,executable_price,slip,status,reason))
    if profiles: store.db.commit()
