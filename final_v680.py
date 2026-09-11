from pathlib import Path
import re
P=Path("/app/app.py")
if not P.exists(): P=Path("app.py")
s=P.read_text(encoding="utf-8")
if 'APP_VERSION = "6.8.0"' in s: raise SystemExit(0)
if 'APP_VERSION = "6.7.2"' not in s: raise SystemExit("V6.7.2 required")
s=s.replace('APP_VERSION = "6.7.2"','APP_VERSION = "6.8.0"',1)

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
s=s.replace("/6.7.2","/6.8.0")

# ============================================================
# V6.8.0 PROFIT CYCLE — PAPER ONLY
# ============================================================

profit_env_anchor = 'METERED_RATE=max(0.0,float(os.getenv("NOVA_METERED_EST_SOL_PER_10K","0.01")))'
profit_env_replacement = profit_env_anchor + '''
PROFIT_CYCLE_ENABLED=os.getenv("NOVA_PROFIT_CYCLE","true").lower() in ("1","true","yes","on")
PROFIT_DAILY_OBJECTIVE_USD=max(0.0,float(os.getenv("NOVA_DAILY_PROFIT_OBJECTIVE_USD","100")))
PROFIT_ROUTER_SIGNAL_DEFICIT=max(0.0,min(5.0,float(os.getenv("NOVA_PROFIT_ROUTER_SIGNAL_DEFICIT","2"))))
PROFIT_ROUTER_MIN_QUALITY=max(55.0,min(70.0,float(os.getenv("NOVA_PROFIT_ROUTER_MIN_QUALITY","58"))))
PROFIT_ROUTER_MIN_LIQ=max(20000.0,float(os.getenv("NOVA_PROFIT_ROUTER_MIN_LIQ","25000")))
PROFIT_SOFT_ENTRIES_H=max(1,min(6,int(float(os.getenv("NOVA_PROFIT_SOFT_ENTRIES_PER_HOUR","4")))))
PROFIT_SCALP_MAX_HOLD_MIN=max(5.0,min(60.0,float(os.getenv("NOVA_PROFIT_SCALP_MAX_HOLD_MIN","25"))))
PROFIT_PUMP_MAX_HOLD_MIN=max(10.0,min(120.0,float(os.getenv("NOVA_PROFIT_PUMP_MAX_HOLD_MIN","45"))))
PROFIT_SCALP_FULL_TP_PCT=max(1.0,min(10.0,float(os.getenv("NOVA_PROFIT_SCALP_FULL_TP_PCT","3.5"))))
PROFIT_PUMP_FULL_TP_PCT=max(2.0,min(20.0,float(os.getenv("NOVA_PROFIT_PUMP_FULL_TP_PCT","7"))))
PROFIT_LAUNCH_MIN_SCORE=max(64.0,min(78.0,float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_SCORE","68"))))
PROFIT_LAUNCH_MIN_EVENTS=max(2,min(5,int(float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_EVENTS_2S","2")))))
PROFIT_LAUNCH_MIN_BUYERS=max(1,min(4,int(float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_BUYERS_2S","2")))))
PROFIT_LAUNCH_MIN_PRESSURE=max(58.0,min(75.0,float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_BUY_PRESSURE","64"))))
PROFIT_LAUNCH_MIN_BUY_SOL=max(0.03,min(0.50,float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_BUY_SOL","0.10"))))
'''
if profit_env_anchor not in s:
    raise SystemExit("[V6.8.0] profit env anchor missing")
s=s.replace(profit_env_anchor,profit_env_replacement,1)

router_helper_anchor='def entry_router_assess(c,strategy=None,signal=None):'
router_helpers=r'''def profit_cycle_active():
    return PROFIT_CYCLE_ENABLED and operating_mode()=="PAPER"

def profit_router_signal_deficit():
    return PROFIT_ROUTER_SIGNAL_DEFICIT if profit_cycle_active() else 0.0

def profit_router_quality_floor():
    return min(f("router_soft_market_quality_floor"),PROFIT_ROUTER_MIN_QUALITY) if profit_cycle_active() else f("router_soft_market_quality_floor")

def profit_router_liquidity_floor():
    return min(f("router_soft_liquidity_floor"),PROFIT_ROUTER_MIN_LIQ) if profit_cycle_active() else f("router_soft_liquidity_floor")

def profit_router_hourly_cap():
    return max(i("router_max_soft_entries_per_hour"),PROFIT_SOFT_ENTRIES_H) if profit_cycle_active() else i("router_max_soft_entries_per_hour")

'''
if router_helper_anchor not in s:
    raise SystemExit("[V6.8.0] entry router anchor missing")
