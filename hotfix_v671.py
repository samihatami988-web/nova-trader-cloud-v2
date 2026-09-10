from pathlib import Path
import re

APP_PATH = Path("/app/app.py")
if not APP_PATH.exists():
    APP_PATH = Path("app.py")

src = APP_PATH.read_text(encoding="utf-8")

if 'APP_VERSION = "6.7.1"' in src:
    print("[NOVA V6.7.1] Launch hotfix already applied.")
    raise SystemExit(0)

if 'APP_VERSION = "6.7.0"' not in src:
    raise SystemExit("[NOVA V6.7.1] Expected V6.7.0 source after final_v670.py.")

src = src.replace('APP_VERSION = "6.7.0"', 'APP_VERSION = "6.7.1"', 1)

runtime_anchor = '''    "pulse_ws_response_headers": {},
    "pulse_ws_response_body": None,
    "pulse_last_event": 0,'''

runtime_replacement = '''    "pulse_ws_response_headers": {},
    "pulse_ws_response_body": None,
    "ws_message_counts": {"create":0,"buy":0,"sell":0,"migration":0,"provider":0,"unknown":0},
    "ws_subscription_requests": 0,
    "ws_unsubscription_requests": 0,
    "ws_trade_subscription_errors": 0,
    "ws_last_provider_message": None,
    "ws_last_trade_event": 0,
    "ws_last_trade_mint": None,
    "pulse_last_event": 0,'''

if runtime_anchor not in src:
    raise SystemExit("[NOVA V6.7.1] Runtime telemetry anchor not found.")
src = src.replace(runtime_anchor, runtime_replacement, 1)

