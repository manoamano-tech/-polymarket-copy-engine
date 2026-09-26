import json,sqlite3,time,hashlib,secrets,re,hmac
from urllib.parse import urlparse,parse_qs
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
DB='/app/data/paper.db'
def q(sql,args=()):
 c=sqlite3.connect(DB,timeout=5); c.row_factory=sqlite3.Row
 try:return [dict(x) for x in c.execute(sql,args).fetchall()]
 finally:c.close()
def backtest(args):
 leader=args.get("leader") or None; min_build=max(0,float(args.get("min_build",500))); max_build=float(args.get("max_build",0) or 0); min_fills=max(1,int(args.get("min_fills",2))); max_fills=max(min_fills,int(args.get("max_fills") or 1000000000)); max_slippage=float(args.get("max_slippage",.01)); stake=max(.01,float(args.get("stake",50)))
 sql="""select id,decided_at,leader,market,event,token_id,outcome,fill_count,build_usdc,current_price,slippage from paper_builds where side='BUY' and build_usdc>=? and fill_count between ? and ? and current_price>0 and slippage is not null and slippage<=?"""; a=[min_build,min_fills,max_fills,max_slippage]
 if max_build>0: sql+=' and build_usdc<=?'; a.append(max_build)
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


def size_research():
 # Diagnostic only: fixed non-overlapping size buckets. Chronological halves test stability without tuning cutoffs.
 buckets=[(0,500,'<$500'),(500,1000,'$500–999'),(1000,2000,'$1,000–1,999'),(2000,5000,'$2,000–4,999'),(5000,10000,'$5,000–9,999'),(10000,None,'$10,000+')]
 sm={}
 for z in q("select t.market,t.token_id,s.settlement_price,s.settled_at from paper_trades t join settlements s on s.trade_id=t.id order by s.settled_at"): sm[(z['market'],z['token_id'])]=(float(z['settlement_price']),z['settled_at'])
 out=[]
 for lo,hi,label in buckets:
  sql="select id,decided_at,leader,market,event,token_id,current_price,build_usdc from paper_builds where side='BUY' and build_usdc>=? and current_price>0 and slippage is not null and slippage<=.01"; a=[lo]
  if hi is not None: sql+=' and build_usdc<?'; a.append(hi)
  sql+=' order by decided_at,id'; first={}
  for x in q(sql,a): first.setdefault((x['leader'],x['market'],x['token_id']),x)
  closed=[]
  for x in first.values():
   z=sm.get((x['market'],x['token_id']))
   if z and z[1]>=x['decided_at']: closed.append((x,50*(z[0]/float(x['current_price'])-1)))
  closed.sort(key=lambda t:(t[0]['decided_at'],t[0]['id']))
  def stats(rows):
   vals=[v for _,v in rows]; pnl=sum(vals); inv=len(vals)*50
   return {'n':len(vals),'pnl':round(pnl,2),'roi':round(100*pnl/inv,2) if inv else 0,'winrate':round(100*sum(v>0 for v in vals)/len(vals),1) if vals else 0}
  mid=len(closed)//2; h1=stats(closed[:mid]); h2=stats(closed[mid:])
  vals=[v for _,v in closed]; pnl=sum(vals); invested=len(vals)*50; events={x['event'] or ('market:'+x['market']) for x,_ in closed}
  out.append({'label':label,'positions':len(first),'settled':len(vals),'events':len(events),'pnl':round(pnl,2),'roi':round(100*pnl/invested,2) if invested else 0,'winrate':round(100*sum(v>0 for v in vals)/len(vals),1) if vals else 0,'first_half':h1,'second_half':h2})
 return out