s=s.replace(router_helper_anchor,router_helpers+router_helper_anchor,1)

router_pattern=re.compile(r'def entry_router_assess\(c,strategy=None,signal=None\):.*?\n(?=def attach_entry_router_status\(c\):)',re.S)
router_replacement=r'''def entry_router_assess(c,strategy=None,signal=None):
    strategy=strategy or suggested_strategy(c)
    signal=nz(signal if signal is not None else strategy_entry_score(strategy,c))
    threshold=effective_threshold(strategy,c)
    deficit=profit_router_signal_deficit()

    result={
        "state":"BLOCKED","reason":"unknown","strategy":strategy,
        "signal":round(signal,1),"threshold":round(threshold,1),
        "soft":False,"risk_multiplier":1.0,
    }

    strict_reason=None
    if signal>=threshold:
        ok,reason=gate(c,strategy)
        if ok:
            collateral=planned_collateral(c,strategy)
            if collateral<5:
                result["reason"]="position too small";return result
            est=execution_cost_estimate(
                c,strategy,
                collateral*max(1.0,min(2.0,strategy_leverage(strategy)))
            )
            result["execution_cost_bps"]=round(nz(est.get("all_in_bps")),1)
            if nz(est.get("all_in_bps"))>f("max_execution_cost_bps"):
                result["reason"]="execution cost too high";return result
            result.update({"state":"READY","reason":"all final gates passed"})
            return result
        strict_reason=reason
        result["strict_reason"]=reason

    if not b("selective_entry_router_enabled") or not profit_cycle_active():
        result["reason"]=strict_reason or "signal below threshold"
        return result
    if strategy not in ("SCALP_LONG","PUMP_LONG"):
        result["reason"]=strict_reason or "signal below threshold"
        return result
    if signal < threshold-deficit:
        result["reason"]="signal too far below controlled range"
        return result
    if strict_reason and strict_reason not in ("low spot liquidity","low spot market quality"):
        result["reason"]=strict_reason
        return result

    liq=nz(c.get("liquidity"))
    mq=nz(c.get("market_risk"))
    bp=nz(c.get("buy_pressure"),50)
    m5=nz(c.get("m5"))

    if liq < profit_router_liquidity_floor():
        result["reason"]="liquidity below controlled floor";return result
    if mq < profit_router_quality_floor():
        result["reason"]="market quality below controlled floor";return result
    if bp < f("router_min_buy_pressure"):
        result["reason"]="controlled router weak buy pressure";return result
    if m5 > f("router_max_soft_m5_pct") or m5 < -2:
        result["reason"]="controlled router momentum unsafe";return result
    if router_soft_entry_count() >= profit_router_hourly_cap():
        result["reason"]="controlled-entry hourly limit";return result

    probe=dict(c);probe["_router_soft_pass"]=True
    ok2,reason2=gate(probe,strategy)
    if not ok2:
        result["reason"]=reason2;return result

    collateral=planned_collateral(probe,strategy)
    if collateral<5:
        result["reason"]="position too small";return result

    est=execution_cost_estimate(
        probe,strategy,
        collateral*max(1.0,min(2.0,strategy_leverage(strategy)))
    )
    result["execution_cost_bps"]=round(nz(est.get("all_in_bps")),1)
    if nz(est.get("all_in_bps"))>f("max_execution_cost_bps"):
        result["reason"]="execution cost too high";return result

    result.update({
        "state":"SOFT_PASS",
        "reason":"near-threshold signal; controlled PAPER entry",
        "soft":True,
        "risk_multiplier":f("router_soft_risk_multiplier"),
        "liquidity":round(liq,2),"market_quality":round(mq,1),
        "buy_pressure":round(bp,1),
        "signal_deficit":round(max(0,threshold-signal),1),
    })
    return result

'''
s,n=router_pattern.subn(router_replacement,s,count=1)
if n!=1:
    raise SystemExit("[V6.8.0] failed to replace entry_router_assess")

