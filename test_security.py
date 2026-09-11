import os

os.environ["NOVA_ADMIN_KEY"] = "test-admin-key-very-long"
os.environ["NOVA_ALLOWED_ORIGINS"] = "https://dashboard.example.com"
os.environ["DATABASE_URL"] = "sqlite:////tmp/nova-security-test.db"
try:
    os.remove("/tmp/nova-security-test.db")
except FileNotFoundError:
    pass

from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

assert client.get("/health").status_code == 200
assert client.get("/api/dashboard").status_code in (401, 403)
assert client.get("/api/diagnostics/pumpportal").status_code in (401, 403)
headers = {"X-NOVA-Key": "test-admin-key-very-long"}
assert client.post("/api/mode/LIVE", headers=headers).status_code == 403
assert client.post("/api/mode/INVALID", headers=headers).status_code == 400
assert client.post("/api/control/not-a-real-action", headers=headers).status_code == 400
dashboard = client.get("/api/dashboard", headers=headers)
assert dashboard.status_code == 200
payload = dashboard.json()
profile = payload["realtime_pulse"]["profit_cycle"]["micro_profit"]
assert profile["unlimited_profit"] is True
assert profile["daily_loss_limit_pct"] == 10.0
assert profile["per_trade_risk_pct"] == 0.35
print("security smoke tests: OK")