def classify_sport(event,question=''):
 e=(event or '').lower(); q=(question or '').lower(); p=e.split('-')[0] if e else ''
 if p=='atp': return ('Tennis','ATP')
 if p=='wta': return ('Tennis','WTA')
 if p=='cs2' or q.startswith('counter-strike:'): return ('Esports','CS2')
 if p in ('lol','league'): return ('Esports','LoL')
 if p in ('dota','dota2'): return ('Esports','Dota 2')
 if p=='nfl': return ('American football','NFL')
 if p=='cfb': return ('American football','CFB')
 if p in ('nba','wnba'): return ('Basketball',p.upper())
 if p=='mlb': return ('Baseball','MLB')
 if p=='nhl': return ('Hockey','NHL')
 # UNL is UEFA Nations League; WSL/ENL are football competition slugs.
 if p=='unl': return ('Football','UEFA Nations League')
 if p=='wsl': return ('Football','WSL')
 if p=='enl': return ('Football','ENL')
 if p in ('fif','mex','col1','bra2','clf','chi2','es2','ned2','mar1','canpl','el1'): return ('Football',p.upper())
 # For legacy fills with an empty event slug, use only explicit wording in
 # verified Polymarket settlement questions. Do not infer from outcome names.
 tennis_tours={
  'chengdu open':'ATP','hangzhou open':'ATP','san diego 2':'ATP',
  'singapore open':'WTA','korea open':'WTA','porto':'WTA',
  'tolentino':'Tennis / ITF','ankara':'Tennis / ITF',
  'buenos aires 2':'Tennis / Challenger','st. tropez':'Tennis / Challenger',
  'plovdiv 4':'Tennis / ITF'}
 for name,tour in tennis_tours.items():
  if q.startswith(name+':'): return ('Tennis',tour)
 # Explicit American-football matchups / spread markets seen in verified metadata.
 football_teams=('falcons','packers','army','temple','clemson','california','liberty','coastal carolina','navy','uab','northwestern','indiana')
 if any(t in q for t in football_teams) and (' vs. ' in q or q.startswith('spread:')):
  return ('American football','Other / legacy')
 # Explicit basketball matchup in verified metadata.
 if q.startswith('golden state valkyries vs. los angeles sparks') or q.startswith('toronto tempo vs. connecticut sun'):
  return ('Basketball','WNBA')
 # CS2 derivative markets whose question explicitly identifies map terminology.
 if q.startswith('map handicap:'): return ('Esports','CS2')
 # Explicit football wording in verified questions. Exact score, draw, BTTS and
 # soccer spreads are grouped as football only when the question itself says so.
 if q.startswith('will ') or (' vs. ' in q and any(x in q for x in ('o/u','exact score','end in a draw','both teams to score','draw at halftime','leading at halftime'))):
  return ('Football','Other football')
 if q.startswith('exact score:'): return ('Football','Other football')
 return ('Other','Unclassified')