s=s.replace('min_liq=max(min_liq,f("router_soft_liquidity_floor"))','min_liq=max(min_liq,profit_router_liquidity_floor())',1)
s=s.replace('min_quality=max(min_quality,f("router_soft_market_quality_floor"))','min_quality=max(min_quality,profit_router_quality_floor())',1)

choose_pattern=re.compile(r'def choose_entry\(\):.*?\n(?=def open_spot_mints\(\):)',re.S)
choose_replacement=r'''def choose_entry():
    if not b("bot_enabled") or b("killed"):return
    if runtime["pause_until"] and datetime.now(timezone.utc)<runtime["pause_until"]:return

    opportunities=[]
    for c in runtime["candidates"]:
        if c.get("perp_eligible"):
            if c.get("data_source")=="VELOCITY":
                if c.get("direction")=="LONG" and c["long_score"]>=effective_threshold("PERP_LONG",c):
                    opportunities.append((c["long_score"],c,"PERP_LONG"))
                elif c.get("direction")=="SHORT" and c["short_score"]>=effective_threshold("PERP_SHORT",c):
                    opportunities.append((c["short_score"],c,"PERP_SHORT"))
            else:
                if c["long_score"]>=effective_threshold("PERP_LONG",c):
                    opportunities.append((c["long_score"],c,"PERP_LONG"))
                if c["short_score"]>=effective_threshold("PERP_SHORT",c):
                    opportunities.append((c["short_score"],c,"PERP_SHORT"))
        else:
            margin=profit_router_signal_deficit()
            pump_th=effective_threshold("PUMP_LONG",c)
            scalp_th=effective_threshold("SCALP_LONG",c)
            if c["pump_score"]>=pump_th-margin:
                opportunities.append((c["pump_score"],c,"PUMP_LONG"))
            if c["scalp_score"]>=scalp_th-margin:
                opportunities.append((c["scalp_score"],c,"SCALP_LONG"))

    ranked=[]
    for signal,c,strategy in opportunities:
        quality,route=signal_quality(c,strategy,signal)
        assessment=entry_router_assess(c,strategy,signal)
        state_rank={"READY":2,"SOFT_PASS":1,"BLOCKED":0}.get(assessment["state"],0)
        ranked.append((state_rank,quality,signal,route,c,strategy,assessment))
    ranked.sort(key=lambda x:(x[0],x[1],x[2]),reverse=True)

    for state_rank,quality,signal,route,c,strategy,assessment in ranked:
        c["entry_router"]=assessment
        sec_score=nz((c.get("security") or {}).get("score"),100 if c.get("perp_eligible") else 50)
        if assessment["state"]=="BLOCKED":
            log_decision(c,strategy,"BLOCKED",assessment["reason"],signal,quality,route.get("quality",0),sec_score)
            continue

        trade_candidate=dict(c)
        if assessment["state"]=="SOFT_PASS":
            trade_candidate["_router_soft_pass"]=True

        opened,oreason=open_position(trade_candidate,strategy)
        if opened:
            outcome_reason="profit-cycle controlled entry" if assessment["state"]=="SOFT_PASS" else "entry accepted"
            log_decision(c,strategy,"OPENED",outcome_reason,signal,quality,route.get("quality",0),sec_score)
            record_event(
                "INFO","POSITION_OPENED",f"{c.get('symbol')} {strategy} opened",
                {"mode":operating_mode(),"router_state":assessment["state"],
                 "signal":signal,"quality":quality,
                 "route_quality":route.get("quality"),"security_score":sec_score}
            )
            return

        log_decision(c,strategy,"BLOCKED",oreason,signal,quality,route.get("quality",0),sec_score)

'''
s,n=choose_pattern.subn(choose_replacement,s,count=1)
if n!=1:
    raise SystemExit("[V6.8.0] failed to replace choose_entry")

