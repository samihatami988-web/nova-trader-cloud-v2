from pathlib import Path
import re
import sys

APP_PATH = Path("/app/app.py")
if not APP_PATH.exists():
    APP_PATH = Path("app.py")

src = APP_PATH.read_text(encoding="utf-8")

if 'APP_VERSION = "6.7.0"' in src:
    print("[NOVA V6.7.0] app.py already finalized.")
    raise SystemExit(0)

def replace_once(old: str, new: str, label: str):
    global src
    if old not in src:
        raise RuntimeError(f"anchor not found: {label}")
    src = src.replace(old, new, 1)

try:
    src, n = re.subn(
        r'APP_VERSION\s*=\s*"6\.6\.(?:1|2(?:-DIAGNOSTIC)?)"',
        'APP_VERSION = "6.7.0"',
        src,
        count=1
    )
    if n != 1:
        raise RuntimeError("version anchor not found")

    replace_once(
        'from typing import Optional',
        'from typing import Optional\nfrom urllib.parse import quote',
        "urllib import"
    )

    replace_once(
        'PUMPPORTAL_API_KEY = os.getenv("PUMPPORTAL_API_KEY","").strip()',
        '''PUMPPORTAL_API_KEY_RAW = os.getenv("PUMPPORTAL_API_KEY","")
PUMPPORTAL_API_KEY = PUMPPORTAL_API_KEY_RAW.strip()
if (
    len(PUMPPORTAL_API_KEY) >= 2
    and PUMPPORTAL_API_KEY[0] in ('"', "'")
    and PUMPPORTAL_API_KEY[-1] == PUMPPORTAL_API_KEY[0]
):
    PUMPPORTAL_API_KEY = PUMPPORTAL_API_KEY[1:-1].strip()''',
        "API key normalization"
    )

    replace_once(
        '''    "pulse_stream_connected": False,
    "pulse_stream_mode": "OFF",
    "pulse_stream_error": None,
    "pulse_last_event": 0,''',
        '''    "pulse_stream_connected": False,
    "pulse_stream_mode": "OFF",
    "pulse_stream_error": None,
    "pulse_ws_loop_started": False,
    "pulse_ws_attempts": 0,
    "pulse_ws_last_attempt": None,
    "pulse_ws_last_connected": None,
    "pulse_ws_http_status": None,
    "pulse_ws_exception_type": None,
    "pulse_ws_retry_sec": None,
    "pulse_ws_response_headers": {},
    "pulse_ws_response_body": None,
    "pulse_last_event": 0,''',
        "runtime websocket telemetry"
    )

    new_loop = r'''async def pumpportal_realtime_loop():
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
                    seed_cap=4 if FREE_LITE else 30
                    seeds=[
                        c.get("mint") for c in runtime.get("candidates",[])
                        if not c.get("perp_eligible") and c.get("mint")
                    ][:seed_cap]
                    seeds=list(dict.fromkeys(open_spot_mints()+seeds))

                    if seeds:
                        await ws.send(json.dumps({"method":"subscribeTokenTrade","keys":seeds}))
                        runtime["pulse_subscribed"].update(seeds)
                        for m in seeds:
                            runtime["pulse_subscription_birth"][m]=now

                    sync_task=asyncio.create_task(sync_pulse_subscriptions(ws))

                    async for raw in ws:
                        try:
                            data=json.loads(raw)
                        except Exception:
                            continue
                        if not isinstance(data,dict):
                            continue

                        mint=str(data.get("mint") or data.get("tokenAddress") or "").strip()
                        if len(mint)<30:
                            continue

                        tx=str(data.get("txType") or data.get("action") or data.get("type") or "").lower()
                        is_create=(tx=="create") or bool(data.get("name") and data.get("symbol"))

                        if is_create:
                            register_launch_token(data)

                            active=[
                                (m0,info) for m0,info in runtime["launch_watch"].items()
                                if time.time()-nz(info.get("created_t"))<=f("launch_watch_ttl_sec")
                                and m0 not in runtime["realtime_exit_refs"]
                            ]
                            if len(active)>i("launch_max_active_watch"):
                                active.sort(key=lambda x:nz(x[1].get("created_t")))
                                evict=[x[0] for x in active[:len(active)-i("launch_max_active_watch")]]
                                if evict:
                                    await ws.send(json.dumps({"method":"unsubscribeTokenTrade","keys":evict}))
                                    for em in evict:
                                        runtime["pulse_subscribed"].discard(em)
                                        runtime["pulse_subscription_birth"].pop(em,None)
                                        if em in runtime["launch_watch"]:
                                            runtime["launch_watch"][em]["status"]="EXPIRED"
                                            runtime["launch_watch"][em]["last_reason"]="launch watch capacity"

                            cap=max(8,i("pulse_max_trade_subscriptions")) if FREE_LITE else max(30,i("pulse_max_trade_subscriptions"))
                            if mint not in runtime["pulse_subscribed"] and len(runtime["pulse_subscribed"])<cap:
                                await ws.send(json.dumps({"method":"subscribeTokenTrade","keys":[mint]}))
                                runtime["pulse_subscribed"].add(mint)
                                runtime["pulse_subscription_birth"][mint]=time.time()

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

                        if len(runtime["pulse_subscribed"])>(
                            max(16,i("pulse_max_trade_subscriptions"))+8
                            if FREE_LITE
                            else max(40,i("pulse_max_trade_subscriptions"))+20
                        ):
                            raise RuntimeError("subscription cap recycle")

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

                if len(runtime["pulse_subscribed"])>(
                    max(16,i("pulse_max_trade_subscriptions"))+8
                    if FREE_LITE
                    else max(40,i("pulse_max_trade_subscriptions"))+20
                ):
                    runtime["pulse_subscribed"].clear()
                    runtime["pulse_subscription_birth"].clear()

    finally:
        runtime["pulse_stream_connected"]=False
        runtime["pulse_ws_loop_started"]=False
'''

    pattern = re.compile(
        r'async def pumpportal_realtime_loop\(\):.*?\n(?=def sniper_gate\(c\):)',
        re.S
    )
    src, n = pattern.subn(new_loop + "\n", src, count=1)
    if n != 1:
        raise RuntimeError("PumpPortal loop block not found")

    old_health = '''        "pulse_connected":bool(runtime.get("pulse_stream_connected")),
        "live_execution_locked":LIVE_EXECUTION_LOCKED'''
    new_health = '''        "pulse_connected":bool(runtime.get("pulse_stream_connected")),
        "pulse_mode":runtime.get("pulse_stream_mode"),
        "pulse_error":(
            str(runtime.get("pulse_stream_error") or "").replace(PUMPPORTAL_API_KEY,"***REDACTED***")
            if PUMPPORTAL_API_KEY else str(runtime.get("pulse_stream_error") or "")
        ),
        "pulse_http_status":runtime.get("pulse_ws_http_status"),
        "pulse_exception_type":runtime.get("pulse_ws_exception_type"),
        "pulse_attempts":runtime.get("pulse_ws_attempts",0),
        "pulse_last_attempt":runtime.get("pulse_ws_last_attempt"),
        "pulse_last_connected":runtime.get("pulse_ws_last_connected"),
        "pulse_retry_sec":runtime.get("pulse_ws_retry_sec"),
        "pumpportal_key_present":bool(PUMPPORTAL_API_KEY),
        "pumpportal_key_length":len(PUMPPORTAL_API_KEY),
        "pumpportal_stream_enabled":bool(PUMPPORTAL_TRADE_STREAM_ENABLED),
        "live_execution_locked":LIVE_EXECUTION_LOCKED'''
    replace_once(old_health, new_health, "health diagnostics")

    system_anchor = '''@app.get("/api/system")
def system_status():
    return {"health":source_health(),"events":system_events(50),"mode":operating_mode(),
            "live_execution_locked":LIVE_EXECUTION_LOCKED}

@app.get("/api/security")'''

    diagnostic_endpoint = '''@app.get("/api/system")
def system_status():
    return {"health":source_health(),"events":system_events(50),"mode":operating_mode(),
            "live_execution_locked":LIVE_EXECUTION_LOCKED}

@app.get("/api/diagnostics/pumpportal")
def pumpportal_diagnostics():
    raw=os.getenv("PUMPPORTAL_API_KEY","")
    stripped=raw.strip()

    def redact(value):
        if value is None:
            return None
        text=str(value)
        for secret in (raw,stripped,PUMPPORTAL_API_KEY):
            if secret:
                text=text.replace(secret,"***REDACTED***")
        return text[:1500]

    recent=[
        event for event in system_events(40)
        if str(event.get("code","")).startswith("PULSE_")
    ][:12]

    return {
        "version":APP_VERSION,
        "diagnostic":"PUMPPORTAL_WEBSOCKET",
        "endpoint":PUMPPORTAL_WS_BASE,
        "connected":bool(runtime.get("pulse_stream_connected")),
        "mode":runtime.get("pulse_stream_mode"),
        "stream_enabled":bool(PUMPPORTAL_TRADE_STREAM_ENABLED),
        "api_key_present":bool(PUMPPORTAL_API_KEY),
        "api_key_length":len(PUMPPORTAL_API_KEY),
        "env_has_outer_whitespace":raw != raw.strip(),
        "env_looks_quoted":(
            len(stripped)>=2
            and stripped[0] in ('"',"'")
            and stripped[-1]==stripped[0]
        ),
        "attempts":runtime.get("pulse_ws_attempts",0),
        "last_attempt":runtime.get("pulse_ws_last_attempt"),
        "last_connected":runtime.get("pulse_ws_last_connected"),
        "http_status":runtime.get("pulse_ws_http_status"),
        "exception_type":runtime.get("pulse_ws_exception_type"),
        "retry_sec":runtime.get("pulse_ws_retry_sec"),
        "last_error":redact(runtime.get("pulse_stream_error")),
        "response_headers":runtime.get("pulse_ws_response_headers",{}),
        "response_body":redact(runtime.get("pulse_ws_response_body")),
        "subscribed_tokens":len(runtime.get("pulse_subscribed",set())),
        "events_total":runtime.get("pulse_events_total",0),
        "recent_stream_events":recent,
        "provider_requirements":{
            "single_websocket_connection":True,
            "token_trade_wallet_min_sol":0.02,
            "token_trade_metered":True
        },
        "live_execution_locked":LIVE_EXECUTION_LOCKED,
        "secret_values_returned":False
    }

@app.get("/api/security")'''

    replace_once(system_anchor, diagnostic_endpoint, "diagnostic endpoint")

    src = src.replace("/6.6.1", "/6.7.0")

    compile(src, str(APP_PATH), "exec")

except Exception as exc:
    print(f"[NOVA V6.7.0] FINALIZATION FAILED: {exc}", flush=True)
    raise SystemExit(1)

APP_PATH.write_text(src, encoding="utf-8")
print("[NOVA V6.7.0] Final app.py generated and syntax-validated.", flush=True)