def fill_copy_dashboard():
 # All observed BUY fills, proportional sizing. Settlement-backed results only; no deduplication.
 sm={}
 for z in q("select t.market,t.token_id,s.settlement_price,s.settled_at from paper_trades t join settlements s on s.trade_id=t.id order by s.settled_at"): sm[(z['market'],z['token_id'])]=(float(z['settlement_price']),z['settled_at'])
 snaps={x['fill_id']:float(x['executable_price']) for x in q("select fill_id,executable_price from fill_price_snapshots where target_delay_seconds=0 and executable_price is not null")}
 questions={(x['condition_id'].lower(),x['token_id']):x['question'] for x in q("select condition_id,token_id,max(question) question from settlement_audit group by condition_id,token_id")}
 rows=q("select id,leader,observed_at,trade_ts,event,outcome,market,token_id,leader_price,leader_usdc,sport,league from raw_fills where side='BUY' order by trade_ts,id")
 leaders={}
 for x in rows:
  L=x['leader']; ld=leaders.setdefault(L,{'leader':L,'last_seen_ts':0,'market_keys':set(),'fills':0,'settled_fills':0,'open_fills':0,'leader_volume':0.0,'copied':0.0,'pnl':0.0,'wins':0,'sports':{},'equity':[],'running':0.0,'exec3':{'fills':0,'settled':0,'copied':0.0,'pnl':0.0}})
  question=questions.get((x['market'].lower(),x['token_id']),'') if not x['event'] else ''
  sport=x['sport'] or classify_sport(x['event'],question)[0]; league=x['league'] or classify_sport(x['event'],question)[1]; d=ld['sports'].setdefault((sport,league),{'sport':sport,'league':league,'fills':0,'closed':0,'leader_volume':0.0,'copied':0.0,'pnl':0.0,'wins':0})
  usd=float(x['leader_usdc']); lp=float(x['leader_price']); ld['last_seen_ts']=max(ld['last_seen_ts'],x['trade_ts']); ld['market_keys'].add(x['market']); ld['fills']+=1;ld['leader_volume']+=usd;d['fills']+=1;d['leader_volume']+=usd
  z=sm.get((x['market'],x['token_id']))
  if z and z[1]>=x['observed_at'] and lp>0:
   stake=.01*usd;pnl=stake*(z[0]/lp-1);ld['settled_fills']+=1;ld['copied']+=stake;ld['pnl']+=pnl;ld['wins']+=int(pnl>0);d['closed']+=1;d['copied']+=stake;d['pnl']+=pnl;d['wins']+=int(pnl>0);ld['running']+=pnl;ld['equity'].append({'ts':x['trade_ts'],'pnl':round(ld['running'],2),'trade_pnl':round(pnl,2),'event':x['event'],'sport':sport,'league':league})
  else: ld['open_fills']+=1
  ep=snaps.get(x['id'])
  if ep is not None and lp>0 and (ep-lp)/lp<=.03:
   ld['exec3']['fills']+=1
   if z and z[1]>=x['observed_at'] and ep>0:
    stake=.01*usd;pnl=stake*(z[0]/ep-1);ld['exec3']['settled']+=1;ld['exec3']['copied']+=stake;ld['exec3']['pnl']+=pnl
 def finish(d):
  for k in ('leader_volume','copied','pnl'): d[k]=round(d.get(k,0),2)
  d['roi']=round(100*d['pnl']/d['copied'],2) if d.get('copied') else 0
  if 'wins' in d:d['winrate']=round(100*d['wins']/d['settled_fills'],1) if d.get('settled_fills') else 0
 for ld in leaders.values():
  finish(ld); ex=ld['exec3'];ex['copied']=round(ex['copied'],2);ex['pnl']=round(ex['pnl'],2);ex['roi']=round(100*ex['pnl']/ex['copied'],2) if ex['copied'] else 0
  ss=[]
  for d in ld['sports'].values():
   d['leader_volume']=round(d['leader_volume'],2);d['copied']=round(d['copied'],2);d['pnl']=round(d['pnl'],2);d['roi']=round(100*d['pnl']/d['copied'],2) if d['copied'] else 0;d['winrate']=round(100*d['wins']/d['closed'],1) if d['closed'] else 0;ss.append(d)
  ss.sort(key=lambda x:(x['sport'],x['league']));ld['sports']=ss;ld.pop('running',None)
  # Keep the dashboard light while retaining chart extrema.
  eq=ld['equity']; max_points=900
  if len(eq)>max_points:
   # Downsample by buckets but preserve local extrema so drawdowns/spikes are not hidden.
   keep={0,len(eq)-1}; buckets=max_points//3; step=(len(eq)-1)/buckets
   for b in range(buckets):
    lo=int(b*step); hi=min(len(eq),max(lo+1,int((b+1)*step)+1)); chunk=range(lo,hi)
    keep.add(lo);keep.add(min(chunk,key=lambda i:eq[i]['pnl']));keep.add(max(chunk,key=lambda i:eq[i]['pnl']))
   ld['equity']=[eq[i] for i in sorted(keep)]
  ld['markets']=len(ld.pop('market_keys'))
 return {'leaders':sorted(leaders.values(),key=lambda x:-x['fills']),'scale_pct':1,'slippage_limit_pct':3}

