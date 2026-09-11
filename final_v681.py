from pathlib import Path
import re

P=Path("/app/app.py")
if not P.exists(): P=Path("app.py")
s=P.read_text(encoding="utf-8")

if 'APP_VERSION = "6.8.1"' in s:
    raise SystemExit(0)
if 'APP_VERSION = "6.8.0"' not in s:
    raise SystemExit("V6.8.0 required")

s=s.replace('APP_VERSION = "6.8.0"','APP_VERSION = "6.8.1"',1)

env_anchor='PROFIT_LAUNCH_MIN_BUY_SOL=max(0.03,min(0.50,float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_BUY_SOL","0.10"))))'
env_add=env_anchor+'''
MICRO_PROFIT_ENABLED=os.getenv("NOVA_MICRO_PROFIT","true").lower() in ("1","true","yes","on")
MICRO_SCALP_TP=max(.60,min(5.0,float(os.getenv("NOVA_MICRO_SCALP_TP_PCT","1.25"))))
MICRO_PUMP_TP=max(1.0,min(8.0,float(os.getenv("NOVA_MICRO_PUMP_TP_PCT","2.00"))))
MICRO_SNIPER_TP=max(.60,min(4.0,float(os.getenv("NOVA_MICRO_SNIPER_TP_PCT","1.00"))))
MICRO_LAUNCH_TP=max(1.5,min(8.0,float(os.getenv("NOVA_MICRO_LAUNCH_TP_PCT","3.00"))))
MICRO_SCALP_MAX_HOLD=max(4.0,min(30.0,float(os.getenv("NOVA_MICRO_SCALP_MAX_HOLD_MIN","12"))))
MICRO_PUMP_MAX_HOLD=max(6.0,min(45.0,float(os.getenv("NOVA_MICRO_PUMP_MAX_HOLD_MIN","20"))))
MICRO_LAUNCH_MAX_HOLD_SEC=max(6.0,min(25.0,float(os.getenv("NOVA_MICRO_LAUNCH_MAX_HOLD_SEC","12"))))
MICRO_SCALP_SCRATCH_SEC=max(30.0,min(240.0,float(os.getenv("NOVA_MICRO_SCALP_SCRATCH_SEC","90"))))
MICRO_PUMP_SCRATCH_SEC=max(60.0,min(360.0,float(os.getenv("NOVA_MICRO_PUMP_SCRATCH_SEC","120"))))
MICRO_LAUNCH_SCRATCH_SEC=max(1.0,min(8.0,float(os.getenv("NOVA_MICRO_LAUNCH_SCRATCH_SEC","2"))))
MICRO_SCALP_SCRATCH_LOSS=max(.20,min(1.0,float(os.getenv("NOVA_MICRO_SCALP_SCRATCH_LOSS_PCT","0.35"))))
MICRO_PUMP_SCRATCH_LOSS=max(.30,min(1.5,float(os.getenv("NOVA_MICRO_PUMP_SCRATCH_LOSS_PCT","0.50"))))
MICRO_LAUNCH_SCRATCH_LOSS=max(1.0,min(5.0,float(os.getenv("NOVA_MICRO_LAUNCH_SCRATCH_LOSS_PCT","2.50"))))
MICRO_ROUTER_DEFICIT=max(0.0,min(2.0,float(os.getenv("NOVA_MICRO_ROUTER_SIGNAL_DEFICIT","1"))))
MICRO_ROUTER_QUALITY=max(58.0,min(72.0,float(os.getenv("NOVA_MICRO_ROUTER_MIN_QUALITY","60"))))
MICRO_ROUTER_LIQ=max(25000.0,float(os.getenv("NOVA_MICRO_ROUTER_MIN_LIQ","35000")))
MICRO_ROUTER_BUY_PRESSURE=max(55.0,min(75.0,float(os.getenv("NOVA_MICRO_ROUTER_MIN_BUY_PRESSURE","60"))))
MICRO_SOFT_ENTRIES_H=max(2,min(8,int(float(os.getenv("NOVA_MICRO_SOFT_ENTRIES_PER_HOUR","6")))))
'''
if env_anchor not in s: raise SystemExit("env anchor missing")
s=s.replace(env_anchor,env_add,1)

