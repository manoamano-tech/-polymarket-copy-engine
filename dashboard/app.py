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
def payload():
 counts={r['k']:r['n'] for r in q("select 'fills' k,count(*) n from raw_fills union all select 'builds',count(*) from paper_builds union all select 'trades',count(*) from paper_trades union all select 'settled',count(*) from settlements")}
 strategies=q("select t.strategy,count(*) trades,count(s.trade_id) settled,round(coalesce(sum(s.realized_pnl_usd),0),2) pnl,round(coalesce(sum(s.realized_pnl_usd)/nullif(sum(case when s.trade_id is not null then t.stake_usd else 0 end),0)*100,0),2) roi,round(100.0*sum(case when s.realized_pnl_usd>0 then 1 else 0 end)/nullif(count(s.trade_id),0),1) winrate from paper_trades t left join settlements s on s.trade_id=t.id group by t.strategy order by roi desc")
 latest=q("select datetime(t.opened_at,'unixepoch') opened,t.strategy,t.leader,t.event,t.outcome,round(b.build_usdc,2) build_usd,b.fill_count,round(b.leader_vwap,3) leader_price,round(b.current_price,3) our_price,round(100*b.slippage,2) slip,case when s.trade_id is null then 'OPEN' else 'SETTLED' end status,round(s.realized_pnl_usd,2) pnl from paper_trades t join paper_builds b on b.id=t.build_id left join settlements s on s.trade_id=t.id order by t.id desc limit 60")
 leaders=q("select leader,count(*) fills,round(sum(leader_usdc),0) volume,datetime(max(observed_at),'unixepoch') last_seen from raw_fills group by leader order by max(observed_at) desc")
 fwd=next((x for x in strategies if x['strategy']=='S500_SLIP1c_F2_9'),{'trades':0,'settled':0,'pnl':0,'roi':0,'winrate':0})
 equity=q("select s.trade_id,s.settled_at ts,datetime(s.settled_at,'unixepoch') settled,t.leader,t.market,t.event,t.outcome,round(t.entry_price,4) entry_price,round(t.stake_usd,2) stake_usd,round(s.realized_pnl_usd,2) trade_pnl,s.realized_pnl_usd trade_pnl_raw from paper_trades t join settlements s on s.trade_id=t.id where t.strategy='S500_SLIP1c_F2_9' order by s.settled_at,s.trade_id")
 running=0
 for x in equity: running+=float(x['trade_pnl_raw']); x['pnl']=round(running,2); del x['trade_pnl_raw']
 leader_stats=q("select t.leader,count(*) trades,count(s.trade_id) settled,round(coalesce(sum(s.realized_pnl_usd),0),2) pnl,round(coalesce(sum(s.realized_pnl_usd)/nullif(sum(case when s.trade_id is not null then t.stake_usd else 0 end),0)*100,0),2) roi from paper_trades t left join settlements s on s.trade_id=t.id where t.strategy='S500_SLIP1c_F2_9' group by t.leader order by trades desc")
 trader_cards=q("select r.leader,count(*) fills,count(distinct r.market) markets,round(sum(r.leader_usdc),2) volume,round(avg(r.leader_usdc),2) avg_fill,datetime(max(r.observed_at),'unixepoch') last_seen,(select count(*) from paper_builds b where b.leader=r.leader) builds,(select round(avg(b.build_usdc),2) from paper_builds b where b.leader=r.leader) avg_build from raw_fills r group by r.leader order by fills desc")
 fwdmap={x['leader']:x for x in leader_stats}; hist=history_by_leader()
 for x in trader_cards:
  x.update(fwdmap.get(x['leader'],{'trades':0,'settled':0,'pnl':0,'roi':0})); x['history']=hist.get(x['leader'],{'positions':0,'settled':0,'open':0,'pnl':0,'roi':0,'winrate':0})
 maxdd=0; peak=0
 for x in equity:
  peak=max(peak,x['pnl']); maxdd=max(maxdd,peak-x['pnl'])
 rn=q("select count(*) builds,round(avg(build_usdc),2) avg_build,round(avg(fill_count),1) avg_fills,datetime(max(decided_at),'unixepoch') last_seen from paper_builds where leader='RN1'")[0]
 rn.update(q("select count(*) trades,count(s.trade_id) settled,round(coalesce(sum(s.realized_pnl_usd),0),2) pnl,round(coalesce(sum(s.realized_pnl_usd)/nullif(sum(case when s.trade_id is not null then t.stake_usd else 0 end),0)*100,0),2) roi,round(100.0*sum(case when s.realized_pnl_usd>0 then 1 else 0 end)/nullif(count(s.trade_id),0),1) winrate from paper_trades t left join settlements s on s.trade_id=t.id where t.strategy='S500_SLIP1c_F2_9' and t.leader='RN1'")[0]); rn['max_drawdown']=round(maxdd,2)
 reasons=q("select d.reason,count(*) n from strategy_decisions d join paper_builds b on b.id=d.build_id where d.strategy='S500_SLIP1c_F2_9' and b.leader='RN1' and d.action='SKIP' group by d.reason order by n desc")
 trade_details=q("select t.id,t.build_id,t.leader,t.event,t.outcome,t.side,round(b.build_usdc,2) build_usd,b.fill_count,round(b.leader_vwap,4) leader_price,round(t.entry_price,4) our_price,round(t.stake_usd,2) stake_usd,CASE WHEN s.trade_id IS NULL THEN 'OPEN' ELSE 'SETTLED' END status,datetime(t.opened_at,'unixepoch') opened,round(b.slippage*100,2) slippage_pct,round(b.build_duration_seconds,1) build_seconds,round(b.avg_latency_seconds,1) latency_seconds,b.reason,round(s.realized_pnl_usd,2) pnl,datetime(s.settled_at,'unixepoch') settled from paper_trades t left join paper_builds b on b.id=t.build_id left join settlements s on s.trade_id=t.id where t.strategy='S500_SLIP1c_F2_9' order by t.id desc limit 250")
 decisions=q("select datetime(b.decided_at,'unixepoch') decided,b.leader,b.event,b.outcome,round(b.build_usdc,2) build_usd,b.fill_count,round(b.leader_vwap,3) leader_price,round(b.current_price,3) our_price,round(100*b.slippage,2) slip,d.action,d.reason from strategy_decisions d join paper_builds b on b.id=d.build_id where d.strategy='S500_SLIP1c_F2_9' order by d.id desc limit 40")
 return {'ts':int(time.time()),'counts':counts,'forward':fwd,'strategies':strategies,'latest':latest,'leaders':leaders,'equity':equity,'decisions':decisions,'rn1':rn,'rn1_reasons':reasons,'leader_stats':leader_stats,'trader_cards':trader_cards,'trade_details':trade_details}
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