def observed_positions(leader=None,status='all',limit=500):
 sm={(x['market'],x['token_id']):(float(x['settlement_price']),x['settled_at']) for x in q("select t.market,t.token_id,s.settlement_price,s.settled_at from paper_trades t join settlements s on s.trade_id=t.id order by s.settled_at")}
 sql="select id,leader,observed_at,trade_ts,event,outcome,market,token_id,leader_price,leader_usdc from raw_fills where side='BUY'"; args=[]
 if leader and leader!='all': sql+=' and leader=?'; args.append(leader)
 sql+=' order by trade_ts,id'; rows=q(sql,args); pos={}
 for x in rows:
  k=(x['leader'],x['market'],x['token_id']); d=pos.setdefault(k,{'id':x['id'],'leader':x['leader'],'event':x['event'],'outcome':x['outcome'],'market':x['market'],'token_id':x['token_id'],'opened_ts':x['trade_ts'],'last_ts':x['trade_ts'],'fill_count':0,'leader_usd':0.0,'shares':0.0})
  usd=float(x['leader_usdc']); price=float(x['leader_price']); d['fill_count']+=1;d['leader_usd']+=usd;d['shares']+=usd/price if price>0 else 0;d['last_ts']=max(d['last_ts'],x['trade_ts']);d['id']=x['id'];d['event']=x['event'] or d['event'];d['outcome']=x['outcome'] or d['outcome']
 out=[]
 for d in pos.values():
  z=sm.get((d['market'],d['token_id'])); closed=bool(z and z[1]>=d['opened_ts']); st='SETTLED' if closed else 'OPEN'
  if status!='all' and st!=status: continue
  avg=d['leader_usd']/d['shares'] if d['shares'] else 0; pnl=(d['shares']*z[0]-d['leader_usd']) if closed else None
  out.append({**d,'leader_usd':round(d['leader_usd'],2),'avg_price':round(avg,4),'status':st,'pnl':round(pnl,2) if pnl is not None else None,'opened':time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime(d['opened_ts']))})
 out.sort(key=lambda x:x['last_ts'],reverse=True); return out[:max(1,min(int(limit),1000))]

def payload():
 fc=fill_copy_dashboard(); cards=[]
 for x in fc['leaders']:
  cards.append({'leader':x['leader'],'fills':x['fills'],'markets':0,'volume':x['leader_volume'],'avg_fill':round(x['leader_volume']/x['fills'],2) if x['fills'] else 0,'last_seen':time.strftime('%Y-%m-%d %H:%M:%S',time.gmtime(x['last_seen_ts'])),'trades':0,'settled':0,'pnl':x['pnl'],'roi':x['roi'],'history':{},'leader_performance':{'buy_fills':x['fills'],'sell_fills':0,'settled_fills':x['settled_fills'],'settled_volume':x['copied']*100,'pnl':x['pnl']*100,'wallet_observed_pnl':x['pnl']*100,'realized_pnl':x['pnl']*100,'unrealized_pnl':None,'open_positions':x['open_fills'],'priced_open_positions':0,'open_value':None,'roi':x['roi']}})
 return {'ts':int(time.time()),'trader_cards':cards,'equity':[],'fill_copy':fc}
def db_exec(sql,args=()):
 c=sqlite3.connect(DB,timeout=5)
 try:
  cur=c.execute(sql,args); c.commit(); return cur.lastrowid
 finally:c.close()
def auth_schema():
 c=sqlite3.connect(DB,timeout=5)
 try:
  c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT NOT NULL UNIQUE COLLATE NOCASE,password_hash TEXT NOT NULL,created_at REAL NOT NULL)")
  c.execute("CREATE TABLE IF NOT EXISTS user_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,token_hash TEXT NOT NULL UNIQUE,created_at REAL NOT NULL,expires_at REAL NOT NULL)")
  cols={r[1] for r in c.execute('pragma table_info(copy_profiles)')}
  if 'user_id' not in cols:c.execute('alter table copy_profiles add column user_id INTEGER')
  c.commit()
 finally:c.close()
def hash_password(password,salt=None):
 salt=salt or secrets.token_bytes(16); dk=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,310000)
 return salt.hex()+'$'+dk.hex()
def verify_password(password,stored):
 try:
  sh,dh=stored.split('$',1); return hmac.compare_digest(hash_password(password,bytes.fromhex(sh)).split('$')[1],dh)
 except:return False
