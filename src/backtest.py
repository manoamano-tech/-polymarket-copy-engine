"""Conservative historical rule evaluator. PAPER/research only.
One position = leader + market + token. First eligible build wins; later builds are ignored.
Settlement is reused only by exact market+token identity.
"""
import sqlite3

def run_rule(db_path, leader=None, min_build=500, min_fills=2, max_fills=9, max_slippage=.01, stake=50):
    con=sqlite3.connect(db_path); con.row_factory=sqlite3.Row
    sql='''select b.id,b.decided_at,b.leader,b.market,b.event,b.token_id,b.outcome,b.fill_count,b.build_usdc,b.current_price,b.slippage
    from paper_builds b where b.side='BUY' and b.build_usdc>=? and b.fill_count between ? and ?
    and b.current_price is not null and b.current_price>0 and b.slippage is not null and b.slippage<=?'''
    args=[min_build,min_fills,max_fills,max_slippage]
    if leader: sql+=' and b.leader=?';args.append(leader)
    sql+=' order by b.decided_at,b.id'
    eligible=[dict(x) for x in con.execute(sql,args)]
    first={}
    for x in eligible: first.setdefault((x['leader'],x['market'],x['token_id']),x)
    positions=list(first.values())
    # Exact resolved token lookup. Settlement occurring before entry is rejected.
    sq='''select t.market,t.token_id,s.settlement_price,s.settled_at from paper_trades t join settlements s on s.trade_id=t.id
          where t.market is not null and t.token_id is not null order by s.settled_at'''
    settlements={}
    for x in con.execute(sq): settlements[(x['market'],x['token_id'])]=(x['settlement_price'],x['settled_at'])
    closed=[]
    for x in positions:
        z=settlements.get((x['market'],x['token_id']))
        if not z or z[1] < x['decided_at']: continue
        pnl=stake*(float(z[0])/float(x['current_price'])-1)
        closed.append((x,pnl))
    pnl=sum(p for _,p in closed); invested=len(closed)*stake
    return {'eligible_builds':len(eligible),'positions':len(positions),'unique_events':len({x['event'] for x in positions if x['event']}),'unique_markets':len({x['market'] for x in positions}),'settled':len(closed),'open':len(positions)-len(closed),'pnl':round(pnl,2),'roi':round(pnl/invested*100,2) if invested else 0,'winrate':round(sum(p>0 for _,p in closed)*100/len(closed),1) if closed else 0}

def event_report(db_path, leader=None, min_build=500, min_fills=2, max_fills=9, max_slippage=.01, stake=50, event_cap=None):
    """Event-aware view: positions stay distinct, but correlated exposure is aggregated/capped per event."""
    con=sqlite3.connect(db_path); con.row_factory=sqlite3.Row
    sql='''select b.* from paper_builds b where b.side='BUY' and b.build_usdc>=? and b.fill_count between ? and ? and b.current_price>0 and b.slippage is not null and b.slippage<=?'''
    args=[min_build,min_fills,max_fills,max_slippage]
    if leader: sql+=' and b.leader=?'; args.append(leader)
    sql+=' order by b.decided_at,b.id'
    first={}
    for r in con.execute(sql,args):
        x=dict(r); first.setdefault((x['leader'],x['market'],x['token_id']),x)
    sm={}
    for r in con.execute('''select t.market,t.token_id,s.settlement_price,s.settled_at from paper_trades t join settlements s on s.trade_id=t.id order by s.settled_at'''):
        sm[(r['market'],r['token_id'])]=(r['settlement_price'],r['settled_at'])
    events={}; missing=0
    for x in first.values():
        # Never merge unknown events: use market as conservative fallback correlation bucket.
        ev=x['event'] or ('market:'+x['market']); missing += int(not bool(x['event']))
        z=sm.get((x['market'],x['token_id'])); pnl=None
        if z and z[1]>=x['decided_at']: pnl=stake*(float(z[0])/float(x['current_price'])-1)
        events.setdefault(ev,[]).append((x,pnl))
    rows=[]
    for ev,ps in events.items():
        # chronological allocation; cap is total stake allowed per event
        ps.sort(key=lambda z:(z[0]['decided_at'],z[0]['id']))
        take=len(ps) if event_cap is None else min(len(ps),int(event_cap//stake))
        used=ps[:take]; closed=[p for _,p in used if p is not None]
        rows.append({'event':ev,'positions':len(ps),'taken':take,'closed':len(closed),'stake':take*stake,'pnl':sum(closed)})
    closed=sum(x['closed'] for x in rows); pnl=sum(x['pnl'] for x in rows); invested=closed*stake
    return {'events':len(rows),'missing_event_labels':missing,'positions':sum(x['positions'] for x in rows),'taken':sum(x['taken'] for x in rows),'settled':closed,'pnl':round(pnl,2),'roi':round(pnl/invested*100,2) if invested else 0,'max_positions_event':max((x['positions'] for x in rows),default=0),'top_exposure':sorted(rows,key=lambda x:x['positions'],reverse=True)[:5]}
