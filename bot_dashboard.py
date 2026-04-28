import json
import os
from pathlib import Path

import requests
import streamlit as st


BOT_URL = os.getenv("BITRUE_BOT_URL", "http://127.0.0.1:8000")
LOG_PATH = Path("data/bot_events.jsonl")
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XLMUSDT", "XRPUSDT", "SHIBUSDT"]
SIGNALS = ["SSB30", "DREAM", "S", "H-S"]
TIMEFRAMES = ["1D", "3D"]


st.set_page_config(page_title="Bitrue Bot Control", layout="wide")


def api_get(path):
    response = requests.get(f"{BOT_URL}{path}", timeout=5)
    response.raise_for_status()
    return response.json()


def api_post(path, payload=None):
    response = requests.post(f"{BOT_URL}{path}", json=payload or {}, timeout=10)
    response.raise_for_status()
    return response.json()


def read_recent_logs(limit=25):
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"raw": line})
    return list(reversed(rows))


def infer_action(signal):
    return "sell" if signal in {"S", "H-S"} else "buy"


st.title("Bitrue Bot Control")
st.caption("Local control panel for the dry-run Bitrue spot bot.")

with st.sidebar:
    st.subheader("Connection")
    st.write(f"Bot API: `{BOT_URL}`")
    st.write("Run the bot first with your normal startup command.")
    if st.button("Refresh"):
        st.rerun()

try:
    health = api_get("/health")
    control = api_get("/control")
    bot_online = True
except Exception as exc:
    health = {"status": "offline", "mode": "unknown", "error": str(exc)}
    control = {"kill_switch": None, "disabled_symbols": [], "notes": ""}
    bot_online = False

status_col, mode_col, kill_col = st.columns(3)
status_col.metric("Status", health.get("status", "unknown"))
mode_col.metric("Mode", health.get("mode", "unknown"))
kill_col.metric("Kill Switch", str(control.get("kill_switch")))

if not bot_online:
    st.error(f"Bot API is not reachable: {health.get('error')}")
    st.stop()

st.divider()

st.subheader("Runtime Control")
control_col1, control_col2, control_col3 = st.columns([1, 1, 2])

with control_col1:
    if st.button("Kill Switch ON", type="primary"):
        result = api_post("/control", {"kill_switch": True, "notes": "enabled from dashboard"})
        st.success(result)
        st.rerun()

with control_col2:
    if st.button("Kill Switch OFF"):
        result = api_post("/control", {"kill_switch": False, "notes": "disabled from dashboard"})
        st.success(result)
        st.rerun()

with control_col3:
    disabled_symbols = st.multiselect(
        "Disabled Symbols",
        SYMBOLS,
        default=control.get("disabled_symbols", []),
    )
    if st.button("Save Disabled Symbols"):
        result = api_post("/control", {"disabled_symbols": disabled_symbols, "notes": "updated from dashboard"})
        st.success(result)
        st.rerun()

st.divider()

st.subheader("Positions")
positions_col1, positions_col2 = st.columns([1, 5])
with positions_col1:
    if st.button("Reconcile Positions"):
        st.json(api_post("/reconcile"))
with positions_col2:
    positions = api_get("/positions")
    st.json(positions)

st.divider()

st.subheader("Send Local Test Alert")
with st.form("test_alert_form"):
    form_col1, form_col2, form_col3, form_col4 = st.columns(4)
    symbol = form_col1.selectbox("Symbol", SYMBOLS)
    signal = form_col2.selectbox("Signal", SIGNALS)
    timeframe = form_col3.selectbox("Timeframe", TIMEFRAMES)
    price = form_col4.text_input("Price", value="55000")
    secret = st.text_input("Webhook Secret", value=os.getenv("BITRUE_WEBHOOK_SECRET", ""), type="password")
    submitted = st.form_submit_button("Send Test Alert")

if submitted:
    payload = {
        "symbol": symbol,
        "action": infer_action(signal),
        "signal": signal,
        "secret": secret,
        "price": price,
        "timeframe": timeframe,
        "strategy": "MRL Slim",
        "timestamp": "dashboard-test",
    }
    try:
        result = api_post("/webhook/tradingview", payload)
        st.success("Alert sent.")
        st.json(result)
    except Exception as exc:
        st.error(f"Alert failed: {exc}")

st.divider()

st.subheader("Recent Bot Events")
for row in read_recent_logs():
    st.code(json.dumps(row, indent=2), language="json")

