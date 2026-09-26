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
