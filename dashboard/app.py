import json,sqlite3,time
from urllib.parse import urlparse,parse_qs
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
DB='/app/data/paper.db'
def q(sql,args=()):
 c=sqlite3.connect(DB,timeout=5); c.row_factory=sqlite3.Row
 try:return [dict(x) for x in c.execute(sql,args).fetchall()]
 finally:c.close()
def backtest(args):
 leader=args.get("leader") or None; min_build=max(0,float(args.get("min_build",500))); min_fills=max(1,int(args.get("min_fills",2))); max_fills=max(min_fills,int(args.get("max_fills",9))); max_slippage=float(args.get("max_slippage",.01)); stake=max(.01,float(args.get("stake",50)))
 sql="""select id,decided_at,leader,market,event,token_id,outcome,fill_count,build_usdc,current_price,slippage from paper_builds where side='BUY' and build_usdc>=? and fill_count between ? and ? and current_price>0 and slippage is not null and slippage<=?"""; a=[min_build,min_fills,max_fills,max_slippage]
 if leader: sql+=' and leader=?'; a.append(leader)
 sql+=' order by decided_at,id'; eligible=q(sql,a); first={}
 for x in eligible: first.setdefault((x['leader'],x['market'],x['token_id']),x)
 positions=list(first.values()); sm={}
 for z in q("select t.market,t.token_id,s.settlement_price,s.settled_at from paper_trades t join settlements s on s.trade_id=t.id order by s.settled_at"): sm[(z['market'],z['token_id'])]=(float(z['settlement_price']),z['settled_at'])
 closed=[]; events={}; missing=0
 for x in positions:
  ev=x['event'] or ('market:'+x['market']); missing+=int(not bool(x['event'])); z=sm.get((x['market'],x['token_id'])); pnl=None
  if z and z[1]>=x['decided_at']: pnl=stake*(z[0]/float(x['current_price'])-1); closed.append((x,pnl))
  events.setdefault(ev,[]).append(pnl)
 pnl=sum(v for _,v in closed); invested=len(closed)*stake; event_rows=[]
 for ev,vals in events.items():
  cv=[v for v in vals if v is not None]; event_rows.append({'event':ev,'positions':len(vals),'settled':len(cv),'pnl':round(sum(cv),2)})
 event_rows.sort(key=lambda x:x['positions'],reverse=True)
 return {'eligible_builds':len(eligible),'positions':len(positions),'settled':len(closed),'open':len(positions)-len(closed),'pnl':round(pnl,2),'roi':round(pnl/invested*100,2) if invested else 0,'winrate':round(100*sum(v>0 for _,v in closed)/len(closed),1) if closed else 0,'events':len(events),'missing_event_labels':missing,'max_positions_event':max((x['positions'] for x in event_rows),default=0),'top_events':event_rows[:5]}
def history_by_leader():
 rows=q("select id,decided_at,leader,market,event,token_id,outcome,current_price from paper_builds where side='BUY' and current_price>0 order by decided_at,id")
 first={}
 for x in rows: first.setdefault((x['leader'],x['market'],x['token_id']),x)
 sm={}
 for z in q("select t.market,t.token_id,s.settlement_price,s.settled_at from paper_trades t join settlements s on s.trade_id=t.id order by s.settled_at"): sm[(z['market'],z['token_id'])]=(float(z['settlement_price']),z['settled_at'])
 out={}
 for x in first.values():
  d=out.setdefault(x['leader'],{'positions':0,'settled':0,'open':0,'pnl':0.0,'wins':0}); d['positions']+=1; z=sm.get((x['market'],x['token_id']))
  if z and z[1]>=x['decided_at']:
   p=50*(z[0]/float(x['current_price'])-1); d['settled']+=1; d['pnl']+=p; d['wins']+=int(p>0)
  else: d['open']+=1
 for d in out.values(): d['pnl']=round(d['pnl'],2); d['roi']=round(d['pnl']/(d['settled']*50)*100,2) if d['settled'] else 0; d['winrate']=round(d['wins']/d['settled']*100,1) if d['settled'] else 0
 return out
