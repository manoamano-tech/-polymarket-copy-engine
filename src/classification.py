"""Stable, conservative sports classification for observed Polymarket fills."""
def classify_sport(event, question=''):
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
    if p=='unl': return ('Football','UEFA Nations League')
    if p=='wsl': return ('Football','WSL')
    if p=='enl': return ('Football','ENL')
    if p in ('fif','mex','col1','bra2','clf','chi2','es2','ned2','mar1','canpl','el1'): return ('Football',p.upper())
    tennis_tours={'chengdu open':'ATP','hangzhou open':'ATP','san diego 2':'ATP','singapore open':'WTA','korea open':'WTA','porto':'WTA','tolentino':'Tennis / ITF','ankara':'Tennis / ITF','buenos aires 2':'Tennis / Challenger','st. tropez':'Tennis / Challenger','plovdiv 4':'Tennis / ITF'}
    for name,tour in tennis_tours.items():
        if q.startswith(name+':'): return ('Tennis',tour)
    football_teams=('falcons','packers','army','temple','clemson','california','liberty','coastal carolina','navy','uab','northwestern','indiana')
    if any(t in q for t in football_teams) and (' vs. ' in q or q.startswith('spread:')): return ('American football','Other / legacy')
    if q.startswith('golden state valkyries vs. los angeles sparks') or q.startswith('toronto tempo vs. connecticut sun'): return ('Basketball','WNBA')
    if q.startswith('map handicap:'): return ('Esports','CS2')
    if q.startswith('will ') or (' vs. ' in q and any(x in q for x in ('o/u','exact score','end in a draw','both teams to score','draw at halftime','leading at halftime'))): return ('Football','Other football')
    if q.startswith('exact score:'): return ('Football','Other football')
    return ('Other','Unclassified')