s=s.replace('return PROFIT_ROUTER_SIGNAL_DEFICIT if profit_cycle_active() else 0.0',
            'return min(PROFIT_ROUTER_SIGNAL_DEFICIT,MICRO_ROUTER_DEFICIT) if profit_cycle_active() and MICRO_PROFIT_ENABLED else (PROFIT_ROUTER_SIGNAL_DEFICIT if profit_cycle_active() else 0.0)',1)
s=s.replace('return min(f("router_soft_market_quality_floor"),PROFIT_ROUTER_MIN_QUALITY) if profit_cycle_active() else f("router_soft_market_quality_floor")',
            'return max(min(f("router_soft_market_quality_floor"),PROFIT_ROUTER_MIN_QUALITY),MICRO_ROUTER_QUALITY) if profit_cycle_active() and MICRO_PROFIT_ENABLED else (min(f("router_soft_market_quality_floor"),PROFIT_ROUTER_MIN_QUALITY) if profit_cycle_active() else f("router_soft_market_quality_floor"))',1)
s=s.replace('return min(f("router_soft_liquidity_floor"),PROFIT_ROUTER_MIN_LIQ) if profit_cycle_active() else f("router_soft_liquidity_floor")',
            'return max(min(f("router_soft_liquidity_floor"),PROFIT_ROUTER_MIN_LIQ),MICRO_ROUTER_LIQ) if profit_cycle_active() and MICRO_PROFIT_ENABLED else (min(f("router_soft_liquidity_floor"),PROFIT_ROUTER_MIN_LIQ) if profit_cycle_active() else f("router_soft_liquidity_floor"))',1)
s=s.replace('return max(i("router_max_soft_entries_per_hour"),PROFIT_SOFT_ENTRIES_H) if profit_cycle_active() else i("router_max_soft_entries_per_hour")',
            'return max(i("router_max_soft_entries_per_hour"),PROFIT_SOFT_ENTRIES_H,MICRO_SOFT_ENTRIES_H) if profit_cycle_active() and MICRO_PROFIT_ENABLED else (max(i("router_max_soft_entries_per_hour"),PROFIT_SOFT_ENTRIES_H) if profit_cycle_active() else i("router_max_soft_entries_per_hour"))',1)

bp_old='''    if bp < f("router_min_buy_pressure"):
        result["reason"]="controlled router weak buy pressure";return result'''
bp_new='''    min_bp=max(f("router_min_buy_pressure"),MICRO_ROUTER_BUY_PRESSURE) if MICRO_PROFIT_ENABLED else f("router_min_buy_pressure")
    if bp < min_bp:
        result["reason"]="controlled router weak buy pressure";return result'''
if bp_old not in s: raise SystemExit("bp anchor missing")
s=s.replace(bp_old,bp_new,1)

s=s.replace('PROFIT_LAUNCH_MIN_SCORE=max(64.0,min(78.0,float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_SCORE","68"))))',
            'PROFIT_LAUNCH_MIN_SCORE=max(68.0,min(80.0,float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_SCORE","72"))))',1)
s=s.replace('PROFIT_LAUNCH_MIN_PRESSURE=max(58.0,min(75.0,float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_BUY_PRESSURE","64"))))',
            'PROFIT_LAUNCH_MIN_PRESSURE=max(62.0,min(78.0,float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_BUY_PRESSURE","68"))))',1)
s=s.replace('PROFIT_LAUNCH_MIN_BUY_SOL=max(0.03,min(0.50,float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_BUY_SOL","0.10"))))',
            'PROFIT_LAUNCH_MIN_BUY_SOL=max(0.05,min(0.50,float(os.getenv("NOVA_PROFIT_LAUNCH_MIN_BUY_SOL","0.12"))))',1)

