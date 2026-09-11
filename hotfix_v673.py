from pathlib import Path
import re
P=Path("/app/app.py")
if not P.exists(): P=Path("app.py")
s=P.read_text(encoding="utf-8")
if 'APP_VERSION = "6.7.3"' in s: raise SystemExit(0)
if 'APP_VERSION = "6.7.2"' not in s: raise SystemExit("V6.7.2 required")
s=s.replace('APP_VERSION = "6.7.2"','APP_VERSION = "6.7.3"',1)

A='PUMPPORTAL_WS_BASE = "wss://pumpportal.fun/api/data"'
B=A+'''
PUMPPORTAL_PUBLIC_WALLET=os.getenv("PUMPPORTAL_PUBLIC_WALLET","").strip()
METERED_OPT=os.getenv("NOVA_METERED_COST_OPTIMIZER","true").lower() in ("1","true","yes","on")
METERED_MAX_ACTIVE=max(1,min(6,int(float(os.getenv("NOVA_METERED_MAX_ACTIVE_SUBS","3")))))
METERED_MAX_SUBS_MIN=max(1,min(60,int(float(os.getenv("NOVA_METERED_MAX_NEW_SUBS_PER_MIN","12")))))
METERED_TTL=max(4.0,min(60.0,float(os.getenv("NOVA_METERED_TOKEN_TTL_SEC","12"))))
METERED_MAX_EVENTS_H=max(500,int(float(os.getenv("NOVA_METERED_MAX_EVENTS_PER_HOUR","4000"))))
METERED_FLOOR=max(.020,float(os.getenv("NOVA_METERED_WALLET_FLOOR_SOL","0.025")))
METERED_CHECK=max(20.0,min(300.0,float(os.getenv("NOVA_METERED_WALLET_CHECK_SEC","60"))))
METERED_RATE=max(0.0,float(os.getenv("NOVA_METERED_EST_SOL_PER_10K","0.01")))'''
if A not in s: raise SystemExit("env anchor missing")
s=s.replace(A,B,1)

A='''    "ws_last_trade_mint": None,
    "pulse_last_event": 0,'''
B='''    "ws_last_trade_mint": None,
    "metered_hour_start":time.time(),"metered_events_h":0,"metered_events_total":0,
    "metered_min_start":time.time(),"metered_subs_min":0,"metered_state":"STARTING",
    "metered_wallet_balance":None,"metered_wallet_check":0,"metered_wallet_error":None,
    "metered_pruned":0,"metered_skipped":0,
    "pulse_last_event": 0,'''
if A not in s: raise SystemExit("runtime anchor missing")
s=s.replace(A,B,1)

