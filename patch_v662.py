from pathlib import Path
import sys

APP_PATH = Path("/app/app.py")
if not APP_PATH.exists():
    APP_PATH = Path("app.py")

original = APP_PATH.read_text(encoding="utf-8")

if 'APP_VERSION = "6.6.2-DIAGNOSTIC"' in original:
    print("[V6.6.2] Diagnostic patch already applied.")
    raise SystemExit(0)

src = original

def replace_once(old: str, new: str, label: str):
    global src
    if old not in src:
        raise RuntimeError(f"[V6.6.2] Patch anchor not found: {label}")
    src = src.replace(old, new, 1)

try:
    replace_once(
        'APP_VERSION = "6.6.1"',
        'APP_VERSION = "6.6.2-DIAGNOSTIC"',
        "version"
    )

    replace_once(
        '''    "pulse_stream_error": None,
    "pulse_last_event": 0,''',
        '''    "pulse_stream_error": None,
    "pulse_diag_attempts": 0,
    "pulse_diag_last_attempt": None,
    "pulse_diag_http_status": None,
    "pulse_diag_exception_type": None,
    "pulse_diag_retry_sec": None,
    "pulse_diag_response_headers": {},
    "pulse_diag_response_body": None,
    "pulse_last_event": 0,''',
        "runtime diagnostic fields"
    )

    replace_once(
        '''        try:
            async with websockets.connect(
                uri,ping_interval=20,ping_timeout=20,close_timeout=5,max_size=2_000_000
            ) as ws:''',
        '''        try:
            runtime["pulse_diag_attempts"] = int(runtime.get("pulse_diag_attempts", 0)) + 1
            runtime["pulse_diag_last_attempt"] = datetime.now(timezone.utc).isoformat()
            runtime["pulse_diag_http_status"] = None
            runtime["pulse_diag_exception_type"] = None
            runtime["pulse_diag_response_headers"] = {}
            runtime["pulse_diag_response_body"] = None

            async with websockets.connect(
                uri,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
                open_timeout=12,
                max_size=2_000_000
            ) as ws:''',
        "websocket attempt instrumentation"
    )

    replace_once(
        '''                runtime["pulse_stream_connected"]=True
                runtime["pulse_stream_mode"]="PUMPPORTAL_REALTIME"
                runtime["pulse_stream_error"]=None
                backoff=2''',
        '''                runtime["pulse_stream_connected"]=True
                runtime["pulse_stream_mode"]="PUMPPORTAL_REALTIME"
                runtime["pulse_stream_error"]=None
                runtime["pulse_diag_http_status"]=101
                runtime["pulse_diag_exception_type"]=None
                runtime["pulse_diag_retry_sec"]=0
                runtime["pulse_diag_response_headers"]={}
                runtime["pulse_diag_response_body"]=None
                backoff=2''',
        "websocket success instrumentation"
    )

    replace_once(
        '''        except Exception as e:
            runtime["pulse_stream_connected"]=False
            runtime["pulse_stream_error"]=str(e)[:220]
            record_event(
                "WARN","PULSE_STREAM_RECONNECT","Real-time pulse stream reconnecting",
                {"error":runtime["pulse_stream_error"]},dedupe_sec=60
            )
            await asyncio.sleep(backoff)
            backoff=min(backoff*2,30)''',
        '''        except Exception as e:
            runtime["pulse_stream_connected"]=False
            runtime["pulse_stream_error"]=str(e)[:500]
            runtime["pulse_diag_exception_type"]=type(e).__name__

            response=getattr(e,"response",None)
            status=getattr(response,"status_code",None) if response is not None else None
            if status is None and response is not None:
                status=getattr(response,"status",None)
            try:
                status=int(status) if status is not None else None
            except Exception:
                status=None
            runtime["pulse_diag_http_status"]=status

            safe_headers={}
            headers=getattr(response,"headers",None) if response is not None else None
            if headers is not None:
                for header_name in (
                    "server","date","retry-after","cf-ray",
                    "x-ratelimit-limit","x-ratelimit-remaining","x-ratelimit-reset"
                ):
                    try:
                        header_value=headers.get(header_name)
                    except Exception:
                        header_value=None
                    if header_value is not None:
                        safe_headers[header_name]=str(header_value)[:200]
            runtime["pulse_diag_response_headers"]=safe_headers

            body=getattr(response,"body",None) if response is not None else None
            if isinstance(body,(bytes,bytearray)):
                body=body.decode("utf-8","replace")
            if body is not None:
                body=str(body)
                if PUMPPORTAL_API_KEY:
                    body=body.replace(PUMPPORTAL_API_KEY,"***REDACTED***")
                body=body[:700]
            runtime["pulse_diag_response_body"]=body

            if status==400:
                retry_sec=60
            elif status==429:
                retry_sec=300
            else:
                retry_sec=backoff
            runtime["pulse_diag_retry_sec"]=retry_sec

            safe_error=runtime["pulse_stream_error"]
            if PUMPPORTAL_API_KEY:
                safe_error=safe_error.replace(PUMPPORTAL_API_KEY,"***REDACTED***")

            record_event(
                "WARN","PULSE_STREAM_RECONNECT","Real-time pulse stream reconnecting",
                {
                    "error":safe_error,
                    "exception_type":runtime["pulse_diag_exception_type"],
                    "http_status":status,
                    "retry_sec":retry_sec,
                    "response_headers":safe_headers,
                    "response_body":body
                },
                dedupe_sec=30
            )
            await asyncio.sleep(retry_sec)
            backoff=min(backoff*2,30)''',
        "websocket exception diagnostics"
    )

    replace_once(
        '''        "pulse_connected":bool(runtime.get("pulse_stream_connected")),
        "live_execution_locked":LIVE_EXECUTION_LOCKED''',
        '''        "pulse_connected":bool(runtime.get("pulse_stream_connected")),
        "pulse_mode":runtime.get("pulse_stream_mode"),
        "pulse_error":(
            str(runtime.get("pulse_stream_error") or "").replace(PUMPPORTAL_API_KEY,"***REDACTED***")
            if PUMPPORTAL_API_KEY else str(runtime.get("pulse_stream_error") or "")
        ),
        "pulse_http_status":runtime.get("pulse_diag_http_status"),
        "pulse_exception_type":runtime.get("pulse_diag_exception_type"),
        "pulse_attempts":runtime.get("pulse_diag_attempts",0),
        "pulse_last_attempt":runtime.get("pulse_diag_last_attempt"),
        "pulse_retry_sec":runtime.get("pulse_diag_retry_sec"),
        "pumpportal_key_present":bool(PUMPPORTAL_API_KEY),
        "pumpportal_key_length":len(PUMPPORTAL_API_KEY),
        "pumpportal_stream_enabled":bool(PUMPPORTAL_TRADE_STREAM_ENABLED),
        "live_execution_locked":LIVE_EXECUTION_LOCKED''',
        "health diagnostics"
    )

    replace_once(
        '''@app.get("/api/system")
def system_status():
    return {"health":source_health(),"events":system_events(50),"mode":operating_mode(),
            "live_execution_locked":LIVE_EXECUTION_LOCKED}

@app.get("/api/security")''',
        '''@app.get("/api/system")
def system_status():
    return {"health":source_health(),"events":system_events(50),"mode":operating_mode(),
            "live_execution_locked":LIVE_EXECUTION_LOCKED}

@app.get("/api/diagnostics/pumpportal")
def pumpportal_diagnostics():
    raw_key=os.getenv("PUMPPORTAL_API_KEY","")
    stripped_key=raw_key.strip()

    def redact(value):
        if value is None:
            return None
        text=str(value)
        for secret in (raw_key,stripped_key,PUMPPORTAL_API_KEY):
            if secret:
                text=text.replace(secret,"***REDACTED***")
        return text[:1200]

    recent=[
        event for event in system_events(30)
        if str(event.get("code","")).startswith("PULSE_STREAM")
    ][:10]

    return {
        "version":APP_VERSION,
        "diagnostic":"PUMPPORTAL_WEBSOCKET",
        "free_lite":FREE_LITE,
        "ws_endpoint":PUMPPORTAL_WS_BASE,
        "stream_enabled":bool(PUMPPORTAL_TRADE_STREAM_ENABLED),
        "api_key_present":bool(stripped_key),
        "api_key_length":len(stripped_key),
        "api_key_has_outer_whitespace":raw_key != stripped_key,
        "api_key_looks_quoted":(
            len(stripped_key)>=2 and
            stripped_key[0] in ('"',"'") and
            stripped_key[-1]==stripped_key[0]
        ),
        "connected":bool(runtime.get("pulse_stream_connected")),
        "mode":runtime.get("pulse_stream_mode"),
        "last_error":redact(runtime.get("pulse_stream_error")),
        "exception_type":runtime.get("pulse_diag_exception_type"),
        "http_status":runtime.get("pulse_diag_http_status"),
        "attempts":runtime.get("pulse_diag_attempts",0),
        "last_attempt":runtime.get("pulse_diag_last_attempt"),
        "retry_sec":runtime.get("pulse_diag_retry_sec"),
        "response_headers":runtime.get("pulse_diag_response_headers",{}),
        "response_body":redact(runtime.get("pulse_diag_response_body")),
        "recent_stream_events":recent,
        "live_execution_locked":LIVE_EXECUTION_LOCKED,
        "secrets_exposed":False
    }

@app.get("/api/security")''',
        "pumpportal diagnostic endpoint"
    )

    compile(src, str(APP_PATH), "exec")

except Exception as exc:
    print(f"[V6.6.2] DIAGNOSTIC PATCH FAILED: {exc}", flush=True)
    raise SystemExit(1)

APP_PATH.write_text(src, encoding="utf-8")
print("[V6.6.2] Diagnostic patch applied successfully.", flush=True)