lock_re=r'def strategy_profit_lock\(strategy,peak_net_pct\):.*?\n(?=def strategy_tp_plan\(strategy\):)'
lock_new=r'''def strategy_profit_lock(strategy,peak_net_pct):
    p=nz(peak_net_pct)
    if MICRO_PROFIT_ENABLED and profit_cycle_active():
        if strategy=="LAUNCH_SNIPER":
            if p>=5:return max(2.5,p-1.5)
            if p>=3:return 1.25
            if p>=2:return .50
        elif strategy=="SNIPER_LONG":
            if p>=1.8:return max(.9,p-.5)
            if p>=1:return .35
            if p>=.7:return .08
        elif strategy=="SCALP_LONG":
            if p>=2:return max(1.0,p-.6)
            if p>=1.25:return .55
            if p>=.8:return .15
        elif strategy=="PUMP_LONG":
            if p>=3:return max(1.5,p-.9)
            if p>=2:return .85
            if p>=1.2:return .20
        elif strategy in ("PERP_LONG","PERP_SHORT"):
            if p>=2:return .80
            if p>=1:return .20
    if strategy=="LAUNCH_SNIPER":
        if p>=25:return max(15.0,p-7.0)
        if p>=15:return 8.0
        if p>=10:return 5.0
        if p>=7:return 3.0
        if p>=5:return 1.25
    elif strategy=="SNIPER_LONG":
        if p>=3:return max(2.0,p-0.8)
        if p>=2:return 1.15
        if p>=1.25:return 0.45
        if p>=0.75:return 0.08
    elif strategy=="SCALP_LONG":
        if p>=5:return max(3.0,p-1.5)
        if p>=3:return 1.50
        if p>=1.75:return 0.60
        if p>=1.00:return 0.12
    elif strategy=="PUMP_LONG":
        if p>=20:return max(10.0,p-6.0)
        if p>=10:return 4.0
        if p>=6:return 2.0
        if p>=3:return 0.75
        if p>=1.50:return 0.15
    elif strategy in ("PERP_LONG","PERP_SHORT"):
        if p>=8:return max(4.0,p-3.0)
        if p>=5:return 2.0
        if p>=2.5:return 0.75
        if p>=1.0:return 0.10
    return None

'''
s,n=re.subn(lock_re,lock_new,s,count=1,flags=re.S)
if n!=1: raise SystemExit("profit lock replace failed")

s=s.replace('max_hold=PROFIT_SCALP_MAX_HOLD_MIN',
            'max_hold=MICRO_SCALP_MAX_HOLD if MICRO_PROFIT_ENABLED else PROFIT_SCALP_MAX_HOLD_MIN',1)
s=s.replace('max_hold=PROFIT_PUMP_MAX_HOLD_MIN',
            'max_hold=MICRO_PUMP_MAX_HOLD if MICRO_PROFIT_ENABLED else PROFIT_PUMP_MAX_HOLD_MIN',1)
s=s.replace('max_hold=f("launch_max_hold_sec")/60',
            'max_hold=(MICRO_LAUNCH_MAX_HOLD_SEC if MICRO_PROFIT_ENABLED and profit_cycle_active() else f("launch_max_hold_sec"))/60',1)

exit_old='''            # Profit Cycle full-bank exits use NET simulated P&L after execution friction.
            elif profit_cycle_active() and obj.strategy=="SCALP_LONG" and net_ret>=PROFIT_SCALP_FULL_TP_PCT:
                reason="PROFIT_CYCLE_TAKE"
            elif profit_cycle_active() and obj.strategy=="PUMP_LONG" and net_ret>=PROFIT_PUMP_FULL_TP_PCT:
                reason="PROFIT_CYCLE_TAKE"

            # Strategy-specific hard stop is intentionally tighter than the user-visible
            # absolute stop-loss cap.'''