H=r'''def _cost_roll():
    n=time.time()
    if n-nz(runtime.get("metered_hour_start"),n)>=3600:
        runtime["metered_hour_start"]=n;runtime["metered_events_h"]=0
    if n-nz(runtime.get("metered_min_start"),n)>=60:
        runtime["metered_min_start"]=n;runtime["metered_subs_min"]=0

def _cost_cap():
    if not METERED_OPT:return max(8,i("pulse_max_trade_subscriptions"))
    _cost_roll();r=nz(runtime.get("metered_events_h"))/max(METERED_MAX_EVENTS_H,1)
    return 1 if r>=.90 else min(METERED_MAX_ACTIVE,2) if r>=.70 else METERED_MAX_ACTIVE

def _cost_note_sub(n=1):
    _cost_roll();runtime["metered_subs_min"]=int(runtime.get("metered_subs_min",0))+int(n)

def _cost_note_event():
    _cost_roll()
    runtime["metered_events_h"]=int(runtime.get("metered_events_h",0))+1
    runtime["metered_events_total"]=int(runtime.get("metered_events_total",0))+1

async def _cost_balance():
    if not PUMPPORTAL_PUBLIC_WALLET:return None
    n=time.time()
    if n-nz(runtime.get("metered_wallet_check"))<METERED_CHECK:return runtime.get("metered_wallet_balance")
    runtime["metered_wallet_check"]=n
    try:
        q={"jsonrpc":"2.0","id":1,"method":"getBalance","params":[PUMPPORTAL_PUBLIC_WALLET,{"commitment":"confirmed"}]}
        async with httpx.AsyncClient(timeout=8) as c:r=await c.post(SOLANA_RPC_URL,json=q)
        r.raise_for_status();v=nz(((r.json().get("result") or {}).get("value")))/1e9
        runtime["metered_wallet_balance"]=round(v,9);runtime["metered_wallet_error"]=None;return v
    except Exception as e:
        runtime["metered_wallet_error"]=str(e)[:180];return runtime.get("metered_wallet_balance")

def _cost_block():
    _cost_roll()
    b=runtime.get("metered_wallet_balance")
    if b is not None and nz(b)<=METERED_FLOOR:return "wallet_floor"
    if int(runtime.get("metered_events_h",0))>=METERED_MAX_EVENTS_H:return "hourly_budget"
    if int(runtime.get("metered_subs_min",0))>=METERED_MAX_SUBS_MIN:return "subscription_rate"
    if runtime.get("ws_subscription_blocked_until",0)>time.time():return "provider_breaker"
    return None

def _cost_can_sub():
    return _trade_subscription_allowed() and (not METERED_OPT or (_cost_block() is None and len(runtime.get("pulse_subscribed",set()))<_cost_cap()))

async def _cost_unsub(ws,mints,reason):
    mints=list(dict.fromkeys(mints))
    if not mints:return
    await ws.send(json.dumps({"method":"unsubscribeTokenTrade","keys":mints}))
    runtime["ws_unsubscription_requests"]+=len(mints);runtime["metered_pruned"]+=len(mints)
    for m in mints:
        runtime["pulse_subscribed"].discard(m);runtime["pulse_subscription_birth"].pop(m,None)
        if m in runtime.get("launch_watch",{}):
            runtime["launch_watch"][m]["status"]="COST_PRUNED";runtime["launch_watch"][m]["last_reason"]=reason

async def cost_sync_pulse_subscriptions(ws):
    while True:
        try:
            await _cost_balance();_cost_roll();n=time.time();subs=list(runtime.get("pulse_subscribed",set()))
            reason=_cost_block()
            if reason in ("wallet_floor","hourly_budget","provider_breaker"):
                runtime["metered_state"]="PAUSED_"+reason.upper()
                await _cost_unsub(ws,subs,reason)
            else:
                runtime["metered_state"]="ACTIVE"
                stale=[m for m in subs if n-nz(runtime["pulse_subscription_birth"].get(m),n)>=METERED_TTL]
                if stale:await _cost_unsub(ws,stale,"first_seconds_ttl")
                subs=list(runtime.get("pulse_subscribed",set()));cap=_cost_cap()
                if len(subs)>cap:
                    subs.sort(key=lambda m:nz(runtime["pulse_subscription_birth"].get(m),0))
                    await _cost_unsub(ws,subs[:len(subs)-cap],"dynamic_cap")
        except asyncio.CancelledError:raise
        except Exception:
            runtime["metered_state"]="ERROR"
        await asyncio.sleep(1.25)

def metered_cost_status():
    _cost_roll();e=int(runtime.get("metered_events_h",0));b=runtime.get("metered_wallet_balance")
    return {"enabled":METERED_OPT,"state":runtime.get("metered_state"),
      "active_paid_subscriptions":len(runtime.get("pulse_subscribed",set())),"active_cap":_cost_cap(),
      "token_ttl_sec":METERED_TTL,"new_subscriptions_this_minute":runtime.get("metered_subs_min",0),
      "new_subscriptions_per_min_limit":METERED_MAX_SUBS_MIN,"events_this_hour":e,
      "events_per_hour_limit":METERED_MAX_EVENTS_H,"hour_budget_pct":round(e/max(METERED_MAX_EVENTS_H,1)*100,1),
      "events_remaining_this_hour":max(0,METERED_MAX_EVENTS_H-e),
      "estimated_session_spend_sol":round(runtime.get("metered_events_total",0)/10000*METERED_RATE,8),
      "wallet_monitor_configured":bool(PUMPPORTAL_PUBLIC_WALLET),"wallet_balance_sol":b,
      "wallet_floor_sol":METERED_FLOOR,"wallet_error":runtime.get("metered_wallet_error"),
      "pruned_subscriptions":runtime.get("metered_pruned",0),"skipped_new_tokens":runtime.get("metered_skipped",0),
      "block_reason":_cost_block()}
'''
anchor='async def pumpportal_realtime_loop():'
if anchor not in s: raise SystemExit("loop anchor missing")
s=s.replace(anchor,H+anchor,1)