def token_hash(t):return hashlib.sha256(t.encode()).hexdigest()
def current_user(cookie):
 token=''
 for part in (cookie or '').split(';'):
  if part.strip().startswith('ce_session='):token=part.strip().split('=',1)[1]
 if not token:return None
 rows=q("select u.id,u.email from user_sessions s join users u on u.id=s.user_id where s.token_hash=? and s.expires_at>?",(token_hash(token),time.time()))
 return rows[0] if rows else None
def account_payload(uid):
 profiles=q("select id,name,leader,stake_usd,sport_filter,league_filter,max_slippage,enabled,execution_mode,created_at,updated_at from copy_profiles where user_id=? order by id",(uid,))
 attempts=[]
 if profiles:
  ids=[x['id'] for x in profiles]; marks=','.join('?'*len(ids)); attempts=q("select id,profile_id,fill_id,decided_at,leader,sport,league,leader_price,requested_usd,executable_price,slippage,status,reason,filled_usd,fill_price from copy_attempts where profile_id in ("+marks+") order by id desc limit 100",ids)
 leaders=[x['leader'] for x in q("select leader,count(*) n from raw_fills group by leader order by n desc")]
 sports=[x['sport'] for x in q("select sport,count(*) n from raw_fills where sport is not null and sport!='' group by sport order by n desc")]
 leagues=[x['league'] for x in q("select league,count(*) n from raw_fills where league is not null and league!='' group by league order by n desc")]
 stats={'signals':len(attempts),'passed':0,'skipped':0,'settled':0,'invested':0.0,'pnl':0.0,'roi':None}
 for a in attempts:
  if a['status'] in ('DRY_RUN','FILLED','LIVE_FILLED'):stats['passed']+=1
  elif str(a['status']).startswith('SKIP'):stats['skipped']+=1
 # DRY-run PnL: only passed attempts with a known settlement for the source fill.
 settled=q("""select ca.id,ca.requested_usd,ca.executable_price,rf.market,rf.token_id,rf.trade_ts,s.settlement_price,s.settled_at from copy_attempts ca join raw_fills rf on rf.id=ca.fill_id join paper_trades pt on pt.market=rf.market and pt.token_id=rf.token_id join settlements s on s.trade_id=pt.id where ca.profile_id in ("""+(','.join('?'*len(ids)) if profiles else 'NULL')+") and ca.status='DRY_RUN' and ca.executable_price>0 and s.settled_at>=rf.trade_ts group by ca.id",ids if profiles else []) if profiles else []
 for z in settled:
  pnl=float(z['requested_usd'])*(float(z['settlement_price'])/float(z['executable_price'])-1);stats['settled']+=1;stats['invested']+=float(z['requested_usd']);stats['pnl']+=pnl
 stats['pnl']=round(stats['pnl'],2);stats['invested']=round(stats['invested'],2);stats['roi']=round(stats['pnl']/stats['invested']*100,2) if stats['invested'] else None
 return {'wallet_connected':False,'live_execution':False,'profiles':profiles,'attempts':attempts,'leaders':leaders,'sports':sports,'leagues':leagues,'stats':stats}
auth_schema()