exit_new='''            # Micro Profit Cycle: bank small NET wins quickly.
            elif profit_cycle_active() and MICRO_PROFIT_ENABLED and obj.strategy=="SCALP_LONG" and net_ret>=MICRO_SCALP_TP:
                reason="MICRO_PROFIT_TAKE"
            elif profit_cycle_active() and MICRO_PROFIT_ENABLED and obj.strategy=="PUMP_LONG" and net_ret>=MICRO_PUMP_TP:
                reason="MICRO_PROFIT_TAKE"
            elif profit_cycle_active() and MICRO_PROFIT_ENABLED and obj.strategy=="SNIPER_LONG" and net_ret>=MICRO_SNIPER_TP:
                reason="MICRO_PROFIT_TAKE"
            elif profit_cycle_active() and MICRO_PROFIT_ENABLED and obj.strategy=="LAUNCH_SNIPER" and net_ret>=MICRO_LAUNCH_TP:
                reason="MICRO_PROFIT_TAKE"
            elif profit_cycle_active() and MICRO_PROFIT_ENABLED and obj.strategy=="SCALP_LONG" and held_seconds>=MICRO_SCALP_SCRATCH_SEC and peak_net_ret<.35 and net_ret<=-MICRO_SCALP_SCRATCH_LOSS:
                reason="MICRO_SCALP_SCRATCH"
            elif profit_cycle_active() and MICRO_PROFIT_ENABLED and obj.strategy=="PUMP_LONG" and held_seconds>=MICRO_PUMP_SCRATCH_SEC and peak_net_ret<.45 and net_ret<=-MICRO_PUMP_SCRATCH_LOSS:
                reason="MICRO_PUMP_SCRATCH"
            elif profit_cycle_active() and MICRO_PROFIT_ENABLED and obj.strategy=="LAUNCH_SNIPER" and held_seconds>=MICRO_LAUNCH_SCRATCH_SEC and peak_net_ret<1.25 and net_ret<=-MICRO_LAUNCH_SCRATCH_LOSS:
                reason="MICRO_LAUNCH_SCRATCH"
            elif profit_cycle_active() and obj.strategy=="SCALP_LONG" and net_ret>=PROFIT_SCALP_FULL_TP_PCT:
                reason="PROFIT_CYCLE_TAKE"
            elif profit_cycle_active() and obj.strategy=="PUMP_LONG" and net_ret>=PROFIT_PUMP_FULL_TP_PCT:
                reason="PROFIT_CYCLE_TAKE"

            # Strategy-specific hard stop is intentionally tighter than the user-visible
            # absolute stop-loss cap.'''
if exit_old not in s: raise SystemExit("exit anchor missing")
s=s.replace(exit_old,exit_new,1)

tele_old='''        "soft_entries_hour_cap":profit_router_hourly_cap(),
        "note":"PAPER objective only; profitability is not guaranteed."'''
tele_new='''        "soft_entries_hour_cap":profit_router_hourly_cap(),
        "micro_profit":{
            "enabled":bool(MICRO_PROFIT_ENABLED and profit_cycle_active()),
            "scalp_tp_pct":MICRO_SCALP_TP,"pump_tp_pct":MICRO_PUMP_TP,
            "sniper_tp_pct":MICRO_SNIPER_TP,"launch_tp_pct":MICRO_LAUNCH_TP,
            "scalp_max_hold_min":MICRO_SCALP_MAX_HOLD,
            "pump_max_hold_min":MICRO_PUMP_MAX_HOLD,
            "launch_max_hold_sec":MICRO_LAUNCH_MAX_HOLD_SEC,
            "router_signal_deficit":profit_router_signal_deficit(),
            "router_quality_floor":profit_router_quality_floor(),
            "router_liquidity_floor":profit_router_liquidity_floor(),
            "router_buy_pressure_floor":MICRO_ROUTER_BUY_PRESSURE
        },
        "note":"PAPER objective only; profitability is not guaranteed."'''
if tele_old not in s: raise SystemExit("telemetry anchor missing")
s=s.replace(tele_old,tele_new,1)

s=s.replace("/6.8.0","/6.8.1")
compile(s,str(P),"exec")
P.write_text(s,encoding="utf-8")
print("[NOVA V6.8.1] Micro Profit Cycle applied.")