s=s.replace('sync_task=asyncio.create_task(sync_pulse_subscriptions(ws))','sync_task=asyncio.create_task(cost_sync_pulse_subscriptions(ws))',1)
s=s.replace('''                    seeds=[
                        c.get("mint") for c in runtime.get("candidates",[])
                        if not c.get("perp_eligible") and c.get("mint")
                    ][:seed_cap]
                    seeds=list(dict.fromkeys(open_spot_mints()+seeds))''','''                    seeds=list(dict.fromkeys(open_spot_mints()))''',1)
s=s.replace('if seeds and _trade_subscription_allowed():','if seeds and _cost_can_sub():',1)
s=s.replace('''runtime["ws_subscription_requests"]+=len(seeds)
                        runtime["pulse_subscribed"].update(seeds)''','''runtime["ws_subscription_requests"]+=len(seeds)
                        _cost_note_sub(len(seeds))
                        runtime["pulse_subscribed"].update(seeds)''',1)
s=s.replace('if mint not in runtime["pulse_subscribed"] and _trade_subscription_allowed():','if mint not in runtime["pulse_subscribed"] and _cost_can_sub():',1)
s=s.replace('cap=max(8,i("pulse_max_trade_subscriptions")) if FREE_LITE else max(30,i("pulse_max_trade_subscriptions"))','cap=_cost_cap()',2)
s=s.replace('''runtime["ws_subscription_requests"]+=1
                                    runtime["pulse_subscribed"].add(mint)''','''runtime["ws_subscription_requests"]+=1
                                    _cost_note_sub(1)
                                    runtime["pulse_subscribed"].add(mint)''',1)
s=s.replace('''                            elif mint not in runtime["pulse_subscribed"] and info:
                                runtime["metered_skipped_new_tokens"]+=1
                                info["status"]="COST_FILTERED"''','''                            elif mint not in runtime["pulse_subscribed"] and info:
                                runtime["metered_skipped"]=int(runtime.get("metered_skipped",0))+1
                                info["status"]="COST_FILTERED"''',1)
s=s.replace('''runtime["ws_last_trade_event"]=time.time()
                        runtime["ws_last_trade_mint"]=mint''','''runtime["ws_last_trade_event"]=time.time()
                        runtime["ws_last_trade_mint"]=mint
                        _cost_note_event()''',1)
s=s.replace('''"last_trade_mint":runtime.get("ws_last_trade_mint"),
            "entries":runtime["pulse_entries"],''','''"last_trade_mint":runtime.get("ws_last_trade_mint"),
            "cost_optimizer":metered_cost_status(),
            "entries":runtime["pulse_entries"],''',1)
s=s.replace('''"last_trade_mint":runtime.get("ws_last_trade_mint"),
        "launch_trades_seen":runtime.get("launch_trades_seen",0),''','''"last_trade_mint":runtime.get("ws_last_trade_mint"),
        "cost_optimizer":metered_cost_status(),
        "launch_trades_seen":runtime.get("launch_trades_seen",0),''',1)
s=s.replace("/6.7.2","/6.7.3")
compile(s,str(P),"exec");P.write_text(s,encoding="utf-8")
print("[NOVA V6.7.3] Cost optimizer applied.")
