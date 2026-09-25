import json,sqlite3,time,os
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
DB='/app/data/paper.db'
def q(sql,args=()):
 c=sqlite3.connect(DB,timeout=5); c.row_factory=sqlite3.Row
 try:return [dict(x) for x in c.execute(sql,args).fetchall()]
 finally:c.close()
def payload():
 counts={r['k']:r['n'] for r in q("select 'fills' k,count(*) n from raw_fills union all select 'builds',count(*) from paper_builds union all select 'trades',count(*) from paper_trades union all select 'settled',count(*) from settlements")}
 strategies=q("select t.strategy,count(*) trades,count(s.trade_id) settled,round(coalesce(sum(s.realized_pnl_usd),0),2) pnl,round(coalesce(sum(s.realized_pnl_usd)/nullif(sum(case when s.trade_id is not null then t.stake_usd else 0 end),0)*100,0),2) roi from paper_trades t left join settlements s on s.trade_id=t.id group by t.strategy order by roi desc")
 latest=q("select datetime(t.opened_at,'unixepoch') opened,t.strategy,t.leader,t.event,t.outcome,round(t.entry_price,3) entry,t.stake_usd,case when s.trade_id is null then 'OPEN' else 'SETTLED' end status,round(s.realized_pnl_usd,2) pnl from paper_trades t left join settlements s on s.trade_id=t.id order by t.id desc limit 30")
 leaders=q("select leader,count(*) fills,round(sum(leader_usdc),0) volume,datetime(max(observed_at),'unixepoch') last_seen from raw_fills group by leader order by max(observed_at) desc")
 fwd=next((x for x in strategies if x['strategy']=='S500_SLIP1c_F2_9'),{'trades':0,'settled':0,'pnl':0,'roi':0})
 equity=q("select s.settled_at ts,round(sum(s.realized_pnl_usd) over(order by s.settled_at,s.trade_id),2) pnl from paper_trades t join settlements s on s.trade_id=t.id where t.strategy='S500_SLIP1c_F2_9' order by s.settled_at,s.trade_id")
 return {'ts':int(time.time()),'counts':counts,'forward':fwd,'strategies':strategies,'latest':latest,'leaders':leaders,'equity':equity}
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path!='/api/dashboard': self.send_response(404); self.end_headers(); return
  try:b=json.dumps(payload()).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(b)
  except Exception as e:self.send_response(500);self.end_headers();self.wfile.write(str(e).encode())
 def log_message(self,*a):pass
ThreadingHTTPServer(('0.0.0.0',8765),H).serve_forever()