def history_positions(args):
 leader=args.get('leader'); sql="select id,decided_at,leader,market,event,token_id,outcome,current_price,build_usdc,fill_count from paper_builds where side='BUY' and current_price>0"; a=[]
 if leader and leader!='all': sql+=' and leader=?'; a.append(leader)
 sql+=' order by decided_at,id'; first={}
 for x in q(sql,a): first.setdefault((x['leader'],x['market'],x['token_id']),x)
 sm={}
 for z in q("select t.market,t.token_id,s.settlement_price,s.settled_at from paper_trades t join settlements s on s.trade_id=t.id order by s.settled_at"): sm[(z['market'],z['token_id'])]=(float(z['settlement_price']),z['settled_at'])
 out=[]
 for x in first.values():
  z=sm.get((x['market'],x['token_id'])); closed=bool(z and z[1]>=x['decided_at']); p=50*(z[0]/float(x['current_price'])-1) if closed else None
  out.append({'id':x['id'],'leader':x['leader'],'event':x['event'],'outcome':x['outcome'],'opened':time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime(x['decided_at'])),'entry_price':round(float(x['current_price']),4),'build_usd':round(float(x['build_usdc']),2),'fill_count':x['fill_count'],'status':'SETTLED' if closed else 'OPEN','pnl':round(p,2) if p is not None else None})
 out.sort(key=lambda x:x['id'],reverse=True); return out[:1000]
def leader_fill_performance():
 sm={}
 for z in q("select t.market,t.token_id,s.settlement_price,s.settled_at from paper_trades t join settlements s on s.trade_id=t.id order by s.settled_at"): sm[(z['market'],z['token_id'])]=(float(z['settlement_price']),z['settled_at'])
 out={}
 rows=q("select leader,market,token_id,side,trade_ts,leader_price,leader_usdc from raw_fills order by leader,trade_ts,id")
 for x in rows:
  d=out.setdefault(x['leader'],{'buy_fills':0,'sell_fills':0,'settled_fills':0,'settled_volume':0.0,'pnl':0.0,'wins':0,'realized_sell_pnl':0.0,'settlement_pnl':0.0,'open_shares':0.0,'oversold_shares':0.0})
  price=float(x['leader_price']); usd=float(x['leader_usdc']); side=x['side']; key=(x['market'],x['token_id']); shares=usd/price if price>0 else 0
  pos=d.setdefault('_pos',{}).setdefault(key,{'shares':0.0,'cost':0.0,'last_ts':0})
  if side=='BUY':
   d['buy_fills']+=1; pos['shares']+=shares; pos['cost']+=usd; pos['last_ts']=x['trade_ts']
   z=sm.get(key)
   if z and z[1]>=x['trade_ts']:
    p=usd*(z[0]/price-1); d['settled_fills']+=1; d['settled_volume']+=usd; d['pnl']+=p; d['wins']+=int(p>0)
  elif side=='SELL':
   d['sell_fills']+=1
   close=min(shares,pos['shares'])
   if close>0:
    avg=pos['cost']/pos['shares']; rp=close*(price-avg); d['realized_sell_pnl']+=rp; pos['cost']-=close*avg; pos['shares']-=close
   if shares>close: d['oversold_shares']+=shares-close
 for leader,d in out.items():
  for key,pos in d.pop('_pos',{}).items():
   z=sm.get(key)
   if z and z[1]>=pos['last_ts'] and pos['shares']>0:
    sp=z[0]; d['settlement_pnl']+=pos['shares']*sp-pos['cost']; pos['shares']=0; pos['cost']=0
   if pos['shares']>0:
    d['open_shares']+=pos['shares']; d.setdefault('_open',[]).append((key[1],pos['shares'],pos['cost']))
  unreal=0.0; open_value=0.0; priced=0; open_count=len(d.get('_open',[]))
  for token,shares,cost in d.pop('_open',[]):
   try: mark=client.executable_price(token,'SELL')
   except Exception: mark=None
   if mark is not None:
    open_value+=shares*mark; unreal+=shares*mark-cost; priced+=1
  d['unrealized_pnl']=round(unreal,2) if priced else None; d['open_value']=round(open_value,2) if priced else None; d['open_positions']=open_count; d['priced_open_positions']=priced
  d['realized_pnl']=round(d['realized_sell_pnl']+d['settlement_pnl'],2); d['wallet_observed_pnl']=round(d['realized_pnl']+d['unrealized_pnl'],2) if d['unrealized_pnl'] is not None else d['realized_pnl']
  for k in ('pnl','settled_volume','realized_sell_pnl','settlement_pnl','open_shares','oversold_shares','realized_pnl'): d[k]=round(d[k],2)
  d['roi']=round(100*d['pnl']/d['settled_volume'],2) if d['settled_volume'] else 0; d['winrate']=round(100*d['wins']/d['settled_fills'],1) if d['settled_fills'] else 0
 return out