s=s.replace('if int(m.get("events_2s") or 0)<i("launch_min_events_2s"):return False,"launch low events"',
            'if int(m.get("events_2s") or 0)<(min(i("launch_min_events_2s"),PROFIT_LAUNCH_MIN_EVENTS) if profit_cycle_active() else i("launch_min_events_2s")):return False,"launch low events"',1)
s=s.replace('if int(m.get("unique_buyers_2s") or 0)<i("launch_min_unique_buyers_2s"):return False,"launch low buyers"',
            'if int(m.get("unique_buyers_2s") or 0)<(min(i("launch_min_unique_buyers_2s"),PROFIT_LAUNCH_MIN_BUYERS) if profit_cycle_active() else i("launch_min_unique_buyers_2s")):return False,"launch low buyers"',1)
s=s.replace('if nz(m.get("buy_pressure_2s"))<f("launch_min_buy_pressure_2s"):return False,"launch low buy pressure"',
            'if nz(m.get("buy_pressure_2s"))<(min(f("launch_min_buy_pressure_2s"),PROFIT_LAUNCH_MIN_PRESSURE) if profit_cycle_active() else f("launch_min_buy_pressure_2s")):return False,"launch low buy pressure"',1)
s=s.replace('if nz(m.get("buy_sol_2s"))<f("launch_min_buy_sol_2s"):return False,"launch low buy flow"',
            'if nz(m.get("buy_sol_2s"))<(min(f("launch_min_buy_sol_2s"),PROFIT_LAUNCH_MIN_BUY_SOL) if profit_cycle_active() else f("launch_min_buy_sol_2s")):return False,"launch low buy flow"',1)
s=s.replace('if nz(m.get("score"))<f("launch_min_score"):return False,"launch low score"',
            'if nz(m.get("score"))<(min(f("launch_min_score"),PROFIT_LAUNCH_MIN_SCORE) if profit_cycle_active() else f("launch_min_score")):return False,"launch low score"',1)

launch_size_pattern=re.compile(r'def launch_position_size\(m\):.*?\n(?=def open_launch_position\(m\):)',re.S)
launch_size_replacement=r'''def launch_position_size(m):
    eq=max(0,nz(metrics().get("equity")))
    if profit_cycle_active():
        cap=eq*1.00/100
        gov=max(governor_risk_multiplier("LAUNCH_SNIPER"),0.50)
    else:
        cap=eq*f("launch_max_position_pct")/100
        gov=governor_risk_multiplier("LAUNCH_SNIPER")
    amount=min(cap*gov,f("cash"))
    return max(0,amount)

'''
s,n=launch_size_pattern.subn(launch_size_replacement,s,count=1)
if n!=1:
    raise SystemExit("[V6.8.0] failed to replace launch_position_size")

old_target='''    target_usd=f("start_balance")*f("daily_profit_target_pct")/100.0
    derisk_usd=f("start_balance")*f("daily_de_risk_start_pct")/100.0
    secure_trigger_usd=f("start_balance")*(f("daily_profit_target_pct")+f("daily_profit_secure_buffer_pct"))/100.0'''
new_target='''    target_usd=(PROFIT_DAILY_OBJECTIVE_USD if profit_cycle_active() and PROFIT_DAILY_OBJECTIVE_USD>0
                else f("start_balance")*f("daily_profit_target_pct")/100.0)
    derisk_usd=(target_usd*.70 if profit_cycle_active()
                else f("start_balance")*f("daily_de_risk_start_pct")/100.0)
    secure_trigger_usd=(target_usd*1.05 if profit_cycle_active()
                        else f("start_balance")*(f("daily_profit_target_pct")+f("daily_profit_secure_buffer_pct"))/100.0)'''
if old_target not in s:
    raise SystemExit("[V6.8.0] daily target anchor missing")
s=s.replace(old_target,new_target,1)

old_hold='''            if obj.strategy=="LAUNCH_SNIPER":
                max_hold=f("launch_max_hold_sec")/60
            elif obj.strategy=="SNIPER_LONG":
                max_hold=f("sniper_max_hold_minutes")
            else:
                max_hold=f("perp_max_hold_minutes") if str(obj.strategy).startswith("PERP_") else f("spot_max_hold_minutes")'''