new_ws_block = r'''def _ws_inc(kind, amount=1):
    counts=runtime.get("ws_message_counts")
    if not isinstance(counts,dict):
        counts={"create":0,"buy":0,"sell":0,"migration":0,"provider":0,"unknown":0}
        runtime["ws_message_counts"]=counts
    counts[kind]=int(counts.get(kind,0))+int(amount)

def _ws_safe_provider_message(data):
    if not isinstance(data,dict):
        return str(data)[:700]
    safe={}
    for k,v in data.items():
        lk=str(k).lower()
        if any(secret in lk for secret in ("api_key","apikey","api-key","private","secret")):
            safe[k]="***REDACTED***"
            continue
        text=str(v)
        if PUMPPORTAL_API_KEY:
            text=text.replace(PUMPPORTAL_API_KEY,"***REDACTED***")
        safe[k]=text[:400]
    try:
        return json.dumps(safe,ensure_ascii=False)[:1000]
    except Exception:
        return str(safe)[:1000]

def _ws_capture_provider_message(data):
    _ws_inc("provider")
    safe=_ws_safe_provider_message(data)
    runtime["ws_last_provider_message"]=safe
    low=safe.lower()
    if any(x in low for x in ("error","insufficient","balance","fund","unauthor","invalid","meter")):
        runtime["ws_trade_subscription_errors"]=int(runtime.get("ws_trade_subscription_errors",0))+1
        record_event(
            "WARN","PULSE_PROVIDER_MESSAGE",
            "PumpPortal returned a control/error message",
            {"message":safe},dedupe_sec=30
        )

async def pumpportal_realtime_loop():
    if runtime.get("pulse_ws_loop_started"):
        record_event(
            "WARN","PULSE_DUPLICATE_LOOP_BLOCKED",
            "Duplicate PumpPortal websocket loop was blocked",
            {},dedupe_sec=300
        )
        return

    runtime["pulse_ws_loop_started"]=True

    try:
        if not PUMPPORTAL_API_KEY:
            runtime["pulse_stream_mode"]="FALLBACK_ONLY"
            runtime["pulse_stream_error"]="PUMPPORTAL_API_KEY not configured"
            return

        if not PUMPPORTAL_TRADE_STREAM_ENABLED:
            runtime["pulse_stream_mode"]="KEY_READY_TRADE_STREAM_OFF"
            runtime["pulse_stream_error"]="Trade stream disabled by environment setting"
            return

        uri=f"{PUMPPORTAL_WS_BASE}?api-key={quote(PUMPPORTAL_API_KEY, safe='')}"
        backoff=2

        while True:
            sync_task=None
            try:
                runtime["pulse_ws_attempts"]=int(runtime.get("pulse_ws_attempts",0))+1
                runtime["pulse_ws_last_attempt"]=datetime.now(timezone.utc).isoformat()
                runtime["pulse_ws_http_status"]=None
                runtime["pulse_ws_exception_type"]=None
                runtime["pulse_ws_response_headers"]={}
                runtime["pulse_ws_response_body"]=None
                runtime["pulse_ws_retry_sec"]=None
                runtime["pulse_stream_mode"]="CONNECTING"

                async with websockets.connect(
                    uri,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    open_timeout=15,
                    max_size=2_000_000
                ) as ws:
                    runtime["pulse_stream_connected"]=True
                    runtime["pulse_stream_mode"]="PUMPPORTAL_REALTIME"
                    runtime["pulse_stream_error"]=None
                    runtime["pulse_ws_http_status"]=101
                    runtime["pulse_ws_last_connected"]=datetime.now(timezone.utc).isoformat()
                    runtime["pulse_ws_retry_sec"]=0
                    backoff=2

                    await ws.send(json.dumps({"method":"subscribeNewToken"}))
                    await ws.send(json.dumps({"method":"subscribeMigration"}))

                    now=time.time()
                    seed_cap=2 if FREE_LITE else 20
                    seeds=[
                        c.get("mint") for c in runtime.get("candidates",[])
                        if not c.get("perp_eligible") and c.get("mint")
                    ][:seed_cap]
                    seeds=list(dict.fromkeys(open_spot_mints()+seeds))

                    cap=max(8,i("pulse_max_trade_subscriptions")) if FREE_LITE else max(30,i("pulse_max_trade_subscriptions"))
                    seeds=seeds[:cap]
                    if seeds:
                        await ws.send(json.dumps({"method":"subscribeTokenTrade","keys":seeds}))
                        runtime["ws_subscription_requests"]+=len(seeds)
                        runtime["pulse_subscribed"].update(seeds)
                        for m0 in seeds:
                            runtime["pulse_subscription_birth"][m0]=now

                    sync_task=asyncio.create_task(sync_pulse_subscriptions(ws))

                    async for raw in ws:
                        try:
                            data=json.loads(raw)
                        except Exception:
                            _ws_inc("unknown")
                            continue
                        if not isinstance(data,dict):
                            _ws_inc("unknown")
                            continue

                        mint=str(data.get("mint") or data.get("tokenAddress") or "").strip()
                        tx=str(data.get("txType") or data.get("action") or data.get("type") or "").lower().strip()

                        if len(mint)<30:
                            _ws_capture_provider_message(data)
                            continue

                        is_buy=(tx=="buy") or str(data.get("isBuy","")).lower()=="true"
                        is_sell=(tx=="sell") or str(data.get("isSell","")).lower()=="true"
                        is_migration=tx in ("migration","migrate")
                        is_create=(tx=="create") or (
                            not is_buy and not is_sell and not is_migration
                            and bool(data.get("name") and data.get("symbol"))
                        )

                        if is_create:
                            _ws_inc("create")
                            info=register_launch_token(data)

                            cap=max(8,i("pulse_max_trade_subscriptions")) if FREE_LITE else max(30,i("pulse_max_trade_subscriptions"))
                            if mint not in runtime["pulse_subscribed"]:
                                open_now=set(open_spot_mints())
                                if len(runtime["pulse_subscribed"])>=cap:
                                    evictable=[
                                        m0 for m0 in runtime["pulse_subscribed"]
                                        if m0 not in open_now and m0!=mint
                                    ]
                                    evictable.sort(key=lambda m0:nz(runtime["pulse_subscription_birth"].get(m0)))
                                    need=max(1,len(runtime["pulse_subscribed"])-cap+1)
                                    evict=evictable[:need]
                                    if evict:
                                        await ws.send(json.dumps({"method":"unsubscribeTokenTrade","keys":evict}))
                                        runtime["ws_unsubscription_requests"]+=len(evict)
                                        for em in evict:
                                            runtime["pulse_subscribed"].discard(em)
                                            runtime["pulse_subscription_birth"].pop(em,None)
                                            if em in runtime["launch_watch"] and em not in runtime["realtime_exit_refs"]:
                                                runtime["launch_watch"][em]["status"]="ROTATED"
                                                runtime["launch_watch"][em]["last_reason"]="subscription rotated for newer launch"

                                if len(runtime["pulse_subscribed"])<cap:
                                    await ws.send(json.dumps({"method":"subscribeTokenTrade","keys":[mint]}))
                                    runtime["ws_subscription_requests"]+=1
                                    runtime["pulse_subscribed"].add(mint)
                                    runtime["pulse_subscription_birth"][mint]=time.time()
                                    if info:
                                        info["status"]="SUBSCRIBED"
                                        info["last_reason"]="waiting for first buy/sell"
                                elif info:
                                    info["status"]="WAITING_SLOT"
                                    info["last_reason"]="trade subscription cap full"

                            continue

                        if is_migration:
                            _ws_inc("migration")
                            continue

                        if not (is_buy or is_sell):
                            _ws_inc("unknown")
                            continue

                        if is_buy:
                            _ws_inc("buy")
                        if is_sell:
                            _ws_inc("sell")
                        runtime["ws_last_trade_event"]=time.time()
                        runtime["ws_last_trade_mint"]=mint

                        lm=add_launch_trade(data)
                        if lm:
                            plausible=(
                                int(lm.get("events_2s") or 0)>=2 and
                                int(lm.get("unique_buyers_2s") or 0)>=1 and
                                nz(lm.get("score"))>=55
                            )
                            if plausible and mint not in runtime["launch_evaluating"]:
                                runtime["ws_eval_tasks_created"]+=1
                                asyncio.create_task(evaluate_launch_mint(mint,lm))

                        m=add_pulse_event(data)
                        if not m:
                            continue

                        if mint in runtime["realtime_exit_refs"]:
                            asyncio.create_task(realtime_exit_check(mint,m))

                        ok,_=pulse_gate_metrics(m)
                        if ok and mint not in runtime["pulse_evaluating"]:
                            runtime["ws_eval_tasks_created"]+=1
                            asyncio.create_task(evaluate_pulse_mint(mint,m))

            except asyncio.CancelledError:
                raise
            except Exception as e:
                runtime["pulse_stream_connected"]=False
                runtime["pulse_ws_exception_type"]=type(e).__name__

                response=getattr(e,"response",None)
                status=None
                if response is not None:
                    status=getattr(response,"status_code",None)
                    if status is None:
                        status=getattr(response,"status",None)
                try:
                    status=int(status) if status is not None else None
                except Exception:
                    status=None
                runtime["pulse_ws_http_status"]=status

                safe_headers={}
                headers=getattr(response,"headers",None) if response is not None else None
                if headers is not None:
                    for hn in (
                        "server","date","retry-after","cf-ray",
                        "x-ratelimit-limit","x-ratelimit-remaining","x-ratelimit-reset"
                    ):
                        try:
                            hv=headers.get(hn)
                        except Exception:
                            hv=None
                        if hv is not None:
                            safe_headers[hn]=str(hv)[:200]
                runtime["pulse_ws_response_headers"]=safe_headers

                body=getattr(response,"body",None) if response is not None else None
                if isinstance(body,(bytes,bytearray)):
                    body=body.decode("utf-8","replace")
                if body is not None:
                    body=str(body)
                    if PUMPPORTAL_API_KEY:
                        body=body.replace(PUMPPORTAL_API_KEY,"***REDACTED***")
                    body=body[:1000]
                runtime["pulse_ws_response_body"]=body

                safe_error=str(e)[:600]
                if PUMPPORTAL_API_KEY:
                    safe_error=safe_error.replace(PUMPPORTAL_API_KEY,"***REDACTED***")
                runtime["pulse_stream_error"]=safe_error

                retry_after=None
                try:
                    retry_after=float(safe_headers.get("retry-after"))
                except Exception:
                    retry_after=None

                if status in (400,403):
                    retry_sec=3600
                    runtime["pulse_stream_mode"]=f"REJECTED_HTTP_{status}"
                elif status==401:
                    retry_sec=1800
                    runtime["pulse_stream_mode"]="AUTH_REJECTED"
                elif status==429:
                    retry_sec=max(300,min(3600,int(retry_after or 3600)))
                    runtime["pulse_stream_mode"]="RATE_LIMITED"
                else:
                    retry_sec=backoff
                    runtime["pulse_stream_mode"]="RECONNECTING"

                runtime["pulse_ws_retry_sec"]=retry_sec
                record_event(
                    "WARN","PULSE_STREAM_RECONNECT","Real-time pulse stream reconnecting",
                    {
                        "error":safe_error,
                        "exception_type":runtime["pulse_ws_exception_type"],
                        "http_status":status,
                        "retry_sec":retry_sec,
                        "response_headers":safe_headers,
                        "response_body":body
                    },
                    dedupe_sec=60
                )
                await asyncio.sleep(retry_sec)
                if status not in (400,401,403,429):
                    backoff=min(backoff*2,60)

            finally:
                runtime["pulse_stream_connected"]=False
                if sync_task:
                    sync_task.cancel()
                    try:
                        await sync_task
                    except BaseException:
                        pass

    finally:
        runtime["pulse_stream_connected"]=False
        runtime["pulse_ws_loop_started"]=False
'''