def payload():
 counts={r['k']:r['n'] for r in q("select 'fills' k,count(*) n from raw_fills union all select 'builds',count(*) from paper_builds union all select 'trades',count(*) from paper_trades union all select 'settled',count(*) from settlements")}
 strategies=q("select t.strategy,count(*) trades,count(s.trade_id) settled,round(coalesce(sum(s.realized_pnl_usd),0),2) pnl,round(coalesce(sum(s.realized_pnl_usd)/nullif(sum(case when s.trade_id is not null then t.stake_usd else 0 end),0)*100,0),2) roi,round(100.0*sum(case when s.realized_pnl_usd>0 then 1 else 0 end)/nullif(count(s.trade_id),0),1) winrate from paper_trades t left join settlements s on s.trade_id=t.id group by t.strategy order by roi desc")
 size_buckets=q("""select case when b.build_usdc<500 then '<$500' when b.build_usdc<1000 then '$500–999' when b.build_usdc<2000 then '$1,000–1,999' when b.build_usdc<5000 then '$2,000–4,999' when b.build_usdc<10000 then '$5,000–9,999' else '$10,000+' end bucket, case when b.build_usdc<500 then 0 when b.build_usdc<1000 then 1 when b.build_usdc<2000 then 2 when b.build_usdc<5000 then 3 when b.build_usdc<10000 then 4 else 5 end ord, count(*) trades,count(s.trade_id) settled,round(coalesce(sum(s.realized_pnl_usd),0),2) pnl,round(coalesce(sum(s.realized_pnl_usd)/nullif(sum(case when s.trade_id is not null then t.stake_usd else 0 end),0)*100,0),2) roi,round(100.0*sum(case when s.realized_pnl_usd>0 then 1 else 0 end)/nullif(count(s.trade_id),0),1) winrate from paper_trades t join paper_builds b on b.id=t.build_id left join settlements s on s.trade_id=t.id where t.strategy='S0_SLIP1c' group by bucket,ord order by ord""")
 latest=q("select datetime(t.opened_at,'unixepoch') opened,t.strategy,t.leader,t.event,t.outcome,round(b.build_usdc,2) build_usd,b.fill_count,round(b.leader_vwap,3) leader_price,round(b.current_price,3) our_price,round(100*b.slippage,2) slip,case when s.trade_id is null then 'OPEN' else 'SETTLED' end status,round(s.realized_pnl_usd,2) pnl from paper_trades t join paper_builds b on b.id=t.build_id left join settlements s on s.trade_id=t.id order by t.id desc limit 60")
 leaders=q("select leader,count(*) fills,round(sum(leader_usdc),0) volume,datetime(max(observed_at),'unixepoch') last_seen from raw_fills group by leader order by max(observed_at) desc")
 fwd=next((x for x in strategies if x['strategy']=='S500_SLIP1c_F2_9'),{'trades':0,'settled':0,'pnl':0,'roi':0,'winrate':0})
 equity=q("select s.trade_id,s.settled_at ts,datetime(s.settled_at,'unixepoch') settled,t.leader,t.market,t.event,t.outcome,round(t.entry_price,4) entry_price,round(t.stake_usd,2) stake_usd,round(s.realized_pnl_usd,2) trade_pnl,s.realized_pnl_usd trade_pnl_raw from paper_trades t join settlements s on s.trade_id=t.id where t.strategy='S500_SLIP1c_F2_9' order by s.settled_at,s.trade_id")
 running=0
 for x in equity: running+=float(x['trade_pnl_raw']); x['pnl']=round(running,2); del x['trade_pnl_raw']
 leader_stats=q("select t.leader,count(*) trades,count(s.trade_id) settled,round(coalesce(sum(s.realized_pnl_usd),0),2) pnl,round(coalesce(sum(s.realized_pnl_usd)/nullif(sum(case when s.trade_id is not null then t.stake_usd else 0 end),0)*100,0),2) roi from paper_trades t left join settlements s on s.trade_id=t.id where t.strategy='S500_SLIP1c_F2_9' group by t.leader order by trades desc")
 trader_cards=q("select r.leader,count(*) fills,count(distinct r.market) markets,round(sum(r.leader_usdc),2) volume,round(avg(r.leader_usdc),2) avg_fill,datetime(max(r.observed_at),'unixepoch') last_seen,(select count(*) from paper_builds b where b.leader=r.leader) builds,(select round(avg(b.build_usdc),2) from paper_builds b where b.leader=r.leader) avg_build from raw_fills r group by r.leader order by fills desc")
 fwdmap={x['leader']:x for x in leader_stats}; hist=history_by_leader(); perf=leader_fill_performance()
 for x in trader_cards:
  x.update(fwdmap.get(x['leader'],{'trades':0,'settled':0,'pnl':0,'roi':0})); x['history']=hist.get(x['leader'],{'positions':0,'settled':0,'open':0,'pnl':0,'roi':0,'winrate':0}); x['leader_performance']=perf.get(x['leader'],{'buy_fills':0,'settled_fills':0,'settled_volume':0,'pnl':0,'roi':0,'winrate':0})
 maxdd=0; peak=0
 for x in equity:
  peak=max(peak,x['pnl']); maxdd=max(maxdd,peak-x['pnl'])
 rn=q("select count(*) builds,round(avg(build_usdc),2) avg_build,round(avg(fill_count),1) avg_fills,datetime(max(decided_at),'unixepoch') last_seen from paper_builds where leader='RN1'")[0]
 rn.update(q("select count(*) trades,count(s.trade_id) settled,round(coalesce(sum(s.realized_pnl_usd),0),2) pnl,round(coalesce(sum(s.realized_pnl_usd)/nullif(sum(case when s.trade_id is not null then t.stake_usd else 0 end),0)*100,0),2) roi,round(100.0*sum(case when s.realized_pnl_usd>0 then 1 else 0 end)/nullif(count(s.trade_id),0),1) winrate from paper_trades t left join settlements s on s.trade_id=t.id where t.strategy='S500_SLIP1c_F2_9' and t.leader='RN1'")[0]); rn['max_drawdown']=round(maxdd,2)
 reasons=q("select d.reason,count(*) n from strategy_decisions d join paper_builds b on b.id=d.build_id where d.strategy='S500_SLIP1c_F2_9' and b.leader='RN1' and d.action='SKIP' group by d.reason order by n desc")
 trade_details=q("select t.id,t.build_id,t.leader,t.event,t.outcome,t.side,round(b.build_usdc,2) build_usd,b.fill_count,round(b.leader_vwap,4) leader_price,round(t.entry_price,4) our_price,round(t.stake_usd,2) stake_usd,CASE WHEN s.trade_id IS NULL THEN 'OPEN' ELSE 'SETTLED' END status,datetime(t.opened_at,'unixepoch') opened,round(b.slippage*100,2) slippage_pct,round(b.build_duration_seconds,1) build_seconds,round(b.avg_latency_seconds,1) latency_seconds,b.reason,round(s.realized_pnl_usd,2) pnl,datetime(s.settled_at,'unixepoch') settled from paper_trades t left join paper_builds b on b.id=t.build_id left join settlements s on s.trade_id=t.id where t.strategy='S500_SLIP1c_F2_9' order by t.id desc limit 250")
 decisions=q("select datetime(b.decided_at,'unixepoch') decided,b.leader,b.event,b.outcome,round(b.build_usdc,2) build_usd,b.fill_count,round(b.leader_vwap,3) leader_price,round(b.current_price,3) our_price,round(100*b.slippage,2) slip,d.action,d.reason from strategy_decisions d join paper_builds b on b.id=d.build_id where d.strategy='S500_SLIP1c_F2_9' order by d.id desc limit 40")
 return {'ts':int(time.time()),'counts':counts,'forward':fwd,'strategies':strategies,'size_buckets':size_buckets,'latest':latest,'leaders':leaders,'equity':equity,'decisions':decisions,'rn1':rn,'rn1_reasons':reasons,'leader_stats':leader_stats,'trader_cards':trader_cards,'trade_details':trade_details}
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  u=urlparse(self.path)
  if u.path not in ('/api/dashboard','/api/backtest','/api/history'): self.send_response(404); self.end_headers(); return
  try:
   z={k:v[-1] for k,v in parse_qs(u.query).items()}
   if u.path=='/api/dashboard': data=payload()
   elif u.path=='/api/history': data=history_positions(z)
   else:
    z['leader']=None if z.get('leader') in (None,'','all') else z.get('leader'); data=backtest(z)
   b=json.dumps(data).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
  except Exception as e:self.send_response(500);self.end_headers();self.wfile.write(str(e).encode())
 def log_message(self,*a):pass
ThreadingHTTPServer(('0.0.0.0',8765),H).serve_forever()