new_hold='''            if obj.strategy=="LAUNCH_SNIPER":
                max_hold=f("launch_max_hold_sec")/60
            elif obj.strategy=="SNIPER_LONG":
                max_hold=f("sniper_max_hold_minutes")
            elif profit_cycle_active() and obj.strategy=="SCALP_LONG":
                max_hold=PROFIT_SCALP_MAX_HOLD_MIN
            elif profit_cycle_active() and obj.strategy=="PUMP_LONG":
                max_hold=PROFIT_PUMP_MAX_HOLD_MIN
            else:
                max_hold=f("perp_max_hold_minutes") if str(obj.strategy).startswith("PERP_") else f("spot_max_hold_minutes")'''
if old_hold not in s:
    raise SystemExit("[V6.8.0] max hold anchor missing")
s=s.replace(old_hold,new_hold,1)

profit_exit_anchor='''            # Strategy-specific hard stop is intentionally tighter than the user-visible
            # absolute stop-loss cap.'''
profit_exit_insert='''            # Profit Cycle banks sufficiently strong NET winners.
            elif profit_cycle_active() and obj.strategy=="SCALP_LONG" and net_ret>=PROFIT_SCALP_FULL_TP_PCT:
                reason="PROFIT_CYCLE_TAKE"
            elif profit_cycle_active() and obj.strategy=="PUMP_LONG" and net_ret>=PROFIT_PUMP_FULL_TP_PCT:
                reason="PROFIT_CYCLE_TAKE"

            # Strategy-specific hard stop is intentionally tighter than the user-visible
            # absolute stop-loss cap.'''
if profit_exit_anchor not in s:
    raise SystemExit("[V6.8.0] profit exit anchor missing")
s=s.replace(profit_exit_anchor,profit_exit_insert,1)

loop_anchor='async def pumpportal_realtime_loop():'
profit_status=r'''def profit_cycle_status():
    realized=today_realized()
    stream_sol=round(runtime.get("metered_events_total",0)/10000*METERED_RATE,8)
    stream_usd=stream_sol*sol_usd_reference()
    net_after_stream=realized-stream_usd
    target=PROFIT_DAILY_OBJECTIVE_USD if PROFIT_DAILY_OBJECTIVE_USD>0 else 100.0
    m=metrics()
    return {
        "enabled":profit_cycle_active(),
        "objective_usd":round(target,2),
        "paper_realized_pnl":round(realized,4),
        "estimated_stream_cost_sol":stream_sol,
        "estimated_stream_cost_usd":round(stream_usd,4),
        "paper_net_after_stream":round(net_after_stream,4),
        "objective_progress_pct":round(clamp(net_after_stream/max(target,1e-9)*100,0,200),1),
        "closed_trades":m.get("trades",0),
        "open_positions":m.get("open_positions",0),
        "router_signal_deficit":profit_router_signal_deficit(),
        "router_quality_floor":profit_router_quality_floor(),
        "router_liquidity_floor":profit_router_liquidity_floor(),
        "soft_entries_hour_cap":profit_router_hourly_cap(),
        "note":"PAPER objective only; profitability is not guaranteed."
    }

'''
if loop_anchor not in s:
    raise SystemExit("[V6.8.0] realtime loop anchor missing")
s=s.replace(loop_anchor,profit_status+loop_anchor,1)

s=s.replace('"cost_optimizer":metered_cost_status(),\n            "entries":runtime["pulse_entries"],',
            '"cost_optimizer":metered_cost_status(),\n            "profit_cycle":profit_cycle_status(),\n            "entries":runtime["pulse_entries"],',1)
s=s.replace('"cost_optimizer":metered_cost_status(),\n        "launch_trades_seen":runtime.get("launch_trades_seen",0),',
            '"cost_optimizer":metered_cost_status(),\n        "profit_cycle":profit_cycle_status(),\n        "launch_trades_seen":runtime.get("launch_trades_seen",0),',1)


compile(s,str(P),"exec");P.write_text(s,encoding="utf-8")
print("[NOVA V6.8.0] Final Profit Cycle applied.")