pattern = re.compile(
    r'async def pumpportal_realtime_loop\(\):.*?\n(?=def sniper_gate\(c\):)',
    re.S
)
src, n = pattern.subn(new_ws_block + "\n", src, count=1)
if n != 1:
    raise SystemExit("[NOVA V6.7.1] PumpPortal loop block not found.")

dash_anchor = '''            "events_total":runtime["pulse_events_total"],
            "entries":runtime["pulse_entries"],'''
dash_replacement = '''            "events_total":runtime["pulse_events_total"],
            "message_counts":dict(runtime.get("ws_message_counts",{})),
            "subscription_requests":runtime.get("ws_subscription_requests",0),
            "subscription_errors":runtime.get("ws_trade_subscription_errors",0),
            "last_provider_message":runtime.get("ws_last_provider_message"),
            "last_trade_event_age_sec":round(time.time()-runtime["ws_last_trade_event"],3) if runtime.get("ws_last_trade_event") else None,
            "last_trade_mint":runtime.get("ws_last_trade_mint"),
            "entries":runtime["pulse_entries"],'''
if dash_anchor not in src:
    raise SystemExit("[NOVA V6.7.1] Dashboard realtime anchor not found.")
src = src.replace(dash_anchor, dash_replacement, 1)

diag_anchor = '''        "events_total":runtime.get("pulse_events_total",0),
        "recent_stream_events":recent,'''
diag_replacement = '''        "events_total":runtime.get("pulse_events_total",0),
        "message_counts":dict(runtime.get("ws_message_counts",{})),
        "subscription_requests":runtime.get("ws_subscription_requests",0),
        "unsubscription_requests":runtime.get("ws_unsubscription_requests",0),
        "trade_subscription_errors":runtime.get("ws_trade_subscription_errors",0),
        "last_provider_message":runtime.get("ws_last_provider_message"),
        "last_trade_event_age_sec":round(time.time()-runtime["ws_last_trade_event"],3) if runtime.get("ws_last_trade_event") else None,
        "last_trade_mint":runtime.get("ws_last_trade_mint"),
        "launch_trades_seen":runtime.get("launch_trades_seen",0),
        "recent_stream_events":recent,'''
if diag_anchor not in src:
    raise SystemExit("[NOVA V6.7.1] Diagnostic endpoint anchor not found.")
src = src.replace(diag_anchor, diag_replacement, 1)

src = src.replace("/6.7.0", "/6.7.1")
compile(src, str(APP_PATH), "exec")
APP_PATH.write_text(src, encoding="utf-8")
print("[NOVA V6.7.1] Launch/trade-stream hotfix applied and syntax-validated.")