class H(BaseHTTPRequestHandler):
 def send_json(self,code,data,cookie=None):
  b=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
  if cookie:self.send_header('Set-Cookie',cookie)
  self.end_headers();self.wfile.write(b)
 def body_json(self):
  n=min(int(self.headers.get('Content-Length','0') or 0),16384);return json.loads(self.rfile.read(n) or b'{}')
 def do_POST(self):
  try:
   d=self.body_json();email=(d.get('email') or '').strip().lower();pw=d.get('password') or ''
   if self.path in ('/api/register','/api/login'):
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):return self.send_json(400,{'error':'Введите корректный email'})
    if len(pw)<8:return self.send_json(400,{'error':'Пароль — минимум 8 символов'})
   if self.path=='/api/register':
    try:uid=db_exec('insert into users(email,password_hash,created_at) values(?,?,?)',(email,hash_password(pw),time.time()))
    except sqlite3.IntegrityError:return self.send_json(409,{'error':'Такой email уже зарегистрирован'})
    now=time.time();db_exec("insert into copy_profiles(user_id,name,leader,stake_usd,sport_filter,league_filter,max_slippage,enabled,execution_mode,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?,?)",(uid,'RN1 · $2 all sports','RN1',2.0,'*','*',.03,1,'DRY_RUN',now,now))
   elif self.path=='/api/login':
    z=q('select id,password_hash from users where email=?',(email,));
    if not z or not verify_password(pw,z[0]['password_hash']):return self.send_json(401,{'error':'Неверный email или пароль'})
    uid=z[0]['id']
   elif self.path=='/api/profile':
    u=current_user(self.headers.get('Cookie'))
    if not u:return self.send_json(401,{'error':'unauthorized'})
    leader=(d.get('leader') or '').strip();stake=float(d.get('stake_usd',2));sport=(d.get('sport_filter') or '*').strip();league=(d.get('league_filter') or '*').strip();slip=float(d.get('max_slippage',.03))
    if not leader or len(leader)>128:return self.send_json(400,{'error':'Укажите трейдера или кошелёк'})
    if not (.1<=stake<=10000):return self.send_json(400,{'error':'Некорректная сумма'})
    if not (0<=slip<=1):return self.send_json(400,{'error':'Некорректное проскальзывание'})
    ps=q('select id from copy_profiles where user_id=? order by id limit 1',(u['id'],));now=time.time()
    if ps:db_exec('update copy_profiles set leader=?,name=?,stake_usd=?,sport_filter=?,league_filter=?,max_slippage=?,updated_at=? where id=?',(leader,leader+' · copy',stake,sport,league,slip,now,ps[0]['id']))
    else:db_exec("insert into copy_profiles(user_id,name,leader,stake_usd,sport_filter,league_filter,max_slippage,enabled,execution_mode,created_at,updated_at) values(?,?,?,?,?,?,?,?,?,?,?)",(u['id'],leader+' · copy',leader,stake,sport,league,slip,1,'DRY_RUN',now,now))
    return self.send_json(200,{'ok':True})
   elif self.path=='/api/logout':
    u=current_user(self.headers.get('Cookie'));
    if u:
     # delete all current-user sessions: simple first version
     db_exec('delete from user_sessions where user_id=?',(u['id'],))
    return self.send_json(200,{'ok':True},'ce_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax')
   else:return self.send_json(404,{'error':'not found'})
   token=secrets.token_urlsafe(32);now=time.time();db_exec('insert into user_sessions(user_id,token_hash,created_at,expires_at) values(?,?,?,?)',(uid,token_hash(token),now,now+30*86400))
   return self.send_json(200,{'ok':True},f'ce_session={token}; Path=/; Max-Age={30*86400}; HttpOnly; Secure; SameSite=Lax')
  except Exception as e:
   print('[AUTH_ERROR]',repr(e),flush=True);return self.send_json(500,{'error':'Ошибка сервера'})
 def do_GET(self):
  u=urlparse(self.path)
  if u.path=='/api/me':
   me=current_user(self.headers.get('Cookie'));return self.send_json(200 if me else 401,{'user':me} if me else {'error':'unauthorized'})
  if u.path not in ('/api/dashboard','/api/backtest','/api/history','/api/positions','/api/account'):return self.send_json(404,{'error':'not found'})
  try:
   z={k:v[-1] for k,v in parse_qs(u.query).items()}
   if u.path=='/api/dashboard':data=payload()
   elif u.path=='/api/account':
    me=current_user(self.headers.get('Cookie'))
    if not me:return self.send_json(401,{'error':'unauthorized'})
    data=account_payload(me['id']);data['user']=me
   elif u.path=='/api/history':data=history_positions(z)
   elif u.path=='/api/positions':data=observed_positions(z.get('leader'),z.get('status','all'),z.get('limit',500))
   else:
    z['leader']=None if z.get('leader') in (None,'','all') else z.get('leader');data=backtest(z)
   return self.send_json(200,data)
  except Exception:return self.send_json(500,{'error':'Ошибка сервера'})
 def log_message(self,*a):pass
ThreadingHTTPServer(('0.0.0.0',8765),H).serve_forever()
