import csv
import json
import os
import re
import time
import concurrent.futures
import hashlib
from datetime import datetime, timedelta, timezone
from io import StringIO
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import requests
import streamlit as st
import yfinance as yf
from streamlit.errors import StreamlitSecretNotFoundError

st.set_page_config(page_title="Market Bias Dashboard", layout="wide")

PUBLIC_MARKET_DEFAULTS_FILE = "default_market_inputs.json"
PUBLIC_ANALYST_DEFAULTS_FILE = "default_analyst_profiles.json"
PUBLIC_NEWS_DEFAULTS_FILE = "default_news_profiles.json"
PUBLIC_CONTEXT_DEFAULTS_FILE = "default_context_profile.json"
DEFAULT_ORACLE_OWNER_EMAIL = "rodster306@gmail.com"

MARKET_INPUT_DEFAULTS = {
    "total_3d_state": "Confirmed Bearish",
    "total_1d_supertrend": "Bearish",
}

WIDGET_STATE_KEYS = {
    "total_3d_state": "ui_total_3d_state",
    "total_1d_supertrend": "ui_total_1d_supertrend",
    "manual_etf_enabled": "ui_manual_etf_enabled",
    "manual_btc_etf_flow": "ui_manual_btc_etf_flow",
    "manual_eth_etf_flow": "ui_manual_eth_etf_flow",
}

ANALYST_DEFAULTS = {
    "analyst1_name": "Analyst 1",
    "analyst1_bias": "Neutral",
    "analyst1_conf": 70,
    "analyst1_weight": 1.0,
    "analyst1_timeframe": "Swing",
    "analyst1_notes": "",
    "analyst2_name": "Analyst 2",
    "analyst2_bias": "Neutral",
    "analyst2_conf": 60,
    "analyst2_weight": 1.0,
    "analyst2_timeframe": "Swing",
    "analyst2_notes": "",
    "analyst3_name": "Analyst 3",
    "analyst3_bias": "Neutral",
    "analyst3_conf": 50,
    "analyst3_weight": 1.0,
    "analyst3_timeframe": "Swing",
    "analyst3_notes": "",
}
NEWS_DEFAULTS = {
    "news1_headline": "ETF inflows rise",
    "news1_direction": "Bullish",
    "news1_impact": 4,
    "news1_category": "ETF / Institutional",
    "news1_notes": "",
    "news2_headline": "Geopolitical tensions rise",
    "news2_direction": "Bearish",
    "news2_impact": 3,
    "news2_category": "Geopolitics",
    "news2_notes": "",
    "news3_headline": "Stablecoin bill advances",
    "news3_direction": "Bullish",
    "news3_impact": 5,
    "news3_category": "Stablecoins",
    "news3_notes": "",
}
CONTEXT_DEFAULTS = {
    "manual_etf_enabled": True,
    "manual_btc_etf_flow": 0.0,
    "manual_eth_etf_flow": 0.0,
    "astro_lunar_event": "None",
    "astro_transits": "Sun trine Jupiter, Mercury conjunct Venus",
    "astro_market_theme": "Expansion",
    "share_video": "Paste a video link or short title",
    "share_article": "Paste an article link or short title",
    "share_why": "Explain why this content matters right now.",
    "share_takeaway": "Explain how this may connect to crypto, macro, or geopolitics.",
}
SUPABASE_SCHEMA_HINT = "Run supabase_schema.sql in your Supabase SQL editor before using cloud saves."
FEED_CACHE_DIR = os.path.join("data", "feed_cache")
DEFAULT_FEED_CACHE_TTL_SECONDS = 60 * 30
DEFAULT_FEED_STALE_TTL_SECONDS = 60 * 60 * 24
EXTERNAL_FETCH_TIMEOUT_SECONDS = 6
EXTERNAL_SIGNAL_CACHE_TTL_SECONDS = 60 * 5
SIGNAL_SECTION_CACHE_TTL_SECONDS = 60 * 30
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
TA_WEIGHT = 0.30
ANALYST_WEIGHT = 0.25
NEWS_WEIGHT = 0.10
MACRO_WEIGHT = 0.25
SENTIMENT_WEIGHT = 0.10
SENTIMENT_FNG_WEIGHT = 0.60
SENTIMENT_OPEN_INTEREST_WEIGHT = 0.40
SELL_SIGNAL_ASSETS = [
    ("BTCUSDT", "BTC / USDT"),
    ("ETHUSDT", "ETH / USDT"),
    ("XRPUSDT", "XRP / USDT"),
    ("XLMUSDT", "XLM / USDT"),
    ("BCHUSDT", "BCH / USDT"),
    ("SOLUSDT", "SOL / USDT"),
    ("LINKUSDT", "LINK / USDT"),
    ("XTZUSDT", "XTZ / USDT"),
    ("LTCUSDT", "LTC / USDT"),
    ("ONDOUSDT", "ONDO / USDT"),
    ("HBARUSDT", "HBAR / USDT"),
    ("ZECUSDT", "ZCASH / USDT"),
    ("ADAUSDT", "ADA / USDT"),
    ("AVAXUSDT", "AVAX / USDT"),
    ("DOGEUSDT", "DOGE / USDT"),
    ("HYPEUSDT", "HYPE / USDT"),
    ("POLUSDT", "POL / USDT"),
    ("ALGOUSDT", "ALGO / USDT"),
    ("ATOMUSDT", "COSMOS / USDT"),
    ("SHIBUSDT", "SHIB / USDT"),
    ("LUNCUSDT", "LUNC / USDT"),
]
SELL_SIGNAL_COINGECKO_IDS = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "XRPUSDT": "ripple",
    "XLMUSDT": "stellar",
    "BCHUSDT": "bitcoin-cash",
    "SOLUSDT": "solana",
    "LINKUSDT": "chainlink",
    "XTZUSDT": "tezos",
    "LTCUSDT": "litecoin",
    "ONDOUSDT": "ondo-finance",
    "HBARUSDT": "hedera-hashgraph",
    "ZECUSDT": "zcash",
    "ADAUSDT": "cardano",
    "AVAXUSDT": "avalanche-2",
    "DOGEUSDT": "dogecoin",
    "HYPEUSDT": "hyperliquid",
    "POLUSDT": "polygon-ecosystem-token",
    "ALGOUSDT": "algorand",
    "ATOMUSDT": "cosmos",
    "SHIBUSDT": "shiba-inu",
    "LUNCUSDT": "terra-luna-classic",
}
DEFAULT_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}


def get_secret(name):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except StreamlitSecretNotFoundError:
        pass
    return os.getenv(name)


def get_coingecko_headers():
    headers = dict(DEFAULT_HTTP_HEADERS)
    api_key = get_secret("COINGECKO_API_KEY")
    if api_key:
        headers["x-cg-pro-api-key"] = api_key
    return headers


def feed_cache_path(feed_key):
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", feed_key)
    return os.path.join(FEED_CACHE_DIR, f"{safe_key}.json")


def load_feed_cache(feed_key):
    path = feed_cache_path(feed_key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        cached_at = float(payload["cached_at"])
        data = payload["data"]
        age_seconds = max(0.0, time.time() - cached_at)
        return data, age_seconds
    except (OSError, ValueError, KeyError, TypeError):
        return None


def load_public_defaults(file_path, fallback_defaults):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return {**fallback_defaults, **payload}
        except (OSError, ValueError, TypeError):
            pass
    return dict(fallback_defaults)


def save_public_defaults(file_path, payload):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def seed_session_defaults(defaults):
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def save_feed_cache(feed_key, data):
    os.makedirs(FEED_CACHE_DIR, exist_ok=True)
    with open(feed_cache_path(feed_key), "w", encoding="utf-8") as f:
        json.dump({"cached_at": time.time(), "data": data}, f, indent=2)


def get_feed_result(feed_key, fetcher, cache_ttl_seconds=DEFAULT_FEED_CACHE_TTL_SECONDS, stale_ttl_seconds=DEFAULT_FEED_STALE_TTL_SECONDS):
    cached = load_feed_cache(feed_key)
    if cached:
        cached_data, cached_age_seconds = cached
        if cached_age_seconds <= cache_ttl_seconds:
            cached_copy = dict(cached_data)
            cached_copy["cached"] = True
            cached_copy["cache_age_seconds"] = cached_age_seconds
            return cached_copy

    result = fetcher()
    if result.get("available"):
        result["cached"] = False
        result["cache_age_seconds"] = 0.0
        save_feed_cache(feed_key, result)
        return result

    if cached:
        cached_data, cached_age_seconds = cached
        if cached_age_seconds <= stale_ttl_seconds:
            cached_copy = dict(cached_data)
            cached_copy["cached"] = True
            cached_copy["cache_age_seconds"] = cached_age_seconds
            cached_copy["stale"] = True
            cached_copy["live_error"] = result.get("error")
            cached_copy["error"] = f"Using cached value because live fetch failed: {result.get('error', 'unknown error')}"
            return cached_copy

    result["cached"] = False
    result["cache_age_seconds"] = None
    return result


def get_supabase_config():
    return {
        "url": get_secret("SUPABASE_URL"),
        "anon_key": get_secret("SUPABASE_ANON_KEY"),
    }


def get_oracle_owner_email():
    value = get_secret("ORACLE_OWNER_EMAIL")
    if value:
        return value.strip().lower()
    return DEFAULT_ORACLE_OWNER_EMAIL


def is_oracle_owner():
    owner_email = get_oracle_owner_email()
    current_email = str(current_user().get("email", "")).strip().lower()
    return bool(owner_email and current_email and current_email == owner_email)


def get_openai_config():
    return {
        "api_key": get_secret("OPENAI_API_KEY"),
        "model": get_secret("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
    }


def has_openai_config():
    return bool(get_openai_config()["api_key"])


def has_supabase_config():
    config = get_supabase_config()
    return bool(config["url"] and config["anon_key"])


def init_auth_state():
    st.session_state.setdefault("auth_access_token", None)
    st.session_state.setdefault("auth_refresh_token", None)
    st.session_state.setdefault("auth_user", None)
    st.session_state.setdefault("post_login_loading", False)
    st.session_state.setdefault("pending_session_payload", None)
    st.session_state.setdefault("pending_session_notice", None)
    st.session_state.setdefault("market_inputs_loaded_user_id", None)
    st.session_state.setdefault("market_inputs_last_saved", None)
    st.session_state.setdefault("context_loaded_user_id", None)
    st.session_state.setdefault("context_last_saved", None)
    st.session_state.setdefault("dashboard_loaded_user_id", None)
    st.session_state.setdefault("saved_dashboard_snapshot", None)
    st.session_state.setdefault("session_event_logged", False)


def clear_auth_state():
    st.session_state["auth_access_token"] = None
    st.session_state["auth_refresh_token"] = None
    st.session_state["auth_user"] = None
    st.session_state["post_login_loading"] = False
    st.session_state["pending_session_payload"] = None
    st.session_state["pending_session_notice"] = None
    st.session_state["market_inputs_loaded_user_id"] = None
    st.session_state["market_inputs_last_saved"] = None
    st.session_state["context_loaded_user_id"] = None
    st.session_state["context_last_saved"] = None
    st.session_state["dashboard_loaded_user_id"] = None
    st.session_state["saved_dashboard_snapshot"] = None
    st.session_state["session_event_logged"] = False


def get_auth_headers(include_auth=True):
    config = get_supabase_config()
    headers = {
        "apikey": config["anon_key"],
        "Content-Type": "application/json",
    }
    if include_auth and st.session_state.get("auth_access_token"):
        headers["Authorization"] = f"Bearer {st.session_state['auth_access_token']}"
    return headers


def parse_api_error(response):
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return payload.get("msg") or payload.get("message") or payload.get("error_description") or payload.get("error") or response.text


def supabase_request(method, path, *, json_body=None, include_auth=True, params=None, prefer=None):
    config = get_supabase_config()
    try:
        response = requests.request(
            method,
            f"{config['url'].rstrip('/')}{path}",
            headers={**get_auth_headers(include_auth=include_auth), **({"Prefer": prefer} if prefer else {})},
            json=json_body,
            params=params,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error contacting Supabase: {exc}") from exc
    if response.ok:
        if not response.text:
            return {}
        try:
            return response.json()
        except ValueError:
            return {}
    raise RuntimeError(parse_api_error(response))


def apply_auth_payload(payload):
    st.session_state["auth_access_token"] = payload.get("access_token")
    st.session_state["auth_refresh_token"] = payload.get("refresh_token")
    st.session_state["auth_user"] = payload.get("user")
    st.session_state["post_login_loading"] = True


def sign_up_user(email, password):
    return supabase_request(
        "POST",
        "/auth/v1/signup",
        json_body={"email": email, "password": password},
        include_auth=False,
    )


def sign_in_user(email, password):
    payload = supabase_request(
        "POST",
        "/auth/v1/token",
        json_body={"email": email, "password": password},
        include_auth=False,
        params={"grant_type": "password"},
    )
    apply_auth_payload(payload)
    return payload


def sign_out_user():
    if st.session_state.get("auth_access_token"):
        try:
            supabase_request("POST", "/auth/v1/logout", json_body={}, include_auth=True)
        except RuntimeError:
            pass
    clear_auth_state()


def current_user():
    return st.session_state.get("auth_user") or {}


def current_user_id():
    return current_user().get("id")


def collect_session_payload(defaults):
    return {key: st.session_state.get(key, value) for key, value in defaults.items()}


def hydrate_session_payload(payload):
    for key, value in payload.items():
        st.session_state[key] = value


def sanitize_context_payload(payload):
    return {key: value for key, value in payload.items() if key in CONTEXT_DEFAULTS}


def get_dashboard_payload_defaults():
    return {**MARKET_INPUT_DEFAULTS, **ANALYST_DEFAULTS, **NEWS_DEFAULTS, **CONTEXT_DEFAULTS}


def queue_session_payload(payload, notice=None):
    queued_payload = dict(payload)
    for model_key, widget_key in WIDGET_STATE_KEYS.items():
        if model_key in payload:
            queued_payload[widget_key] = payload[model_key]
    st.session_state["pending_session_payload"] = queued_payload
    st.session_state["pending_session_notice"] = notice


def apply_pending_session_payload():
    payload = st.session_state.get("pending_session_payload")
    applied_payload = None
    if payload:
        hydrate_session_payload(payload)
        applied_payload = dict(payload)
        st.session_state["pending_session_payload"] = None
    notice = st.session_state.get("pending_session_notice")
    if notice:
        st.sidebar.success(notice)
        st.session_state["pending_session_notice"] = None
    return applied_payload


def sync_widget_state_from_model():
    for model_key, widget_key in WIDGET_STATE_KEYS.items():
        if model_key in st.session_state and widget_key not in st.session_state:
            st.session_state[widget_key] = st.session_state[model_key]


def sync_model_state_from_widgets():
    for model_key, widget_key in WIDGET_STATE_KEYS.items():
        if widget_key in st.session_state:
            st.session_state[model_key] = st.session_state[widget_key]


def save_profile_to_supabase(profile_key, payload):
    if not current_user_id():
        raise RuntimeError("Please sign in before saving.")
    supabase_request(
        "POST",
        "/rest/v1/user_dashboards",
        json_body={
            "user_id": current_user_id(),
            "profile_key": profile_key,
            "payload": payload,
        },
        prefer="resolution=merge-duplicates,return=minimal",
    )


def log_user_event(event_name, details=None):
    if not current_user_id():
        return
    try:
        supabase_request(
            "POST",
            "/rest/v1/user_events",
            json_body={
                "user_id": current_user_id(),
                "event_name": event_name,
                "event_details": details or {},
            },
            prefer="return=minimal",
        )
    except RuntimeError:
        return


def load_profile_from_supabase(profile_key):
    if not current_user_id():
        raise RuntimeError("Please sign in before loading.")
    rows = supabase_request(
        "GET",
        "/rest/v1/user_dashboards",
        params={
            "select": "payload",
            "user_id": f"eq.{current_user_id()}",
            "profile_key": f"eq.{profile_key}",
            "limit": 1,
        },
    )
    if not rows:
        return None
    return rows[0].get("payload")


def render_auth_gate():
    st.markdown(
        """
        <div style="max-width:760px;margin:40px auto;padding:28px;border:1px solid rgba(153,27,27,0.18);border-radius:24px;background:#fffdfb;box-shadow:0 18px 40px rgba(28,25,23,0.08);">
            <div style="font-size:34px;font-weight:800;color:#1c1917;margin-bottom:10px;">Market Bias Dashboard</div>
            <div style="font-size:16px;color:#6b625c;line-height:1.6;">
                Create an account or sign in to access your dashboard and save your analyst and news inputs privately.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not has_supabase_config():
        st.error("Supabase is not configured yet.")
        st.info(
            "Add `SUPABASE_URL` and `SUPABASE_ANON_KEY` to Streamlit secrets before enabling registration. "
            + SUPABASE_SCHEMA_HINT
        )
        st.stop()

    sign_in_tab, sign_up_tab = st.tabs(["Sign in", "Create account"])

    with sign_in_tab:
        with st.form("sign_in_form"):
            email = st.text_input("Email", key="sign_in_email")
            password = st.text_input("Password", type="password", key="sign_in_password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            try:
                sign_in_user(email.strip(), password)
            except RuntimeError as exc:
                st.error(f"Sign-in failed: {exc}")
            else:
                st.success("Signed in successfully.")
                log_user_event("sign_in", {"email": email.strip().lower()})
                st.rerun()

    with sign_up_tab:
        with st.form("sign_up_form"):
            email = st.text_input("Email", key="sign_up_email")
            password = st.text_input("Password", type="password", key="sign_up_password")
            confirm_password = st.text_input("Confirm password", type="password", key="sign_up_confirm_password")
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            if len(password) < 8:
                st.error("Use a password with at least 8 characters.")
            elif password != confirm_password:
                st.error("Passwords do not match.")
            else:
                try:
                    payload = sign_up_user(email.strip(), password)
                except RuntimeError as exc:
                    st.error(f"Registration failed: {exc}")
                else:
                    if payload.get("access_token") and payload.get("user"):
                        apply_auth_payload(payload)
                        st.success("Account created. You are now signed in.")
                        st.rerun()
                    else:
                        st.success("Account created. Check your email if confirmation is enabled, then sign in.")

    st.stop()


def save_analysts():
    save_profile_to_supabase("analysts", collect_session_payload(ANALYST_DEFAULTS))


def load_analysts():
    data = load_profile_from_supabase("analysts")
    if data:
        return {**ANALYST_DEFAULTS, **data}
    return False


def save_dashboard():
    payload = collect_session_payload(get_dashboard_payload_defaults())
    save_profile_to_supabase("dashboard_state", payload)
    st.session_state["dashboard_loaded_user_id"] = current_user_id()
    st.session_state["saved_dashboard_snapshot"] = dict(payload)
    st.session_state["market_inputs_last_saved"] = collect_session_payload(MARKET_INPUT_DEFAULTS)
    st.session_state["context_last_saved"] = collect_session_payload(CONTEXT_DEFAULTS)
    if is_oracle_owner():
        save_public_defaults(PUBLIC_MARKET_DEFAULTS_FILE, collect_session_payload(MARKET_INPUT_DEFAULTS))
        save_public_defaults(PUBLIC_ANALYST_DEFAULTS_FILE, collect_session_payload(ANALYST_DEFAULTS))
        save_public_defaults(PUBLIC_NEWS_DEFAULTS_FILE, collect_session_payload(NEWS_DEFAULTS))
        save_public_defaults(PUBLIC_CONTEXT_DEFAULTS_FILE, collect_session_payload(CONTEXT_DEFAULTS))
    log_user_event(
        "save_dashboard",
        {
            "bias_inputs": {
                "total_3d_state": payload.get("total_3d_state"),
                "total_1d_supertrend": payload.get("total_1d_supertrend"),
            },
            "owner_saved_oracle_defaults": is_oracle_owner(),
        },
    )


def load_dashboard():
    data = load_profile_from_supabase("dashboard_state")
    if data:
        return {**get_dashboard_payload_defaults(), **data}
    return False


def save_market_inputs():
    payload = collect_session_payload(MARKET_INPUT_DEFAULTS)
    save_profile_to_supabase("market_inputs", payload)
    st.session_state["market_inputs_last_saved"] = dict(payload)


def load_market_inputs():
    data = load_profile_from_supabase("market_inputs")
    if data:
        return {**MARKET_INPUT_DEFAULTS, **data}
    return False


def save_news():
    save_profile_to_supabase("news", collect_session_payload(NEWS_DEFAULTS))


def load_news():
    data = load_profile_from_supabase("news")
    if data:
        return {**NEWS_DEFAULTS, **data}
    return False


def clear_news():
    return {
        **NEWS_DEFAULTS,
        "news1_notes": "Add news notes here",
        "news2_notes": "Add news notes here ",
        "news3_notes": "Add news notes here  ",
    }


def save_context():
    payload = collect_session_payload(CONTEXT_DEFAULTS)
    save_profile_to_supabase("context", payload)
    st.session_state["context_last_saved"] = dict(payload)


def load_context():
    data = load_profile_from_supabase("context")
    if data:
        return {**CONTEXT_DEFAULTS, **sanitize_context_payload(data)}
    return False


def load_oracle_defaults():
    return {
        **load_public_defaults(PUBLIC_MARKET_DEFAULTS_FILE, MARKET_INPUT_DEFAULTS),
        **load_public_defaults(PUBLIC_ANALYST_DEFAULTS_FILE, ANALYST_DEFAULTS),
        **load_public_defaults(PUBLIC_NEWS_DEFAULTS_FILE, NEWS_DEFAULTS),
        **load_public_defaults(PUBLIC_CONTEXT_DEFAULTS_FILE, CONTEXT_DEFAULTS),
    }


def bootstrap_dashboard_for_user():
    user_id = current_user_id()
    if not user_id or st.session_state.get("dashboard_loaded_user_id") == user_id:
        return False
    try:
        saved_dashboard = load_dashboard()
    except RuntimeError:
        saved_dashboard = None
    if not saved_dashboard:
        return False
    hydrate_session_payload(saved_dashboard)
    st.session_state["dashboard_loaded_user_id"] = user_id
    st.session_state["saved_dashboard_snapshot"] = dict(saved_dashboard)
    st.session_state["market_inputs_last_saved"] = collect_session_payload(MARKET_INPUT_DEFAULTS)
    st.session_state["context_last_saved"] = collect_session_payload(CONTEXT_DEFAULTS)
    st.session_state["market_inputs_loaded_user_id"] = user_id
    st.session_state["context_loaded_user_id"] = user_id
    return True


def bootstrap_market_inputs_for_user():
    user_id = current_user_id()
    if not user_id or st.session_state.get("market_inputs_loaded_user_id") == user_id:
        return
    try:
        saved_market_inputs = load_market_inputs()
    except RuntimeError:
        saved_market_inputs = None
    if saved_market_inputs:
        hydrate_session_payload(saved_market_inputs)
        st.session_state["market_inputs_last_saved"] = dict(saved_market_inputs)
    else:
        st.session_state["market_inputs_last_saved"] = collect_session_payload(MARKET_INPUT_DEFAULTS)
    st.session_state["market_inputs_loaded_user_id"] = user_id


def persist_market_inputs_if_needed():
    user_id = current_user_id()
    if not user_id or st.session_state.get("market_inputs_loaded_user_id") != user_id:
        return
    payload = collect_session_payload(MARKET_INPUT_DEFAULTS)
    last_saved = st.session_state.get("market_inputs_last_saved")
    if payload == last_saved:
        return
    try:
        save_profile_to_supabase("market_inputs", payload)
    except RuntimeError:
        return
    st.session_state["market_inputs_last_saved"] = dict(payload)


def handle_market_inputs_change():
    sync_model_state_from_widgets()
    persist_market_inputs_if_needed()


def bootstrap_context_for_user():
    user_id = current_user_id()
    if not user_id or st.session_state.get("context_loaded_user_id") == user_id:
        return
    try:
        saved_context = load_context()
    except RuntimeError:
        saved_context = None
    if saved_context:
        hydrate_session_payload(saved_context)
        st.session_state["context_last_saved"] = dict(saved_context)
    else:
        st.session_state["context_last_saved"] = collect_session_payload(CONTEXT_DEFAULTS)
    st.session_state["context_loaded_user_id"] = user_id


def persist_context_if_needed():
    user_id = current_user_id()
    if not user_id or st.session_state.get("context_loaded_user_id") != user_id:
        return
    payload = collect_session_payload(CONTEXT_DEFAULTS)
    last_saved = st.session_state.get("context_last_saved")
    if payload == last_saved:
        return
    try:
        save_profile_to_supabase("context", payload)
    except RuntimeError:
        return
    st.session_state["context_last_saved"] = dict(payload)


def handle_context_change():
    persist_context_if_needed()


def tag_html(label):
    bg = "#16a34a" if label == "Bullish" else "#dc2626" if label == "Bearish" else "#ca8a04"
    return f'<span style="background-color:{bg};color:white;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:bold;display:inline-block;margin:4px 0 8px 0;">{label}</span>'


def display_text(value, fallback="Not set"):
    cleaned = str(value).strip() if value is not None else ""
    return cleaned if cleaned else fallback


def display_link(title, url, fallback="Not added yet"):
    clean_title = display_text(title, "")
    clean_url = display_text(url, "")
    if clean_url.startswith("http://") or clean_url.startswith("https://"):
        label = clean_title if clean_title else clean_url
        return f"[{label}]({clean_url})"
    if clean_title:
        return clean_title
    return fallback


def display_simple_link(value, fallback="Not added yet"):
    clean_value = display_text(value, "")
    if clean_value.startswith("http://") or clean_value.startswith("https://"):
        return f"[Open link]({clean_value})"
    if clean_value:
        return clean_value
    return fallback


def format_change_value(value):
    if isinstance(value, bool):
        return "On" if value else "Off"
    if isinstance(value, float):
        return f"{value:.1f}"
    return display_text(value, "Blank")


def format_signal_date(value):
    if not value:
        return "Not triggered yet"
    try:
        return datetime.fromisoformat(str(value)).strftime("%b %d, %Y")
    except ValueError:
        return str(value)


def build_saved_dashboard_changes(saved_payload, current_payload):
    if not saved_payload:
        return []
    fields = [
        ("Market", "TOTAL 3D Trend", "total_3d_state"),
        ("Market", "TOTAL 1D Signal", "total_1d_supertrend"),
        ("Analysts", "Analyst 1 Bias", "analyst1_bias"),
        ("Analysts", "Analyst 2 Bias", "analyst2_bias"),
        ("Analysts", "Analyst 3 Bias", "analyst3_bias"),
        ("News", "News 1 Headline", "news1_headline"),
        ("News", "News 2 Headline", "news2_headline"),
        ("News", "News 3 Headline", "news3_headline"),
        ("News", "News 1 Direction", "news1_direction"),
        ("News", "News 2 Direction", "news2_direction"),
        ("News", "News 3 Direction", "news3_direction"),
        ("Context", "Manual BTC ETF Flow", "manual_btc_etf_flow"),
        ("Context", "Manual ETH ETF Flow", "manual_eth_etf_flow"),
        ("Context", "Lunar Event", "astro_lunar_event"),
        ("Context", "Transits Worth Noting", "astro_transits"),
        ("Context", "Market Theme", "astro_market_theme"),
        ("Context", "Recommended Video", "share_video"),
        ("Context", "Recommended Article", "share_article"),
    ]
    changes = []
    for section, label, key in fields:
        saved_value = saved_payload.get(key)
        current_value = current_payload.get(key)
        if saved_value != current_value:
            changes.append(
                {
                    "section": section,
                    "label": label,
                    "saved": format_change_value(saved_value),
                    "current": format_change_value(current_value),
                }
            )
    return changes


def build_ai_summary_payload(
    bias,
    final_score,
    signal_strength,
    conviction_label,
    total_3d_state,
    score_3d,
    total_1d_supertrend,
    score_1d,
    ta_score,
    analyst_score,
    news_score,
    macro_score,
    sentiment_score,
    fng_score,
    fng_value,
    fng_label,
    stablecoin_signal,
    global_liquidity_signal,
    etf_flows_signal,
    open_interest_signal,
    macro_unavailable,
    analyst_rows,
    news_rows,
):
    payload = {
        "bias": bias,
        "final_score": round(final_score, 1),
        "signal_strength": round(signal_strength, 1),
        "conviction": conviction_label,
        "technical_analysis": {
            "total_3d_state": total_3d_state,
            "total_3d_score": score_3d,
            "total_1d_state": total_1d_supertrend,
            "total_1d_score": score_1d,
            "combined_score": ta_score,
        },
        "analyst_consensus_score": round(analyst_score, 1),
        "news_score": news_score,
        "macro_score": macro_score,
        "sentiment_score": round(sentiment_score, 1),
        "fear_and_greed": {
            "value": fng_value,
            "classification": fng_label,
            "score": fng_score,
        },
        "analysts": analyst_rows,
        "news_items": news_rows,
        "macro_highlights": {
            "stablecoin_liquidity": {
                "state": stablecoin_signal["state"],
                "score": stablecoin_signal["score"],
                "change_pct": round(stablecoin_signal["change_pct"], 2) if stablecoin_signal.get("change_pct") is not None else None,
            },
            "global_liquidity_proxy": {
                "state": global_liquidity_signal["state"],
                "score": global_liquidity_signal["score"],
                "missing_components": global_liquidity_signal.get("missing_components", []),
            },
            "crypto_etf_flows": {
                "state": etf_flows_signal["state"],
                "score": etf_flows_signal["score"],
                "value_usd_millions": round(etf_flows_signal["value"], 1) if etf_flows_signal.get("value") is not None else None,
            },
            "btc_market_fragility": {
                "state": open_interest_signal["state"],
                "score": open_interest_signal["score"],
                "change_pct": round(open_interest_signal["change_pct"], 2) if open_interest_signal.get("change_pct") is not None else None,
            },
        },
        "unavailable_feeds": macro_unavailable,
    }
    return payload


def get_ai_summary_fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def generate_ai_summary(summary_payload):
    config = get_openai_config()
    if not config["api_key"]:
        raise RuntimeError("Add `OPENAI_API_KEY` to Streamlit secrets to enable AI explanations.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Install the `openai` package to enable AI explanations.") from exc

    client = OpenAI(api_key=config["api_key"])
    prompt = (
        "You are an experienced crypto market analyst writing for a dashboard user. "
        "Do not recalculate the score or change the bias. Use only the provided inputs. "
        "Be concise, specific, and practical. Mention uncertainty when conviction is low or data is unavailable."
    )
    response = client.responses.create(
        model=config["model"],
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(summary_payload, indent=2)}]},
        ],
        max_output_tokens=900,
        text={
            "format": {
                "type": "json_schema",
                "name": "oracle_summary",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "current_bias_explained": {"type": "string"},
                        "top_reasons": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
                        "what_could_flip_this": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
                        "risk_watch": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
                        "plain_english_takeaway": {"type": "string"},
                    },
                    "required": [
                        "current_bias_explained",
                        "top_reasons",
                        "what_could_flip_this",
                        "risk_watch",
                        "plain_english_takeaway",
                    ],
                    "additionalProperties": False,
                },
            }
        },
    )
    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise RuntimeError("OpenAI returned an empty explanation.")
    try:
        return json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenAI returned an invalid structured explanation.") from exc


def get_theme_colors(is_dark_mode):
    if is_dark_mode:
        return {
            "app_bg": "#070707", "card_bg": "#15110f", "card_border": "rgba(239,68,68,0.34)",
            "card_shadow": "0 16px 38px rgba(0,0,0,0.45)", "text": "#f8fafc", "muted": "#a8a29e",
            "divider": "rgba(255,255,255,0.09)",
        }
    return {
        "app_bg": "#f7f2ee", "card_bg": "#fffdfb", "card_border": "rgba(153,27,27,0.16)",
        "card_shadow": "0 10px 28px rgba(28,25,23,0.10)", "text": "#1c1917", "muted": "#6b625c",
        "divider": "rgba(28,25,23,0.10)",
    }


def fetch_market_signal(ticker, label, rising_score, falling_score):
    result = {"label": label, "value": None, "state": "Unavailable", "score": 0, "available": False, "error": None}
    try:
        data = yf.download(ticker, period="10d", interval="1d", auto_adjust=False, progress=False, threads=False)
        close_series = data.get("Close")
        if close_series is None or len(close_series) < 2:
            result["error"] = "Not enough market data returned."
            return result
        latest_value = float(close_series.iloc[-1].item())
        previous_value = float(close_series.iloc[-2].item())
        if latest_value > previous_value:
            state, score = "Rising", rising_score
        elif latest_value < previous_value:
            state, score = "Falling", falling_score
        else:
            state, score = "Neutral", 0
        result.update({"value": latest_value, "state": state, "score": score, "available": True})
    except Exception as exc:
        result["error"] = str(exc)
    return result


def fetch_stooq_signal(symbol, label, rising_score, falling_score):
    result = {"label": label, "value": None, "state": "Unavailable", "score": 0, "available": False, "error": None}
    try:
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
        response = requests.get(url, headers=DEFAULT_HTTP_HEADERS, timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        rows = list(csv.DictReader(StringIO(response.text)))
        closes = [float(row["Close"]) for row in rows if row.get("Close")]
        if len(closes) < 2:
            result["error"] = "Not enough Stooq data returned."
            return result
        latest_value = closes[-1]
        previous_value = closes[-2]
        if latest_value > previous_value:
            state, score = "Rising", rising_score
        elif latest_value < previous_value:
            state, score = "Falling", falling_score
        else:
            state, score = "Neutral", 0
        result.update({"value": latest_value, "state": state, "score": score, "available": True})
    except Exception as exc:
        result["error"] = str(exc)
    return result


def choose_best_signal(primary_signal, fallback_signal):
    if primary_signal.get("available"):
        return primary_signal
    if fallback_signal.get("available"):
        fallback_copy = dict(fallback_signal)
        primary_error = primary_signal.get("error")
        if primary_error:
            fallback_copy["error"] = f"Primary source unavailable: {primary_error}"
        fallback_copy["fallback_used"] = True
        return fallback_copy
    combined = dict(primary_signal)
    fallback_error = fallback_signal.get("error")
    if fallback_error:
        combined["error"] = f"{primary_signal.get('error', 'Primary source unavailable.')} Fallback source unavailable: {fallback_error}"
    return combined


def compute_wilder_rsi(values, length):
    if len(values) <= length:
        return [None] * len(values)
    rsi_values = [None] * len(values)
    gains = []
    losses = []
    for idx in range(1, length + 1):
        delta = values[idx] - values[idx - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / length
    avg_loss = sum(losses) / length
    if avg_loss == 0:
        rsi_values[length] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_values[length] = 100.0 - (100.0 / (1.0 + rs))
    for idx in range(length + 1, len(values)):
        delta = values[idx] - values[idx - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = ((avg_gain * (length - 1)) + gain) / length
        avg_loss = ((avg_loss * (length - 1)) + loss) / length
        if avg_loss == 0:
            rsi_values[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[idx] = 100.0 - (100.0 / (1.0 + rs))
    return rsi_values


def group_daily_series_into_three_day_bars(points):
    if not points:
        return []
    daily_by_date = {}
    for timestamp_ms, value in points:
        try:
            point_date = datetime.fromtimestamp(float(timestamp_ms) / 1000.0, tz=timezone.utc).date()
            point_value = float(value)
        except (TypeError, ValueError, OSError):
            continue
        daily_by_date[point_date] = point_value
    sorted_points = sorted(daily_by_date.items(), key=lambda item: item[0])
    buckets = []
    current_bucket = None
    for point_date, point_value in sorted_points:
        bucket_id = point_date.toordinal() // 3
        if current_bucket is None or current_bucket["bucket_id"] != bucket_id:
            current_bucket = {
                "bucket_id": bucket_id,
                "date": point_date,
                "open": point_value,
                "high": point_value,
                "low": point_value,
                "close": point_value,
                "count": 1,
            }
            buckets.append(current_bucket)
            continue
        current_bucket["date"] = point_date
        current_bucket["high"] = max(current_bucket["high"], point_value)
        current_bucket["low"] = min(current_bucket["low"], point_value)
        current_bucket["close"] = point_value
        current_bucket["count"] += 1
    return [bucket for bucket in buckets if bucket["count"] == 3]


def group_daily_ohlc_into_three_day_bars(daily_bars):
    if not daily_bars:
        return []
    sorted_bars = sorted(daily_bars, key=lambda bar: bar["date"])
    buckets = []
    current_bucket = None
    for bar in sorted_bars:
        bucket_id = bar["date"].toordinal() // 3
        if current_bucket is None or current_bucket["bucket_id"] != bucket_id:
            current_bucket = {
                "bucket_id": bucket_id,
                "date": bar["date"],
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "count": 1,
            }
            buckets.append(current_bucket)
            continue
        current_bucket["date"] = bar["date"]
        current_bucket["high"] = max(current_bucket["high"], bar["high"])
        current_bucket["low"] = min(current_bucket["low"], bar["low"])
        current_bucket["close"] = bar["close"]
        current_bucket["count"] += 1
    return [bucket for bucket in buckets if bucket["count"] == 3]


def linear_regression_last(values):
    length = len(values)
    if length == 0:
        return None
    x_values = list(range(length))
    sum_x = sum(x_values)
    sum_y = sum(values)
    sum_xy = sum(x * y for x, y in zip(x_values, values))
    sum_x2 = sum(x * x for x in x_values)
    denominator = (length * sum_x2) - (sum_x * sum_x)
    if denominator == 0:
        return values[-1]
    slope = ((length * sum_xy) - (sum_x * sum_y)) / denominator
    intercept = (sum_y - (slope * sum_x)) / length
    return intercept + slope * (length - 1)


def compute_sell_signals_from_bars(bars):
    signal_defaults = {
        "sell_warning": {"active": False, "label": "Inactive", "date": None, "rsi": None, "last_triggered": None, "history": []},
        "hard_sell": {"active": False, "label": "Inactive", "date": None, "rsi": None, "last_triggered": None, "history": []},
        "dream_sell": {"active": False, "label": "Inactive", "date": None, "rsi": None, "last_triggered": None, "history": []},
    }
    closes = [bar["close"] for bar in bars]
    hlc3_values = [(bar["high"] + bar["low"] + bar["close"]) / 3.0 for bar in bars]
    rsi_values = compute_wilder_rsi(closes, 14)
    mean_values = [None] * len(bars)
    upper_values = [None] * len(bars)
    for idx in range(99, len(bars)):
        mean_window = hlc3_values[idx - 99 : idx + 1]
        mean_value = linear_regression_last(mean_window)
        sigma = float((sum((value - (sum(mean_window) / len(mean_window))) ** 2 for value in mean_window) / len(mean_window)) ** 0.5)
        mean_values[idx] = mean_value
        upper_values[idx] = mean_value + (2.0 * sigma)

    ss_count = 0
    hard_armed = False
    dream_armed = False
    last_triggered = {"sell_warning": None, "hard_sell": None, "dream_sell": None}
    history = {"sell_warning": [], "hard_sell": [], "dream_sell": []}
    current_flags = {"sell_warning": False, "hard_sell": False, "dream_sell": False}
    current_rsi = None
    current_date = None

    for idx in range(1, len(bars)):
        rsi = rsi_values[idx]
        prev_rsi = rsi_values[idx - 1]
        mean_value = mean_values[idx]
        prev_mean = mean_values[idx - 1] if idx > 0 else None
        upper_value = upper_values[idx]
        if rsi is None or prev_rsi is None or mean_value is None or prev_mean is None or upper_value is None:
            continue

        current_date = bars[idx]["date"].isoformat()
        current_rsi = rsi

        reset_ob = prev_rsi >= 71 and rsi < 71
        reset_neutral = prev_rsi >= 50 and rsi < 50
        if reset_neutral:
            ss_count = 0
            hard_armed = False
            dream_armed = False

        if rsi >= 85:
            hard_armed = True
        if rsi >= 92:
            dream_armed = True

        rollover71 = prev_rsi >= 71 and rsi < 71
        rollover_hard = hard_armed and prev_rsi >= 83 and rsi < 83
        rollover_dream = dream_armed and prev_rsi >= 85 and rsi < 85

        bearish_bar = bars[idx]["close"] < bars[idx]["open"]
        mean_flat_down = mean_value <= prev_mean
        upper_close_reject = bars[idx]["close"] >= upper_value
        upper_wick_reject = bars[idx]["high"] >= upper_value and bars[idx]["close"] < upper_value
        upper_reject = upper_close_reject or upper_wick_reject

        sell_can_fire = bearish_bar
        sell_attempt_dream = sell_can_fire and rollover_dream
        sell_attempt_hard = sell_can_fire and rollover_hard and not sell_attempt_dream
        sell_attempt71 = sell_can_fire and rollover71 and not sell_attempt_dream and not sell_attempt_hard

        cap_ok = ss_count < 2
        sig_dream = sell_attempt_dream
        sig_hard = sell_attempt_hard and cap_ok
        sig_71 = sell_attempt71 and cap_ok

        current_flags = {"sell_warning": sig_71, "hard_sell": sig_hard, "dream_sell": sig_dream}

        if sig_71:
            last_triggered["sell_warning"] = current_date
            history["sell_warning"].append(current_date)
        if sig_hard:
            last_triggered["hard_sell"] = current_date
            history["hard_sell"].append(current_date)
        if sig_dream:
            last_triggered["dream_sell"] = current_date
            history["dream_sell"].append(current_date)

        if sig_hard or sig_71:
            ss_count += 1
        if sig_dream:
            dream_armed = False
            hard_armed = False
        if sig_hard:
            hard_armed = False

    signal_defaults["sell_warning"] = {
        "active": current_flags["sell_warning"],
        "label": "Active" if current_flags["sell_warning"] else "Inactive",
        "date": current_date,
        "rsi": current_rsi,
        "last_triggered": last_triggered["sell_warning"],
        "history": history["sell_warning"][-5:][::-1],
    }
    signal_defaults["hard_sell"] = {
        "active": current_flags["hard_sell"],
        "label": "Active" if current_flags["hard_sell"] else "Inactive",
        "date": current_date,
        "rsi": current_rsi,
        "last_triggered": last_triggered["hard_sell"],
        "history": history["hard_sell"][-5:][::-1],
    }
    signal_defaults["dream_sell"] = {
        "active": current_flags["dream_sell"],
        "label": "Active" if current_flags["dream_sell"] else "Inactive",
        "date": current_date,
        "rsi": current_rsi,
        "last_triggered": last_triggered["dream_sell"],
        "history": history["dream_sell"][-5:][::-1],
    }
    return signal_defaults


def fetch_coingecko_market_chart_prices(coin_id, days="max"):
    headers = get_coingecko_headers()
    if "x-cg-pro-api-key" not in headers:
        raise RuntimeError("CoinGecko Pro API key not configured.")
    response = requests.get(
        f"https://pro-api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
        params={"vs_currency": "usd", "days": days, "interval": "daily"},
        headers=headers,
        timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    price_points = payload.get("prices") if isinstance(payload, dict) else None
    if not isinstance(price_points, list) or len(price_points) < 100:
        raise RuntimeError("Not enough CoinGecko market chart history returned.")
    return price_points


def fetch_coingecko_market_chart_range(coin_id, start_dt, end_dt):
    headers = get_coingecko_headers()
    if "x-cg-pro-api-key" not in headers:
        raise RuntimeError("CoinGecko Pro API key not configured.")
    response = requests.get(
        f"https://pro-api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range",
        params={
            "vs_currency": "usd",
            "from": int(start_dt.timestamp()),
            "to": int(end_dt.timestamp()),
            "interval": "daily",
        },
        headers=headers,
        timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("prices") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("No CoinGecko market-chart rows returned.")
    return rows


def fetch_coingecko_daily_bars(symbol, lookback_days=360):
    coin_id = SELL_SIGNAL_COINGECKO_IDS.get(symbol)
    if not coin_id:
        raise RuntimeError("No CoinGecko coin id mapping available.")
    end_dt = datetime.now(timezone.utc)
    mid_dt = end_dt - timedelta(days=180)
    start_dt = end_dt - timedelta(days=lookback_days)
    rows = fetch_coingecko_market_chart_range(coin_id, start_dt, mid_dt) + fetch_coingecko_market_chart_range(coin_id, mid_dt - timedelta(days=1), end_dt)
    daily_closes = {}
    for row in rows:
        try:
            point_dt = datetime.fromtimestamp(int(row[0]) / 1000.0, tz=timezone.utc).date()
            daily_closes[point_dt] = float(row[1])
        except (TypeError, ValueError, IndexError, OSError):
            continue
    sorted_dates = sorted(daily_closes.keys())
    daily_bars = []
    previous_close = None
    for point_date in sorted_dates:
        close_value = daily_closes[point_date]
        open_value = previous_close if previous_close is not None else close_value
        high_value = max(open_value, close_value)
        low_value = min(open_value, close_value)
        daily_bars.append(
            {
                "date": point_date,
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
            }
        )
        previous_close = close_value
    if len(daily_bars) < 300:
        raise RuntimeError("Not enough valid CoinGecko daily bars after parsing.")
    return daily_bars[-lookback_days:]


def fetch_asset_sell_signal_bundle(symbol, label):
    result = {
        "label": label,
        "symbol": symbol,
        "available": False,
        "source": None,
        "fallback_used": False,
        "error": None,
        "sell_warning": {"active": False, "label": "Unavailable", "date": None, "rsi": None, "last_triggered": None, "history": []},
        "hard_sell": {"active": False, "label": "Unavailable", "date": None, "rsi": None, "last_triggered": None, "history": []},
        "dream_sell": {"active": False, "label": "Unavailable", "date": None, "rsi": None, "last_triggered": None, "history": []},
    }
    try:
        bars = group_daily_ohlc_into_three_day_bars(fetch_coingecko_daily_bars(symbol))
        if len(bars) < 110:
            result["error"] = "Not enough 3D history to evaluate sell signals."
            return result
        sell_signals = compute_sell_signals_from_bars(bars)
        result["sell_warning"] = sell_signals["sell_warning"]
        result["hard_sell"] = sell_signals["hard_sell"]
        result["dream_sell"] = sell_signals["dream_sell"]
        result["available"] = True
        result["source"] = "CoinGecko Basic price-history proxy"
    except Exception as exc:
        result["error"] = str(exc)
    return result


def build_sell_signal_summary(asset_results, signal_key):
    active_assets = [asset["label"] for asset in asset_results if asset.get("available") and asset[signal_key]["active"]]
    recently_triggered = []
    for asset in asset_results:
        last_triggered = asset.get(signal_key, {}).get("last_triggered")
        if last_triggered:
            recently_triggered.append((last_triggered, asset["label"]))
    recently_triggered.sort(reverse=True)
    return {
        "active_assets": active_assets,
        "active_count": len(active_assets),
        "label": f"{len(active_assets)} Active" if active_assets else "None Active",
        "recent_assets": [label for _, label in recently_triggered[:5]],
    }


@st.cache_data(ttl=SIGNAL_SECTION_CACHE_TTL_SECONDS, show_spinner=False)
def load_signal_section_data():
    jobs = {
        "buy_signals": lambda: get_feed_result(
            "signal_total_market_v4",
            fetch_total_market_signals,
            cache_ttl_seconds=SIGNAL_SECTION_CACHE_TTL_SECONDS,
            stale_ttl_seconds=DEFAULT_FEED_STALE_TTL_SECONDS,
        )
    }
    for symbol, label in SELL_SIGNAL_ASSETS:
        jobs[f"sell_{symbol.lower()}"] = lambda symbol=symbol, label=label: get_feed_result(
            f"signal_sell_{symbol.lower()}_v4",
            lambda symbol=symbol, label=label: fetch_asset_sell_signal_bundle(symbol, label),
            cache_ttl_seconds=SIGNAL_SECTION_CACHE_TTL_SECONDS,
            stale_ttl_seconds=DEFAULT_FEED_STALE_TTL_SECONDS,
        )
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(jobs))) as executor:
        future_map = {executor.submit(job): name for name, job in jobs.items()}
        for future in concurrent.futures.as_completed(future_map):
            name = future_map[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                results[name] = {"available": False, "error": str(exc)}
    sell_assets = [results[f"sell_{symbol.lower()}"] for symbol, _ in SELL_SIGNAL_ASSETS if f"sell_{symbol.lower()}" in results]
    return {
        "buy": results.get("buy_signals", {"available": False, "error": "Buy signal source unavailable."}),
        "sell_assets": sell_assets,
        "sell_warning_summary": build_sell_signal_summary(sell_assets, "sell_warning"),
        "hard_sell_summary": build_sell_signal_summary(sell_assets, "hard_sell"),
        "dream_sell_summary": build_sell_signal_summary(sell_assets, "dream_sell"),
    }


def fetch_total_market_signals():
    result = {
        "label": "BTC Market Signals",
        "available": False,
        "error": None,
        "source": "CoinGecko BTC market chart grouped into 3D bars",
        "approximate": True,
        "dream_buy": {"active": False, "label": "Unavailable", "rsi": None, "date": None, "last_triggered": None, "history": []},
        "oial": {"active": False, "label": "Unavailable", "sma_600": None, "close": None, "date": None, "last_triggered": None, "history": []},
        "sell_warning": {"active": False, "label": "Unavailable", "date": None, "rsi": None, "last_triggered": None, "history": []},
        "hard_sell": {"active": False, "label": "Unavailable", "date": None, "rsi": None, "last_triggered": None, "history": []},
        "dream_sell": {"active": False, "label": "Unavailable", "date": None, "rsi": None, "last_triggered": None, "history": []},
    }
    try:
        price_points = fetch_coingecko_market_chart_prices("bitcoin", days="max")
        bars = group_daily_series_into_three_day_bars(price_points)
        closes = [bar["close"] for bar in bars]
        if len(closes) < 100:
            result["error"] = "Not enough 3D BTC history to evaluate buy signals."
            return result

        latest_bar = bars[-1]
        latest_date = latest_bar["date"].isoformat()

        rsi_values = compute_wilder_rsi(closes, 14)
        latest_rsi = rsi_values[-1]
        dream_buy_history = [bars[idx]["date"].isoformat() for idx, rsi_value in enumerate(rsi_values) if rsi_value is not None and rsi_value <= 20]
        dream_buy_active = latest_rsi is not None and latest_rsi <= 20
        result["dream_buy"] = {
            "active": dream_buy_active,
            "label": "Active" if dream_buy_active else "Not Active",
            "rsi": latest_rsi,
            "date": latest_date,
            "last_triggered": dream_buy_history[-1] if dream_buy_history else None,
            "history": dream_buy_history[-5:][::-1],
        }

        if len(closes) >= 600:
            sma_600 = sum(closes[-600:]) / 600
            oial_history = [bar["date"].isoformat() for bar in bars if bar["low"] <= sma_600 <= bar["high"]]
            oial_active = latest_bar["low"] <= sma_600 <= latest_bar["high"]
            oial_label = "Touched 600 SMA" if oial_active else "Not Active"
            oial_last = oial_history[-1] if oial_history else None
            oial_recent = oial_history[-5:][::-1]
        else:
            sma_600 = None
            oial_active = False
            oial_label = "History Building"
            oial_last = None
            oial_recent = []
        result["oial"] = {
            "active": oial_active,
            "label": oial_label,
            "sma_600": sma_600,
            "close": latest_bar["close"],
            "date": latest_date,
            "last_triggered": oial_last,
            "history": oial_recent,
        }
        result["available"] = True
        result["source"] = "CoinGecko BTC market chart grouped into 3D bars"
    except Exception as exc:
        result["error"] = str(exc)
    return result


def fetch_dxy_signal():
    primary = fetch_market_signal("DX=F", "DXY", -12, 12)
    secondary = fetch_market_signal("DX-Y.NYB", "DXY", -12, 12)
    if primary.get("available"):
        return primary
    fallback = choose_best_signal(primary, secondary)
    if fallback.get("available"):
        return fallback
    tertiary = fetch_stooq_signal("dx.f", "DXY", -12, 12)
    return choose_best_signal(fallback, tertiary)


def fetch_wti_signal():
    primary = fetch_stooq_signal("cl.f", "WTI Crude Oil", -6, 6)
    fallback = fetch_market_signal("CL=F", "WTI Crude Oil", -6, 6)
    return choose_best_signal(primary, fallback)


def fetch_us10y_signal():
    # FRED DGS10 is a more stable hosted source than Yahoo's ^TNX feed.
    return fetch_fred_signal("DGS10", "US 10Y", -10, 10)


def fetch_fred_signal(series_id, label, rising_score, falling_score):
    result = {"label": label, "value": None, "state": "Unavailable", "score": 0, "available": False, "error": None}
    try:
        with urlopen(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}", timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS) as response:
            csv_text = response.read().decode("utf-8")
        rows = list(csv.DictReader(StringIO(csv_text)))
        values = [float(row[series_id]) for row in rows if row.get(series_id) and row[series_id] != "."]
        if len(values) < 2:
            result["error"] = "Not enough FRED data returned."
            return result
        latest_value, previous_value = values[-1], values[-2]
        if latest_value > previous_value:
            state, score = "Rising", rising_score
        elif latest_value < previous_value:
            state, score = "Falling", falling_score
        else:
            state, score = "Neutral", 0
        result.update({"value": latest_value, "state": state, "score": score, "available": True})
    except Exception as exc:
        result["error"] = str(exc)
    return result

def fetch_fred_change_signal(series_id, label, lookback_points, positive_score, negative_score, inverse=False):
    result = {"label": label, "value": None, "previous_value": None, "state": "Unavailable", "score": 0, "available": False, "change_pct": None, "error": None}
    try:
        with urlopen(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}", timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS) as response:
            csv_text = response.read().decode("utf-8")
        rows = list(csv.DictReader(StringIO(csv_text)))
        values = [float(row[series_id]) for row in rows if row.get(series_id) and row[series_id] != "."]
        if len(values) <= lookback_points:
            result["error"] = "Not enough FRED history returned."
            return result
        latest_value = values[-1]
        previous_value = values[-1 - lookback_points]
        if previous_value == 0:
            result["error"] = "Invalid previous FRED value."
            return result
        change_pct = ((latest_value - previous_value) / previous_value) * 100
        is_positive = latest_value > previous_value
        if latest_value == previous_value:
            state, score = "Flat", 0
        else:
            is_supportive = (not is_positive) if inverse else is_positive
            state = ("Falling" if inverse else "Expanding") if is_supportive else ("Rising" if inverse else "Contracting")
            score = positive_score if is_supportive else negative_score
        result.update({"value": latest_value, "previous_value": previous_value, "state": state, "score": score, "available": True, "change_pct": change_pct})
    except Exception as exc:
        result["error"] = str(exc)
    return result


def fetch_ecb_balance_sheet_signal():
    result = {"label": "ECB / Eurosystem Balance Sheet", "value": None, "previous_value": None, "state": "Unavailable", "score": 0, "available": False, "change_pct": None, "error": None}
    try:
        url = "https://data-api.ecb.europa.eu/service/data/BSI/BSI.M.U2.N.C.T00.A.1.Z5.0000.Z01.E?format=csvdata"
        with urlopen(url, timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS) as response:
            csv_text = response.read().decode("utf-8")
        rows = list(csv.DictReader(StringIO(csv_text)))
        values = [float(row["OBS_VALUE"]) for row in rows if row.get("OBS_VALUE") and row["OBS_VALUE"] != "."]
        if len(values) < 4:
            result["error"] = "Not enough ECB history returned."
            return result
        latest_value, previous_value = values[-1], values[-4]
        change_pct = ((latest_value - previous_value) / previous_value) * 100 if previous_value else 0
        if latest_value > previous_value:
            state, score = "Expanding", 3
        elif latest_value < previous_value:
            state, score = "Contracting", -3
        else:
            state, score = "Flat", 0
        result.update({"value": latest_value, "previous_value": previous_value, "state": state, "score": score, "available": True, "change_pct": change_pct})
    except Exception as exc:
        result["error"] = str(exc)
    return result


def fetch_boj_balance_sheet_signal():
    result = {"label": "BoJ Balance Sheet", "value": None, "previous_value": None, "state": "Unavailable", "score": 0, "available": False, "change_pct": None, "error": None}
    try:
        with urlopen("https://www.boj.or.jp/en/statistics/boj/other/acmai/index.htm", timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS) as response:
            index_html = response.read().decode("utf-8")
        release_paths = re.findall(r'href="(/en/statistics/boj/other/acmai/release/\d{4}/ac\d+\.htm)"', index_html)
        unique_paths = []
        for path in release_paths:
            if path not in unique_paths:
                unique_paths.append(path)
        if len(unique_paths) < 4:
            result["error"] = "Not enough BoJ release links found."
            return result
        totals = []
        for path in unique_paths[:4]:
            with urlopen(f"https://www.boj.or.jp{path}", timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS) as response:
                page_html = response.read().decode("utf-8")
            match = re.search(r"Total\s*\|\s*([\d,]+)", page_html)
            if match:
                totals.append(float(match.group(1).replace(",", "")))
        if len(totals) < 4:
            result["error"] = "Not enough BoJ total asset values found."
            return result
        latest_value, previous_value = totals[0], totals[3]
        change_pct = ((latest_value - previous_value) / previous_value) * 100 if previous_value else 0
        if latest_value > previous_value:
            state, score = "Expanding", 3
        elif latest_value < previous_value:
            state, score = "Contracting", -3
        else:
            state, score = "Flat", 0
        result.update({"value": latest_value, "previous_value": previous_value, "state": state, "score": score, "available": True, "change_pct": change_pct})
    except Exception as exc:
        result["error"] = str(exc)
    return result


def build_global_liquidity_proxy():
    components = [
        fetch_fred_change_signal("WALCL", "Fed Balance Sheet", 4, 3, -3),
        fetch_ecb_balance_sheet_signal(),
        fetch_boj_balance_sheet_signal(),
        fetch_fred_change_signal("TOTBKCR", "Bank Credit", 4, 4, -4),
        fetch_fred_change_signal("DTWEXBGS", "Broad Dollar Index", 20, 4, -4, inverse=True),
    ]
    available_components = [component for component in components if component["available"]]
    proxy = {"label": "Global Liquidity Proxy", "state": "Unavailable", "score": 0, "available": False, "components": components, "missing_components": [], "error": None}
    if not available_components:
        proxy["error"] = "No liquidity components available."
        return proxy
    raw_score = sum(component["score"] for component in available_components)
    normalized_score = round((raw_score / 17) * 12)
    state = "Improving" if normalized_score > 0 else "Tightening" if normalized_score < 0 else "Neutral"
    proxy.update({"state": state, "score": normalized_score, "available": True, "missing_components": [component["label"] for component in components if not component["available"]]})
    return proxy


def fetch_stablecoin_liquidity_signal():
    result = {"label": "Stablecoin Liquidity", "value": None, "previous_value": None, "state": "Unavailable", "score": 0, "available": False, "change_pct": None, "error": None}
    try:
        with urlopen("https://stablecoins.llama.fi/stablecoincharts/all", timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list) or len(payload) < 8:
            result["error"] = "Not enough stablecoin history returned."
            return result
        latest_entry, previous_entry = payload[-1], payload[-8]
        latest_value = float(latest_entry["totalCirculatingUSD"]["peggedUSD"])
        previous_value = float(previous_entry["totalCirculatingUSD"]["peggedUSD"])
        if previous_value == 0:
            result["error"] = "Invalid previous stablecoin supply value."
            return result
        change_pct = ((latest_value - previous_value) / previous_value) * 100
        if change_pct >= 1.0:
            state, score = "Expanding", 8
        elif change_pct <= -1.0:
            state, score = "Contracting", -8
        else:
            state, score = "Flat", 0
        result.update({"value": latest_value, "previous_value": previous_value, "state": state, "score": score, "available": True, "change_pct": change_pct})
    except Exception as exc:
        result["error"] = str(exc)
    return result


def fetch_etf_flow_table(path, label):
    result = {"label": label, "value": None, "state": "Unavailable", "score": 0, "available": False, "error": None}
    try:
        with urlopen(f"https://farside.co.uk/{path}/", timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS) as response:
            html = response.read().decode("utf-8", errors="ignore")
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL)
        for row in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.IGNORECASE | re.DOTALL)
            cleaned = [re.sub(r"<.*?>", "", cell).replace("&nbsp;", " ").strip() for cell in cells]
            if len(cleaned) < 2:
                continue
            if not re.search(r"\d{1,2}\s+[A-Za-z]{3}\s+\d{4}", cleaned[0]):
                continue
            total_text = cleaned[-1].replace(",", "").replace("(", "-").replace(")", "")
            if total_text in {"", "-", "—"}:
                continue
            latest_flow = float(total_text)
            if latest_flow >= 150:
                state, score = "Strong Inflow", 6
            elif latest_flow > 0:
                state, score = "Inflow", 3
            elif latest_flow <= -150:
                state, score = "Strong Outflow", -6
            elif latest_flow < 0:
                state, score = "Outflow", -3
            else:
                state, score = "Flat", 0
            result.update({"value": latest_flow, "state": state, "score": score, "available": True})
            return result
        result["error"] = "No recent ETF flow row found."
    except Exception as exc:
        result["error"] = str(exc)
    return result


def fetch_crypto_etf_flows_signal():
    btc_flow = fetch_etf_flow_table("btc", "BTC ETF Flow")
    eth_flow = fetch_etf_flow_table("eth", "ETH ETF Flow")
    components = [btc_flow, eth_flow]
    available_components = [component for component in components if component["available"]]
    result = {
        "label": "Crypto ETF Flows",
        "value": None,
        "state": "Unavailable",
        "score": 0,
        "available": False,
        "components": components,
        "missing_components": [],
        "error": None,
    }
    if not available_components:
        result["error"] = "No ETF flow components available."
        return result
    total_flow = sum(component["value"] for component in available_components)
    total_score = sum(component["score"] for component in available_components)
    if total_flow >= 200:
        state = "Strong Net Inflow"
    elif total_flow > 0:
        state = "Net Inflow"
    elif total_flow <= -200:
        state = "Strong Net Outflow"
    elif total_flow < 0:
        state = "Net Outflow"
    else:
        state = "Flat"
    result.update(
        {
            "value": total_flow,
            "state": state,
            "score": max(min(total_score, 8), -8),
            "available": True,
            "missing_components": [component["label"] for component in components if not component["available"]],
        }
    )
    return result


def build_manual_etf_flows_signal(btc_flow, eth_flow):
    components = [
        {"label": "BTC ETF Flow", "value": btc_flow, "state": "Manual", "score": 0, "available": True},
        {"label": "ETH ETF Flow", "value": eth_flow, "state": "Manual", "score": 0, "available": True},
    ]
    total_flow = btc_flow + eth_flow
    if total_flow >= 200:
        state, score = "Strong Net Inflow", 8
    elif total_flow > 0:
        state, score = "Net Inflow", 4
    elif total_flow <= -200:
        state, score = "Strong Net Outflow", -8
    elif total_flow < 0:
        state, score = "Net Outflow", -4
    else:
        state, score = "Flat", 0
    return {
        "label": "Crypto ETF Flows",
        "value": total_flow,
        "state": f"{state} (Manual)",
        "score": score,
        "available": True,
        "components": components,
        "missing_components": [],
        "error": None,
    }


def classify_open_interest_fragility(change_pct):
    if change_pct >= 15:
        return "High Fragility", "Expanding Fast", -12
    if change_pct >= 5:
        return "Elevated Fragility", "Expanding", -6
    if change_pct <= -10:
        return "Low Fragility", "Contracting", 6
    return "Moderate Fragility", "Flat", 0


def fetch_open_interest_signal():
    result = {"label": "BTC Market Fragility", "value": None, "previous_value": None, "state": "Unavailable", "score": 0, "available": False, "change_pct": None, "oi_state": "Unavailable", "error": None}
    try:
        current_response = requests.get(
            "https://fapi.binance.com/fapi/v1/openInterest",
            params={"symbol": "BTCUSDT"},
            headers=DEFAULT_HTTP_HEADERS,
            timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS,
        )
        current_response.raise_for_status()
        current_payload = current_response.json()

        history_response = requests.get(
            "https://fapi.binance.com/futures/data/openInterestHist",
            params={"symbol": "BTCUSDT", "period": "1d", "limit": 8},
            headers=DEFAULT_HTTP_HEADERS,
            timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS,
        )
        history_response.raise_for_status()
        history_payload = history_response.json()
        if not isinstance(history_payload, list) or len(history_payload) < 2:
            result["error"] = "Not enough open interest history returned."
            return result
        latest_value = float(current_payload["openInterest"])
        previous_value = float(history_payload[0]["sumOpenInterest"])
        if previous_value == 0:
            result["error"] = "Invalid previous open interest value."
            return result
        change_pct = ((latest_value - previous_value) / previous_value) * 100
        state, oi_state, score = classify_open_interest_fragility(change_pct)
        result.update({"value": latest_value, "previous_value": previous_value, "state": state, "score": score, "available": True, "change_pct": change_pct, "oi_state": oi_state})
    except requests.RequestException as exc:
        result["error"] = f"Binance open interest request failed: {exc}"
    except Exception as exc:
        result["error"] = str(exc)
    return result


def fetch_bybit_open_interest_signal():
    result = {"label": "BTC Market Fragility", "value": None, "previous_value": None, "state": "Unavailable", "score": 0, "available": False, "change_pct": None, "oi_state": "Unavailable", "error": None}
    try:
        response = requests.get(
            "https://api.bybit.com/v5/market/open-interest",
            params={"category": "linear", "symbol": "BTCUSDT", "intervalTime": "1d", "limit": 8},
            headers=DEFAULT_HTTP_HEADERS,
            timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("result", {}).get("list", [])
        if not isinstance(rows, list) or len(rows) < 2:
            result["error"] = "Not enough Bybit open interest history returned."
            return result
        values = []
        for row in rows:
            if "openInterest" in row:
                values.append(float(row["openInterest"]))
        if len(values) < 2:
            result["error"] = "No Bybit open interest values found."
            return result
        latest_value = values[0]
        previous_value = values[-1]
        if previous_value == 0:
            result["error"] = "Invalid previous Bybit open interest value."
            return result
        change_pct = ((latest_value - previous_value) / previous_value) * 100
        state, oi_state, score = classify_open_interest_fragility(change_pct)
        result.update({"value": latest_value, "previous_value": previous_value, "state": state, "score": score, "available": True, "change_pct": change_pct, "oi_state": oi_state})
    except requests.RequestException as exc:
        result["error"] = f"Bybit open interest request failed: {exc}"
    except Exception as exc:
        result["error"] = str(exc)
    return result


def fetch_bitget_open_interest_signal():
    result = {"label": "BTC Market Fragility", "value": None, "previous_value": None, "state": "Unavailable", "score": 0, "available": False, "change_pct": None, "oi_state": "Unavailable", "error": None}
    try:
        response = requests.get(
            "https://api.bitget.com/api/v3/market/open-interest",
            params={"category": "USDT-FUTURES", "symbol": "BTCUSDT"},
            headers=DEFAULT_HTTP_HEADERS,
            timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data", {}).get("list", [])
        if not isinstance(rows, list) or not rows:
            result["error"] = "No Bitget open interest rows returned."
            return result
        current_value = float(rows[0]["openInterest"])

        cached = load_feed_cache("macro_open_interest")
        previous_value = None
        if cached:
            cached_data, _ = cached
            try:
                previous_value = float(cached_data.get("value")) if cached_data.get("value") is not None else None
            except (TypeError, ValueError):
                previous_value = None

        if previous_value and previous_value != 0:
            change_pct = ((current_value - previous_value) / previous_value) * 100
            state, oi_state, score = classify_open_interest_fragility(change_pct)
            result.update({"value": current_value, "previous_value": previous_value, "state": state, "score": score, "available": True, "change_pct": change_pct, "oi_state": oi_state})
        else:
            # First successful fallback read: seed a usable baseline so the card is not blank.
            result.update({"value": current_value, "previous_value": current_value, "state": "Moderate Fragility", "score": 0, "available": True, "change_pct": None, "oi_state": "First Reading"})
    except requests.RequestException as exc:
        result["error"] = f"Bitget open interest request failed: {exc}"
    except Exception as exc:
        result["error"] = str(exc)
    return result


def fetch_best_open_interest_signal():
    primary = fetch_open_interest_signal()
    if primary.get("available"):
        return primary
    secondary = fetch_bybit_open_interest_signal()
    if secondary.get("available"):
        secondary["fallback_used"] = True
        secondary["fallback_source"] = secondary.get("fallback_source") or secondary.get("source") or "fallback"
        return secondary
    tertiary = fetch_bitget_open_interest_signal()
    return choose_best_signal(secondary, tertiary)


def fetch_fear_greed_signal():
    result = {"value": None, "label": "Unavailable", "score": 0, "error": None}
    try:
        with urlopen("https://api.alternative.me/fng/?limit=1&format=json", timeout=EXTERNAL_FETCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        value = int(payload["data"][0]["value"])
        label = payload["data"][0]["value_classification"]
        score = -12 if value >= 75 else -6 if value >= 55 else 0 if value > 45 else 6 if value > 25 else 12
        result.update({"value": value, "label": label, "score": score})
    except (URLError, HTTPError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
        result["error"] = str(exc)
    return result


@st.cache_data(ttl=EXTERNAL_SIGNAL_CACHE_TTL_SECONDS, show_spinner=False)
def load_external_signals(manual_etf_enabled, manual_btc_etf_flow, manual_eth_etf_flow):
    jobs = {
        "dxy_signal": lambda: get_feed_result("macro_dxy_v2", fetch_dxy_signal),
        "us2y_signal": lambda: get_feed_result("macro_us2y", lambda: fetch_fred_signal("DGS2", "US 2Y Treasury", -8, 8)),
        "us10y_signal": lambda: get_feed_result("macro_us10y", fetch_us10y_signal),
        "jp10y_signal": lambda: get_feed_result("macro_jp10y", lambda: fetch_fred_signal("IRLTLT01JPM156N", "Japan 10Y Govt Bond", -6, 6)),
        "oil_signal": lambda: get_feed_result("macro_wti", fetch_wti_signal),
        "stablecoin_signal": lambda: get_feed_result("macro_stablecoins", fetch_stablecoin_liquidity_signal),
        "global_liquidity_signal": lambda: get_feed_result("macro_global_liquidity", build_global_liquidity_proxy),
        "etf_flows_signal": lambda: get_feed_result("macro_etf_flows", fetch_crypto_etf_flows_signal),
        "open_interest_signal": lambda: get_feed_result("macro_open_interest", fetch_best_open_interest_signal),
        "fear_greed_signal": fetch_fear_greed_signal,
    }
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        future_map = {executor.submit(job): name for name, job in jobs.items()}
        for future in concurrent.futures.as_completed(future_map):
            name = future_map[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                if name.endswith("_signal"):
                    fallback_label = name.replace("_signal", "").replace("_", " ").title()
                    results[name] = {"label": fallback_label, "available": False, "score": 0, "error": str(exc)}
                else:
                    results[name] = {"error": str(exc)}
    if not results["etf_flows_signal"]["available"] and manual_etf_enabled:
        results["etf_flows_signal"] = build_manual_etf_flows_signal(manual_btc_etf_flow, manual_eth_etf_flow)
    return results

init_auth_state()
st.session_state.setdefault("ai_summary_result", None)
st.session_state.setdefault("ai_summary_fingerprint", None)
st.session_state.setdefault("ai_summary_error", None)
if not current_user_id():
    render_auth_gate()

public_market_defaults = load_public_defaults(PUBLIC_MARKET_DEFAULTS_FILE, MARKET_INPUT_DEFAULTS)
public_analyst_defaults = load_public_defaults(PUBLIC_ANALYST_DEFAULTS_FILE, ANALYST_DEFAULTS)
public_news_defaults = load_public_defaults(PUBLIC_NEWS_DEFAULTS_FILE, NEWS_DEFAULTS)
public_context_defaults = load_public_defaults(PUBLIC_CONTEXT_DEFAULTS_FILE, CONTEXT_DEFAULTS)
applied_payload = apply_pending_session_payload()
seed_session_defaults(public_market_defaults)
seed_session_defaults(public_analyst_defaults)
seed_session_defaults(public_news_defaults)
seed_session_defaults(public_context_defaults)
pending_market_override = bool(applied_payload and any(key in applied_payload for key in MARKET_INPUT_DEFAULTS))
if pending_market_override:
    st.session_state["market_inputs_loaded_user_id"] = current_user_id()
    st.session_state["market_inputs_last_saved"] = collect_session_payload(MARKET_INPUT_DEFAULTS)
else:
    dashboard_bootstrapped = bootstrap_dashboard_for_user()
    if not dashboard_bootstrapped:
        st.session_state["saved_dashboard_snapshot"] = None
if current_user_id() and not st.session_state.get("session_event_logged"):
    log_user_event("app_session_started", {"email": current_user().get("email", "")})
    st.session_state["session_event_logged"] = True
sync_widget_state_from_model()

st.sidebar.markdown("### Account")
st.sidebar.caption(current_user().get("email", "Signed in"))
account_save_col, account_default_col = st.sidebar.columns(2)
with account_save_col:
    if st.button("Save Dashboard", use_container_width=True):
        try:
            sync_model_state_from_widgets()
            save_dashboard()
        except RuntimeError as exc:
            st.sidebar.error(str(exc))
        else:
            st.sidebar.success("Dashboard saved for next session")
with account_default_col:
    if st.button("Load Oracle Defaults", use_container_width=True):
        log_user_event("load_oracle_defaults", {"owner": is_oracle_owner()})
        queue_session_payload(
            load_oracle_defaults(),
            "Oracle defaults loaded",
        )
        st.rerun()
if st.sidebar.button("Log out", use_container_width=True):
    sign_out_user()
    st.rerun()

st.sidebar.header("Display")
dark_mode = st.sidebar.toggle("Dark Mode", value=False, key="dark_mode")
theme = get_theme_colors(dark_mode)

st.markdown(f"""
<style>
.stApp {{
    background:
        radial-gradient(circle at 12% 0%, rgba(220,38,38,0.18), transparent 28%),
        radial-gradient(circle at 88% 10%, rgba(22,163,74,0.10), transparent 24%),
        linear-gradient(180deg, {theme['app_bg']} 0%, {theme['app_bg']} 100%);
    color: {theme['text']};
}}
.block-container {{
    padding-top: 0.05rem;
}}
.main {{ padding-top: 0rem; }}
.brand-row {{
    display: flex;
    align-items: center;
    justify-content: flex-start;
    margin: 0;
}}
.brand-card {{
    background: linear-gradient(180deg, rgba(255,255,255,0.78) 0%, rgba(255,255,255,0.54) 100%);
    border: 1px solid rgba(153,27,27,0.16);
    border-radius: 18px;
    padding: 8px 14px 6px 14px;
    box-shadow: 0 18px 38px rgba(0,0,0,0.10);
    display: inline-flex;
    align-items: center;
}}
.brand-card.dark {{
    background: linear-gradient(180deg, #120c0b 0%, #050505 100%);
    border: 1px solid rgba(239,68,68,0.22);
    box-shadow: 0 18px 38px rgba(0,0,0,0.18);
}}
.big-title {{
    font-size: 1.35rem;
    font-weight: 900;
    margin-bottom: 0.2rem;
    letter-spacing: -1px;
    color: {theme['text']};
    text-transform: uppercase;
}}
.brand-logo {{
    max-width: 215px;
    margin: 0;
}}
.brand-kicker {{
    color: #dc2626;
    font-size: 0.74rem;
    font-weight: 800;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}}
.bias-box {{
    padding: 12px 20px;
    border-radius: 18px;
    color: white;
    text-align: left;
    margin-bottom: 12px;
    box-shadow: 0 18px 42px rgba(0,0,0,0.32);
    border: 1px solid rgba(255,255,255,0.18);
    position: relative;
    overflow: hidden;
}}
.bias-box:before {{
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.18), transparent 42%);
    pointer-events: none;
}}
.status-grid {{
    display: grid;
    grid-template-columns: 1.5fr 1fr 1fr 1fr;
    gap: 14px;
    align-items: center;
    position: relative;
    z-index: 1;
}}
.status-label {{
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    opacity: 0.78;
    margin-bottom: 4px;
}}
.status-value {{
    font-size: 1.35rem;
    font-weight: 900;
    line-height: 1.1;
}}
.status-value.large {{
    font-size: 1.8rem;
}}
.status-cell {{
    border-left: 1px solid rgba(255,255,255,0.22);
    padding-left: 16px;
}}
.status-cell:first-child {{
    border-left: none;
    padding-left: 0;
}}
.driver-box {{
    background: linear-gradient(180deg, {theme['card_bg']} 0%, rgba(127,29,29,0.05) 100%);
    border: 1px solid {theme['card_border']};
    border-radius: 18px;
    padding: 18px;
    box-shadow: {theme['card_shadow']};
    margin-bottom: 14px;
    color: {theme['text']};
}}
.driver-box.core-intro {{
    padding: 7px 14px;
    margin-bottom: 10px;
    border-radius: 12px;
    box-shadow: none;
}}
.driver-box.core-intro .small-muted {{
    display: block;
    font-size: 0.82rem;
    margin-top: 3px;
}}
.driver-box.core-intro .section-title {{
    margin-bottom: 0;
    font-size: 0.9rem;
}}
.driver-line {{ font-size: 1rem; padding: 6px 0; border-bottom: 1px solid {theme['divider']}; }}
.driver-line:last-child {{ border-bottom: none; }}
.summary-box {{ background: {theme['card_bg']}; border: 1px solid {theme['card_border']}; border-radius: 18px; padding: 18px; box-shadow: {theme['card_shadow']}; margin-top: 20px; margin-bottom: 20px; color: {theme['text']}; }}
.guide-box {{ background: {theme['card_bg']}; border: 1px solid {theme['card_border']}; border-radius: 18px; padding: 18px; box-shadow: {theme['card_shadow']}; margin-top: 16px; color: {theme['text']}; }}
.section-title {{
    font-size: 1.05rem;
    font-weight: 850;
    margin-bottom: 8px;
    color: {theme['text']};
    letter-spacing: 0.01em;
}}
.section-title:before {{
    content: "";
    display: inline-block;
    width: 8px;
    height: 18px;
    background: #dc2626;
    border-radius: 99px;
    margin-right: 8px;
    vertical-align: -3px;
}}
.small-muted {{ color: {theme['muted']}; font-size: 0.92rem; }}
.info-heading-row {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
}}
.info-heading-title {{
    font-size: 1.05rem;
    font-weight: 850;
    color: {theme['text']};
    line-height: 1.2;
}}
.info-tooltip-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    border-radius: 999px;
    border: 1px solid {theme['card_border']};
    color: {theme['muted']};
    font-size: 0.74rem;
    font-weight: 800;
    cursor: help;
    user-select: none;
}}
.info-caption {{
    color: {theme['muted']};
    font-size: 0.86rem;
    line-height: 1.35;
    margin-bottom: 10px;
}}
div[data-testid="stButton"] > button {{
    background: {"#221714" if dark_mode else "#fffdfb"};
    color: {"#f8fafc" if dark_mode else "#1c1917"};
    border: 1px solid {"rgba(239,68,68,0.34)" if dark_mode else "rgba(153,27,27,0.16)"};
    border-radius: 12px;
    box-shadow: {theme['card_shadow']};
}}
div[data-testid="stButton"] > button:hover {{
    border-color: rgba(239,68,68,0.55);
    color: {"#ffffff" if dark_mode else "#111111"};
}}
div[data-testid="stButton"] > button:disabled,
div[data-testid="stButton"] > button[disabled] {{
    background: {"#1a1311" if dark_mode else "#f4f4f5"};
    color: {"#a8a29e" if dark_mode else "#71717a"};
    border: 1px solid {"rgba(120,113,108,0.26)" if dark_mode else "rgba(161,161,170,0.3)"};
    opacity: 1;
}}
div[data-testid="stMetric"] {{
    background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(220,38,38,0.075)), {theme['card_bg']};
    border: 1px solid rgba(239,68,68,0.42);
    border-radius: 14px;
    padding: 12px 14px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), {theme['card_shadow']};
}}
div[data-testid="stMetric"] label {{
    color: {theme['muted']};
}}
div[data-testid="stMetricValue"] {{
    color: {theme['text']};
}}
</style>
""", unsafe_allow_html=True)

st.sidebar.header("Market Inputs")
total_3d_state = st.sidebar.selectbox(
    "TOTAL 3D Trend State",
    ["Confirmed Bearish", "Bearish Cross", "Soft Bearish", "Neutral", "Soft Bullish", "Bullish Cross", "Confirmed Bullish"],
    key="ui_total_3d_state",
)
total_1d_supertrend = st.sidebar.selectbox(
    "TOTAL 1D Signal State",
    ["Bearish", "Bearish Cross", "Soft Bearish", "Soft Bullish", "Bullish"],
    key="ui_total_1d_supertrend",
)
sync_model_state_from_widgets()

st.sidebar.header("Analyst Profiles")
st.sidebar.header("Analyst Consensus")
analyst1_name = st.sidebar.text_input("Analyst 1 Name", "Analyst 1", key="analyst1_name")
analyst1_bias = st.sidebar.selectbox("Analyst 1 Bias", ["Bearish", "Neutral", "Bullish"], key="analyst1_bias")
analyst1_conf = st.sidebar.slider("Analyst 1 Confidence", 0, 100, 70, key="analyst1_conf")
analyst1_weight = st.sidebar.slider("Analyst 1 Weight", 0.5, 2.0, 1.0, 0.1, key="analyst1_weight")
analyst1_timeframe = st.sidebar.selectbox("Analyst 1 Timeframe", ["Swing", "Long Term"], key="analyst1_timeframe")
analyst1_notes = st.sidebar.text_area("Analyst 1 Notes", "Add notes here", key="analyst1_notes")
analyst2_name = st.sidebar.text_input("Analyst 2 Name", "Analyst 2", key="analyst2_name")
analyst2_bias = st.sidebar.selectbox("Analyst 2 Bias", ["Bearish", "Neutral", "Bullish"], key="analyst2_bias")
analyst2_conf = st.sidebar.slider("Analyst 2 Confidence", 0, 100, 60, key="analyst2_conf")
analyst2_weight = st.sidebar.slider("Analyst 2 Weight", 0.5, 2.0, 1.0, 0.1, key="analyst2_weight")
analyst2_timeframe = st.sidebar.selectbox("Analyst 2 Timeframe", ["Swing", "Long Term"], key="analyst2_timeframe")
analyst2_notes = st.sidebar.text_area("Analyst 2 Notes", "Add notes here ", key="analyst2_notes")
analyst3_name = st.sidebar.text_input("Analyst 3 Name", "Analyst 3", key="analyst3_name")
analyst3_bias = st.sidebar.selectbox("Analyst 3 Bias", ["Bearish", "Neutral", "Bullish"], key="analyst3_bias")
analyst3_conf = st.sidebar.slider("Analyst 3 Confidence", 0, 100, 50, key="analyst3_conf")
analyst3_weight = st.sidebar.slider("Analyst 3 Weight", 0.5, 2.0, 1.0, 0.1, key="analyst3_weight")
analyst3_timeframe = st.sidebar.selectbox("Analyst 3 Timeframe", ["Swing", "Long Term"], key="analyst3_timeframe")
analyst3_notes = st.sidebar.text_area("Analyst 3 Notes", "Add notes here  ", key="analyst3_notes")

st.sidebar.header("News / Macro News")
news_categories = ["Regulation", "Geopolitics", "Macro", "ETF / Institutional", "Stablecoins", "Security / Exchange"]
news1_headline = st.sidebar.text_input("News 1 Headline", "ETF inflows rise", key="news1_headline")
news1_direction = st.sidebar.selectbox("News 1 Direction", ["Bearish", "Neutral", "Bullish"], key="news1_direction")
news1_impact = st.sidebar.slider("News 1 Impact", 1, 5, 4, key="news1_impact")
news1_category = st.sidebar.selectbox("News 1 Category", news_categories, key="news1_category")
news1_notes = st.sidebar.text_area("News 1 Notes", "Add news notes here", key="news1_notes")
news2_headline = st.sidebar.text_input("News 2 Headline", "Geopolitical tensions rise", key="news2_headline")
news2_direction = st.sidebar.selectbox("News 2 Direction", ["Bearish", "Neutral", "Bullish"], key="news2_direction")
news2_impact = st.sidebar.slider("News 2 Impact", 1, 5, 3, key="news2_impact")
news2_category = st.sidebar.selectbox("News 2 Category", news_categories, key="news2_category")
news2_notes = st.sidebar.text_area("News 2 Notes", "Add news notes here ", key="news2_notes")
news3_headline = st.sidebar.text_input("News 3 Headline", "Stablecoin bill advances", key="news3_headline")
news3_direction = st.sidebar.selectbox("News 3 Direction", ["Bearish", "Neutral", "Bullish"], key="news3_direction")
news3_impact = st.sidebar.slider("News 3 Impact", 1, 5, 5, key="news3_impact")
news3_category = st.sidebar.selectbox("News 3 Category", news_categories, key="news3_category")
news3_notes = st.sidebar.text_area("News 3 Notes", "Add news notes here  ", key="news3_notes")

st.sidebar.header("ETF Flows")
st.sidebar.caption("Used only when the live ETF flow feed is unavailable.")
manual_etf_enabled = st.sidebar.checkbox("Use Manual ETF Flow Fallback", value=True, key="ui_manual_etf_enabled")
manual_btc_etf_flow = st.sidebar.number_input("Manual BTC ETF Flow (US$m)", value=0.0, step=25.0, key="ui_manual_btc_etf_flow")
manual_eth_etf_flow = st.sidebar.number_input("Manual ETH ETF Flow (US$m)", value=0.0, step=25.0, key="ui_manual_eth_etf_flow")
sync_model_state_from_widgets()

st.sidebar.header("Astro + Recommended Content")
st.sidebar.caption("Optional context and curated resources. Excluded from scoring.")
astro_lunar_event = st.sidebar.text_input("Lunar Event", "None", key="astro_lunar_event")
astro_transits = st.sidebar.text_input("Transits Worth Noting", "Sun trine Jupiter, Mercury conjunct Venus", key="astro_transits")
astro_market_theme = st.sidebar.selectbox("Astro Market Theme", ["Expansion", "Volatility", "Reversal Watch", "Consolidation", "Risk-Off Tone", "Neutral"], key="astro_market_theme")
share_video = st.sidebar.text_input("Recommended Video", "Paste a video link or short title", key="share_video")
share_article = st.sidebar.text_input("Recommended Article", "Paste an article link or short title", key="share_article")
share_why = st.sidebar.text_area("Why It Matters", "Explain why this content matters right now.", key="share_why")
share_takeaway = st.sidebar.text_area("Market Connection", "Explain how this may connect to crypto, macro, or geopolitics.", key="share_takeaway")

state_scores_3d = {"Confirmed Bearish": -40, "Bearish Cross": -25, "Soft Bearish": -10, "Neutral": 0, "Soft Bullish": 10, "Bullish Cross": 25, "Confirmed Bullish": 40}
score_3d = state_scores_3d[total_3d_state]
state_scores_1d = {"Bearish": -10, "Bearish Cross": -7, "Soft Bearish": -4, "Soft Bullish": 4, "Bullish": 10}
score_1d = state_scores_1d[total_1d_supertrend]
ta_score = score_3d + score_1d
bias_map = {"Bearish": -1, "Neutral": 0, "Bullish": 1}
analyst_score = max(min((bias_map[analyst1_bias] * analyst1_conf * analyst1_weight + bias_map[analyst2_bias] * analyst2_conf * analyst2_weight + bias_map[analyst3_bias] * analyst3_conf * analyst3_weight) / 3, 100), -100)
news_score = max(min(bias_map[news1_direction] * news1_impact * 10 + bias_map[news2_direction] * news2_impact * 10 + bias_map[news3_direction] * news3_impact * 10, 100), -100)
analyst_rows = [
    {"name": analyst1_name, "bias": analyst1_bias, "confidence": analyst1_conf, "weight": analyst1_weight, "timeframe": analyst1_timeframe},
    {"name": analyst2_name, "bias": analyst2_bias, "confidence": analyst2_conf, "weight": analyst2_weight, "timeframe": analyst2_timeframe},
    {"name": analyst3_name, "bias": analyst3_bias, "confidence": analyst3_conf, "weight": analyst3_weight, "timeframe": analyst3_timeframe},
]
news_rows = [
    {"headline": news1_headline, "direction": news1_direction, "impact": news1_impact, "category": news1_category},
    {"headline": news2_headline, "direction": news2_direction, "impact": news2_impact, "category": news2_category},
    {"headline": news3_headline, "direction": news3_direction, "impact": news3_impact, "category": news3_category},
]

dashboard_loading = st.empty()
if st.session_state.get("post_login_loading"):
    dashboard_loading.info("Signing you in and loading the dashboard...")
external_signals = load_external_signals(manual_etf_enabled, manual_btc_etf_flow, manual_eth_etf_flow)
st.session_state["post_login_loading"] = False
dashboard_loading.empty()

dxy_signal = external_signals["dxy_signal"]
us2y_signal = external_signals["us2y_signal"]
us10y_signal = external_signals["us10y_signal"]
jp10y_signal = external_signals["jp10y_signal"]
oil_signal = external_signals["oil_signal"]
stablecoin_signal = external_signals["stablecoin_signal"]
global_liquidity_signal = external_signals["global_liquidity_signal"]
etf_flows_signal = external_signals["etf_flows_signal"]
open_interest_signal = external_signals["open_interest_signal"]
macro_score = dxy_signal["score"] + us2y_signal["score"] + us10y_signal["score"] + jp10y_signal["score"] + oil_signal["score"] + stablecoin_signal["score"] + global_liquidity_signal["score"] + etf_flows_signal["score"]
macro_unavailable = [signal["label"] for signal in [dxy_signal, us2y_signal, us10y_signal, jp10y_signal, oil_signal, stablecoin_signal, global_liquidity_signal, etf_flows_signal] if not signal["available"]]
macro_cached = [signal["label"] for signal in [dxy_signal, us2y_signal, us10y_signal, jp10y_signal, oil_signal, stablecoin_signal, global_liquidity_signal, etf_flows_signal] if signal.get("cached")]
macro_error_details = []
for signal in [dxy_signal, us2y_signal, us10y_signal, jp10y_signal, oil_signal, stablecoin_signal, etf_flows_signal]:
    if signal.get("cached") and signal.get("live_error"):
        macro_error_details.append(f"{signal['label']}: live fetch failed, using cached value. {signal['live_error']}")
    elif not signal["available"] and signal.get("error"):
        macro_error_details.append(f"{signal['label']}: {signal['error']}")
if not global_liquidity_signal["available"]:
    if global_liquidity_signal.get("error"):
        macro_error_details.append(f"{global_liquidity_signal['label']}: {global_liquidity_signal['error']}")
    for component in global_liquidity_signal.get("components", []):
        if not component["available"] and component.get("error"):
            macro_error_details.append(f"{component['label']}: {component['error']}")
elif global_liquidity_signal.get("cached") and global_liquidity_signal.get("live_error"):
    macro_error_details.append(f"{global_liquidity_signal['label']}: live fetch failed, using cached value. {global_liquidity_signal['live_error']}")

fear_greed_signal = external_signals["fear_greed_signal"]
fng_value = fear_greed_signal["value"]
fng_label = fear_greed_signal["label"]
fng_score = fear_greed_signal["score"]
fng_error = fear_greed_signal["error"]
open_interest_component_score = open_interest_signal["score"] if open_interest_signal["available"] else 0
sentiment_weight_total = 0.0
sentiment_weighted_sum = 0.0
if fng_value is not None:
    sentiment_weight_total += SENTIMENT_FNG_WEIGHT
    sentiment_weighted_sum += SENTIMENT_FNG_WEIGHT * fng_score
if open_interest_signal["available"]:
    sentiment_weight_total += SENTIMENT_OPEN_INTEREST_WEIGHT
    sentiment_weighted_sum += SENTIMENT_OPEN_INTEREST_WEIGHT * open_interest_component_score
sentiment_score = (sentiment_weighted_sum / sentiment_weight_total) if sentiment_weight_total else 0

final_score = (TA_WEIGHT * ta_score) + (ANALYST_WEIGHT * analyst_score) + (NEWS_WEIGHT * news_score) + (MACRO_WEIGHT * macro_score) + (SENTIMENT_WEIGHT * sentiment_score)
ta_contribution = TA_WEIGHT * ta_score
analyst_contribution = ANALYST_WEIGHT * analyst_score
news_contribution = NEWS_WEIGHT * news_score
macro_contribution = MACRO_WEIGHT * macro_score
sentiment_contribution = SENTIMENT_WEIGHT * sentiment_score
if final_score >= 25:
    bias, bias_color = "Bullish", "#16a34a"
elif final_score <= -25:
    bias, bias_color = "Bearish", "#dc2626"
else:
    bias, bias_color = "Neutral", "#ca8a04"

signal_strength = min(abs(final_score), 100)
conviction_label = "Very Low" if signal_strength < 20 else "Low" if signal_strength < 40 else "Moderate" if signal_strength < 60 else "High" if signal_strength < 80 else "Very High"

logo_path = "assets/LOGO_transparent.png" if dark_mode else "assets/logo_little_red_tricycle_light.png"
brand_card_class = "brand-card dark" if dark_mode else "brand-card"
header_logo_col, header_status_col = st.columns([0.95, 6.2], gap="small")
with header_logo_col:
    st.markdown(f'<div class="brand-row"><div class="{brand_card_class}">', unsafe_allow_html=True)
    st.image(logo_path, width=185)
    st.markdown('</div></div>', unsafe_allow_html=True)
with header_status_col:
    st.markdown(f"""
<div class="bias-box" style="background-color:{bias_color};">
    <div class="status-grid">
        <div class="status-cell">
            <div class="status-label">Market Regime</div>
            <div class="status-value large">{bias}</div>
        </div>
        <div class="status-cell">
            <div class="status-label">Signal Strength</div>
            <div class="status-value">{signal_strength:.1f}%</div>
        </div>
        <div class="status-cell">
            <div class="status-label">Conviction</div>
            <div class="status-value">{conviction_label}</div>
        </div>
        <div class="status-cell">
            <div class="status-label">Final Score</div>
            <div class="status-value">{final_score:.1f}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="driver-box core-intro">
    <div class="section-title">Core Dashboard</div>
    <div class="small-muted">These are the five scored layers used to form the final market bias. Each section analyzes a different part of the market so the result is based on structure, sentiment, narrative, and macro conditions together rather than one signal alone.</div>
</div>
""", unsafe_allow_html=True)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.markdown(
        """
<div class="info-heading-row">
    <div class="info-heading-title">Technical Analysis</div>
    <span class="info-tooltip-icon" title="Measures TOTAL market-cap structure using the 3D and 1D trend states. This section looks at broader trend direction, shorter-term momentum, and whether price action is confirming strength, weakness, or a neutral setup.">i</span>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption("TOTAL 3D + 1D")
    st.metric("TOTAL 3D Score", score_3d)
    st.write(f"3D State: **{total_3d_state}**")
    st.metric("TOTAL 1D Signal Score", score_1d)
    st.write(f"1D State: **{total_1d_supertrend}**")
    st.metric("Combined TA Score", ta_score)
with col2:
    st.markdown(
        """
<div class="info-heading-row">
    <div class="info-heading-title">Analyst Consensus</div>
    <span class="info-tooltip-icon" title="Combines the selected analyst views using their bias, confidence, weight, and timeframe. The goal is to estimate whether trusted market commentators are collectively leaning bullish, bearish, or mixed.">i</span>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption("Weighted analyst views")
    st.metric("Consensus Score", round(analyst_score, 1))
    for name, bias_label, conf, weight, timeframe, notes in [
        (analyst1_name, analyst1_bias, analyst1_conf, analyst1_weight, analyst1_timeframe, analyst1_notes),
        (analyst2_name, analyst2_bias, analyst2_conf, analyst2_weight, analyst2_timeframe, analyst2_notes),
        (analyst3_name, analyst3_bias, analyst3_conf, analyst3_weight, analyst3_timeframe, analyst3_notes),
    ]:
        st.markdown(f"**{name}**")
        st.markdown(tag_html(bias_label), unsafe_allow_html=True)
        st.write(f"Confidence: {conf} | Weight: {weight}")
        st.write(f"Timeframe: **{timeframe}**")
        st.write(f"Notes: {notes}")
        if name != analyst3_name:
            st.divider()
with col3:
    st.markdown(
        """
<div class="info-heading-row">
    <div class="info-heading-title">News / Macro News</div>
    <span class="info-tooltip-icon" title="Scores major headlines by their direction, category, and expected impact. This section is meant to capture whether the current narrative backdrop is adding support, creating risk, or leaving the market mixed.">i</span>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption("Headline impact tracker")
    st.metric("News Score", news_score)
    for idx, headline, direction, category, impact, notes in [
        (1, news1_headline, news1_direction, news1_category, news1_impact, news1_notes),
        (2, news2_headline, news2_direction, news2_category, news2_impact, news2_notes),
        (3, news3_headline, news3_direction, news3_category, news3_impact, news3_notes),
    ]:
        st.markdown(f"**{idx}. {headline}**")
        st.markdown(tag_html(direction), unsafe_allow_html=True)
        st.write(f"Category: **{category}**")
        st.write(f"Impact: {impact}")
        st.write(f"Notes: {notes}")
        if idx != 3:
            st.divider()
with col4:
    st.markdown(
        """
<div class="info-heading-row">
    <div class="info-heading-title">Macro / Liquidity</div>
    <span class="info-tooltip-icon" title="Tracks rates, DXY, oil, stablecoin supply, global liquidity, and ETF flows to judge whether the broader financial backdrop is adding support to crypto or creating pressure against it.">i</span>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption("Rates + DXY + Oil + Stablecoin Supply + Global Liquidity + ETF Flows")
    st.metric("Macro Score", macro_score)
    for signal in [us2y_signal, us10y_signal, jp10y_signal, dxy_signal, oil_signal]:
        if signal["available"]:
            st.write(f"{signal['label']}: **{signal['state']}** ({signal['score']}) | Last: {signal['value']:.2f}")
            if signal["label"] == "DXY" and signal.get("fallback_used"):
                st.caption(f"DXY feed detail: using fallback source{'. ' + signal['error'] if signal.get('error') else ''}")
        else:
            st.write(f"{signal['label']}: **Unavailable** (0) | Last: N/A")
            if signal["label"] == "DXY" and signal.get("error"):
                st.caption(f"DXY feed detail: {signal['error']}")
    if stablecoin_signal["available"]:
        st.write(f"{stablecoin_signal['label']}: **{stablecoin_signal['state']}** ({stablecoin_signal['score']}) | Last: ${stablecoin_signal['value'] / 1_000_000_000:.1f}B")
        st.write(f"7D Change: **{stablecoin_signal['change_pct']:+.2f}%**")
    else:
        st.write(f"{stablecoin_signal['label']}: **Unavailable** (0) | Last: N/A")
    if global_liquidity_signal["available"]:
        st.write(f"{global_liquidity_signal['label']}: **{global_liquidity_signal['state']}** ({global_liquidity_signal['score']})")
        if global_liquidity_signal["missing_components"]:
            st.caption("Using available components only: " + ", ".join(global_liquidity_signal["missing_components"]))
        for component in global_liquidity_signal["components"]:
            if component["available"] and component.get("change_pct") is not None:
                st.write(f"{component['label']}: **{component['state']}** ({component['score']}) | Change: {component['change_pct']:+.2f}%")
            else:
                st.write(f"{component['label']}: **Unavailable** (0)")
    else:
        st.write(f"{global_liquidity_signal['label']}: **Unavailable** (0)")
    if etf_flows_signal["available"]:
        st.write(f"{etf_flows_signal['label']}: **{etf_flows_signal['state']}** ({etf_flows_signal['score']}) | Latest: ${etf_flows_signal['value']:.1f}M")
        for component in etf_flows_signal["components"]:
            if component["available"]:
                st.write(f"{component['label']}: **{component['state']}** | ${component['value']:.1f}M")
            else:
                st.write(f"{component['label']}: **Unavailable**")
    else:
        st.write(f"{etf_flows_signal['label']}: **Unavailable** (0)")
    if macro_unavailable:
        st.caption(f"Unavailable feeds: {', '.join(macro_unavailable)}")
    if macro_cached:
        st.caption(f"Cached feeds in use: {', '.join(macro_cached)}")
    if macro_error_details:
        with st.expander("Macro Feed Diagnostics"):
            for detail in macro_error_details:
                st.write(detail)
with col5:
    st.markdown(
        """
<div class="info-heading-row">
    <div class="info-heading-title">Sentiment / Positioning</div>
    <span class="info-tooltip-icon" title="Uses Fear and Greed plus BTC positioning data to gauge crowd emotion and market fragility. This section helps identify when sentiment is stable, overheated, fearful, or vulnerable to sharper moves.">i</span>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption("Fear & Greed + BTC open interest")
    st.metric("Sentiment Score", round(sentiment_score, 1))
    if fng_value is not None:
        st.write(f"Value: **{fng_value}**")
        st.write(f"Classification: **{fng_label}**")
    else:
        st.write("Value: **N/A**")
        st.write("Classification: **Unavailable**")
        if fng_error:
            st.caption("Fear & Greed feed unavailable right now.")
    st.divider()
    if open_interest_signal["available"]:
        st.write(f"{open_interest_signal['label']}: **{open_interest_signal['state']}**")
        st.write(f"Fragility Score: **{open_interest_signal['score']}**")
        st.write(f"Current: **{open_interest_signal['value']:,.0f} BTC**")
        st.write(f"Open Interest Trend: **{open_interest_signal['oi_state']}**")
        if open_interest_signal.get("change_pct") is not None:
            st.write(f"7D Change: **{open_interest_signal['change_pct']:+.2f}%**")
        else:
            st.write("7D Change: **Tracking from first reading**")
    else:
        st.write("BTC Market Fragility: **Unavailable**")
        if open_interest_signal.get("error"):
            st.caption(f"Feed detail: {open_interest_signal['error']}")

ai_summary_payload = build_ai_summary_payload(
    bias=bias,
    final_score=final_score,
    signal_strength=signal_strength,
    conviction_label=conviction_label,
    total_3d_state=total_3d_state,
    score_3d=score_3d,
    total_1d_supertrend=total_1d_supertrend,
    score_1d=score_1d,
    ta_score=ta_score,
    analyst_score=analyst_score,
    news_score=news_score,
    macro_score=macro_score,
    sentiment_score=sentiment_score,
    fng_score=fng_score,
    fng_value=fng_value,
    fng_label=fng_label,
    stablecoin_signal=stablecoin_signal,
    global_liquidity_signal=global_liquidity_signal,
    etf_flows_signal=etf_flows_signal,
    open_interest_signal=open_interest_signal,
    macro_unavailable=macro_unavailable,
    analyst_rows=analyst_rows,
    news_rows=news_rows,
)
ai_summary_fingerprint = get_ai_summary_fingerprint(ai_summary_payload)
current_dashboard_payload = collect_session_payload(get_dashboard_payload_defaults())
saved_dashboard_changes = build_saved_dashboard_changes(st.session_state.get("saved_dashboard_snapshot"), current_dashboard_payload)
show_owner_signals = is_oracle_owner()
if show_owner_signals:
    signal_section_data = load_signal_section_data()
    buy_signal_data = signal_section_data["buy"]
    sell_signal_assets = signal_section_data["sell_assets"]
    sell_warning_summary = signal_section_data["sell_warning_summary"]
    hard_sell_summary = signal_section_data["hard_sell_summary"]
    dream_sell_summary = signal_section_data["dream_sell_summary"]
else:
    signal_section_data = None
    buy_signal_data = {}
    sell_signal_assets = []
    sell_warning_summary = {"label": "Hidden", "active_assets": [], "recent_assets": []}
    hard_sell_summary = {"label": "Hidden", "active_assets": [], "recent_assets": []}
    dream_sell_summary = {"label": "Hidden", "active_assets": [], "recent_assets": []}

st.markdown(f"""
<div class="summary-box">
    <div class="section-title">Summary</div>
    <div class="small-muted">
        The current market bias is <b>{bias}</b> with <b>{signal_strength:.1f}% signal strength</b> and <b>{conviction_label}</b> conviction.
        TOTAL on the 3D is <b>{total_3d_state}</b> for <b>{score_3d}</b> points.
        The TOTAL daily signal state is <b>{total_1d_supertrend}</b> for <b>{score_1d}</b> points.
        Combined TA score is <b>{ta_score}</b>. Analyst consensus score is <b>{analyst_score:.1f}</b>.
        News / macro score is <b>{news_score}</b>. Macro / liquidity score is <b>{macro_score}</b>. Sentiment / positioning score is <b>{sentiment_score:.1f}</b>.
    </div>
</div>
""", unsafe_allow_html=True)
st.caption("Signal strength guide: 0-19.9 Very Low | 20-39.9 Low | 40-59.9 Moderate | 60-79.9 High | 80-100 Very High")

if show_owner_signals:
    st.markdown(
        """
<div class="driver-box">
    <div class="section-title">Signals</div>
    <div class="small-muted">
        3D longer-term signal layer for higher-quality entries and exits. Buy signals stay tied to the broader market
        framework, while sell signals now monitor the tracked asset list directly.
    </div>
</div>
""",
        unsafe_allow_html=True,
    )
    buy_panel_col, sell_panel_col = st.columns(2)
    with buy_panel_col:
        st.markdown(
            """
<div class="guide-box">
    <div class="section-title">Buy Signals</div>
    <div class="small-muted">Focused on deeper 3D entry conditions using BTC as the current proxy while the broader market framework is still being refined.</div>
</div>
""",
            unsafe_allow_html=True,
        )
        buy_col1, buy_col2 = st.columns(2)
        with buy_col1:
            dream_buy = buy_signal_data.get("dream_buy", {})
            dream_buy_value = dream_buy.get("label", "Source Pending") if buy_signal_data.get("available") else "Source Pending"
            st.metric("Dream Buy", dream_buy_value)
            st.write(f"Last triggered: **{format_signal_date(dream_buy.get('last_triggered'))}**")
            if dream_buy.get("history"):
                st.caption("Recent triggers: " + ", ".join(format_signal_date(item) for item in dream_buy["history"]))
            elif not buy_signal_data.get("available"):
                st.caption("Waiting on the BTC proxy history source for the live buy framework.")
        with buy_col2:
            oial_signal = buy_signal_data.get("oial", {})
            oial_value = oial_signal.get("label", "Source Pending") if buy_signal_data.get("available") else "Source Pending"
            st.metric("Once In A Lifetime Buy", oial_value)
            st.write(f"Last triggered: **{format_signal_date(oial_signal.get('last_triggered'))}**")
            if oial_signal.get("history"):
                st.caption("Recent triggers: " + ", ".join(format_signal_date(item) for item in oial_signal["history"]))
            elif not buy_signal_data.get("available"):
                st.caption("Reserved for the deepest long-term entry conditions once the BTC proxy builds enough history.")
            elif oial_signal.get("label") == "History Building":
                st.caption("The 600 SMA trigger needs a deeper BTC history set before it can light up reliably.")
    with sell_panel_col:
        st.markdown(
            """
<div class="guide-box">
    <div class="section-title">Sell Signals</div>
    <div class="small-muted">Focused on stronger 3D warning and exit conditions across the tracked asset list.</div>
</div>
""",
            unsafe_allow_html=True,
        )
        sell_col1, sell_col2, sell_col3 = st.columns(3)
        with sell_col1:
            st.metric("Sell Warning (S)", sell_warning_summary["label"])
            if sell_warning_summary["active_assets"]:
                st.caption("Active: " + ", ".join(sell_warning_summary["active_assets"][:5]))
            elif sell_warning_summary["recent_assets"]:
                st.caption("Recent: " + ", ".join(sell_warning_summary["recent_assets"]))
        with sell_col2:
            st.metric("Hard Sell (H-S)", hard_sell_summary["label"])
            if hard_sell_summary["active_assets"]:
                st.caption("Active: " + ", ".join(hard_sell_summary["active_assets"][:5]))
            elif hard_sell_summary["recent_assets"]:
                st.caption("Recent: " + ", ".join(hard_sell_summary["recent_assets"]))
        with sell_col3:
            st.metric("Dream Sell (D-S)", dream_sell_summary["label"])
            if dream_sell_summary["active_assets"]:
                st.caption("Active: " + ", ".join(dream_sell_summary["active_assets"][:5]))
            elif dream_sell_summary["recent_assets"]:
                st.caption("Recent: " + ", ".join(dream_sell_summary["recent_assets"]))
    sell_unavailable_assets = [asset["label"] for asset in sell_signal_assets if not asset.get("available")]
    if sell_unavailable_assets:
        unavailable_preview = ", ".join(sell_unavailable_assets[:8])
        extra_count = len(sell_unavailable_assets) - min(len(sell_unavailable_assets), 8)
        if extra_count > 0:
            unavailable_preview += f" and {extra_count} more"
        st.caption("Unavailable sell feeds: " + unavailable_preview)
    with st.expander("Tracked Sell Asset Detail"):
        for asset in sell_signal_assets:
            st.markdown(f"**{asset['label']}**")
            if asset.get("available"):
                st.write(
                    " | ".join(
                        [
                            f"S: {asset['sell_warning']['label']} (last {format_signal_date(asset['sell_warning']['last_triggered'])})",
                            f"H-S: {asset['hard_sell']['label']} (last {format_signal_date(asset['hard_sell']['last_triggered'])})",
                            f"D-S: {asset['dream_sell']['label']} (last {format_signal_date(asset['dream_sell']['last_triggered'])})",
                        ]
                    )
                )
                if asset.get("source"):
                    source_line = f"Source: {asset['source']}"
                    if asset.get("fallback_used") and asset.get("error"):
                        source_line += f" | {asset['error']}"
                    st.caption(source_line)
            else:
                st.write("Sell signal feed unavailable.")
                if asset.get("error"):
                    st.caption(asset["error"])
            st.divider()

if st.session_state.get("saved_dashboard_snapshot"):
    if saved_dashboard_changes:
        change_lines = "".join(
            [
                f'<div class="driver-line"><b>{change["section"]} / {change["label"]}</b>: saved as <b>{change["saved"]}</b>, now <b>{change["current"]}</b></div>'
                for change in saved_dashboard_changes[:10]
            ]
        )
        extra_change_count = max(0, len(saved_dashboard_changes) - 10)
        extra_note = f'<div class="small-muted" style="margin-top:8px;">{extra_change_count} more change(s) not shown.</div>' if extra_change_count else ""
        st.markdown(
            f"""
<div class="driver-box">
    <div class="section-title">What Changed Since Last Save</div>
    <div class="small-muted">Comparing the current screen to the last dashboard snapshot you saved.</div>
    {change_lines}
    {extra_note}
</div>
""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
<div class="driver-box">
    <div class="section-title">What Changed Since Last Save</div>
    <div class="small-muted">No changes yet. The current screen matches your last saved dashboard snapshot.</div>
</div>
""",
            unsafe_allow_html=True,
        )
else:
    st.caption("Save Dashboard once to start tracking what changed since your last saved snapshot.")

ai_header_col, ai_button_col = st.columns([4, 1])
with ai_header_col:
    st.markdown("""
<div class="driver-box">
    <div class="section-title">AI Analyst Summary</div>
    <div class="small-muted">Your scoring model stays in charge. AI explains the current setup like an analyst using the live dashboard inputs.</div>
</div>
""", unsafe_allow_html=True)
with ai_button_col:
    if has_openai_config():
        if st.button("Generate AI Summary", use_container_width=True):
            with st.spinner("Generating analyst-style summary..."):
                try:
                    ai_result = generate_ai_summary(ai_summary_payload)
                except RuntimeError as exc:
                    st.session_state["ai_summary_error"] = str(exc)
                else:
                    st.session_state["ai_summary_result"] = ai_result
                    st.session_state["ai_summary_fingerprint"] = ai_summary_fingerprint
                    st.session_state["ai_summary_error"] = None
                    log_user_event(
                        "generate_ai_summary",
                        {
                            "bias": bias,
                            "final_score": round(final_score, 1),
                            "conviction": conviction_label,
                        },
                    )
    else:
        st.button("Generate AI Summary", use_container_width=True, disabled=True)

if not has_openai_config():
    st.info(f"Add `OPENAI_API_KEY` to Streamlit secrets to enable AI explanations. Optional: set `OPENAI_MODEL` to override the default `{DEFAULT_OPENAI_MODEL}`.")
elif st.session_state.get("ai_summary_error"):
    st.error(st.session_state["ai_summary_error"])

if st.session_state.get("ai_summary_result") and st.session_state.get("ai_summary_fingerprint") == ai_summary_fingerprint:
    ai_result = st.session_state["ai_summary_result"]
    ai_col1, ai_col2 = st.columns([1.45, 1])
    with ai_col1:
        st.markdown(
            f"""
<div class="guide-box">
    <div class="section-title">Current Bias Explained</div>
    <div class="small-muted">{display_text(ai_result.get('current_bias_explained'), 'No AI explanation generated yet.')}</div>
</div>
""",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
<div class="guide-box">
    <div class="section-title">Plain-English Takeaway</div>
    <div class="small-muted">{display_text(ai_result.get('plain_english_takeaway'), 'No takeaway generated yet.')}</div>
</div>
""",
            unsafe_allow_html=True,
        )
    with ai_col2:
        st.markdown("**Top Reasons**")
        for item in ai_result.get("top_reasons", []):
            st.write(f"- {item}")
        st.markdown("**What Could Flip This**")
        for item in ai_result.get("what_could_flip_this", []):
            st.write(f"- {item}")
        st.markdown("**Risk Watch**")
        for item in ai_result.get("risk_watch", []):
            st.write(f"- {item}")
elif has_openai_config():
    st.caption("Generate the AI summary when you want a fresh analyst-style read on the current dashboard state.")

with st.expander("Score Breakdown"):
    st.write(f"Technical Analysis: Raw **{ta_score:.1f}** | Weight **30%** | Contribution **{ta_contribution:.1f}**")
    st.write(f"Analyst Consensus: Raw **{analyst_score:.1f}** | Weight **25%** | Contribution **{analyst_contribution:.1f}**")
    st.write(f"News / Macro News: Raw **{news_score:.1f}** | Weight **10%** | Contribution **{news_contribution:.1f}**")
    st.write(f"Macro / Liquidity: Raw **{macro_score:.1f}** | Weight **25%** | Contribution **{macro_contribution:.1f}**")
    st.write(f"Sentiment / Positioning: Raw **{sentiment_score:.1f}** | Weight **10%** | Contribution **{sentiment_contribution:.1f}**")
    st.caption(f"Sentiment mix: Fear & Greed {SENTIMENT_FNG_WEIGHT:.0%}, BTC Market Fragility {SENTIMENT_OPEN_INTEREST_WEIGHT:.0%} when available.")
    st.divider()
    st.write(f"Final Score: **{final_score:.1f}**")
    st.write(f"Bias: **{bias}**")
    st.write(f"Signal Strength: **{signal_strength:.1f}%**")

drivers = [
    f"TOTAL 3D state: {total_3d_state} ({score_3d})",
    f"TOTAL 1D state: {total_1d_supertrend} ({score_1d})",
    f"Analyst consensus score: {analyst_score:.1f}",
    f"News / Macro score: {news_score}",
    f"Macro / liquidity score: {macro_score}",
    f"Sentiment / positioning score: {sentiment_score:.1f}",
    f"Fear & Greed: {fng_label} ({fng_value if fng_value is not None else 'N/A'}) | score {fng_score}",
]
if stablecoin_signal["available"] and stablecoin_signal.get("change_pct") is not None:
    drivers.append(f"Stablecoin liquidity: {stablecoin_signal['state']} ({stablecoin_signal['change_pct']:+.2f}% 7d) | score {stablecoin_signal['score']}")
if open_interest_signal["available"]:
    if open_interest_signal.get("change_pct") is not None:
        drivers.append(f"BTC market fragility: {open_interest_signal['state']} ({open_interest_signal['change_pct']:+.2f}% 7d) | score {open_interest_signal['score']}")
    else:
        drivers.append(f"BTC market fragility: {open_interest_signal['state']} | score {open_interest_signal['score']}")
if global_liquidity_signal["available"]:
    drivers.append(f"Global liquidity proxy: {global_liquidity_signal['state']} | score {global_liquidity_signal['score']}")
    if global_liquidity_signal["missing_components"]:
        drivers.append("Global liquidity proxy uses available components only: " + ", ".join(global_liquidity_signal["missing_components"]))
if macro_unavailable:
    drivers.append(f"Unavailable macro feeds: {', '.join(macro_unavailable)}")
if etf_flows_signal["available"]:
    drivers.append(f"Crypto ETF flows: {etf_flows_signal['state']} (${etf_flows_signal['value']:.1f}M) | score {etf_flows_signal['score']}")

driver_html = "".join([f'<div class="driver-line">{d}</div>' for d in drivers])
st.markdown(f"""
<div class="driver-box">
    <div class="section-title">Top Drivers</div>
    <div class="small-muted">Highest-impact scored factors currently shaping the dashboard output.</div>
    {driver_html}
</div>
""", unsafe_allow_html=True)

chart_col, guide_col = st.columns([2, 1])
with chart_col:
    st.markdown("""
<div class="driver-box">
    <div class="section-title">TOTAL TradingView Chart</div>
    <div class="small-muted">Supporting chart context for TOTAL market-cap structure on the 3D timeframe.</div>
</div>
""", unsafe_allow_html=True)
    st.markdown(
        """
<div class="guide-box" style="margin-top:6px;">
    <div class="section-title">TOTAL Market Cap Chart</div>
    <div class="small-muted">
        Open the live TradingView chart in a separate tab for the most reliable beta experience.
    </div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.link_button("Open TOTAL on TradingView", "https://www.tradingview.com/symbols/CRYPTOCAP-TOTAL/", use_container_width=True)
    st.markdown("""
<div class="driver-box">
    <div class="section-title">Astro + Recommended Content</div>
    <div class="small-muted">Optional educational context only. This section is excluded from scoring and is designed to help users learn, explore, and connect broader themes to market behavior.</div>
</div>
""", unsafe_allow_html=True)
    astro_col1, astro_col2 = st.columns([1, 1])
    with astro_col1:
        st.markdown(
            f"""
<div class="guide-box">
    <div class="driver-line"><b>Lunar Event:</b> {display_text(astro_lunar_event)}</div>
    <div class="driver-line"><b>Transits Worth Noting:</b> {display_text(astro_transits)}</div>
    <div class="driver-line"><b>Market Theme:</b> {display_text(astro_market_theme)}</div>
</div>
""",
            unsafe_allow_html=True,
        )
    with astro_col2:
        st.markdown(
            """
<div class="guide-box">
    <div class="section-title">Recommended Content</div>
</div>
""",
            unsafe_allow_html=True,
        )
        st.markdown(f"**Recommended Video:** {display_simple_link(share_video, 'Not added yet')}")
        st.markdown(f"**Recommended Article:** {display_simple_link(share_article, 'Not added yet')}")
        st.markdown(
            f"""
<div class="guide-box">
    <div class="section-title">Why It Matters</div>
    <div class="small-muted">{display_text(share_why, "No featured explanation added yet.")}</div>
</div>
""",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
<div class="guide-box">
    <div class="section-title">Market Connection</div>
    <div class="small-muted">{display_text(share_takeaway, "No takeaway added yet.")}</div>
</div>
""",
            unsafe_allow_html=True,
        )
with guide_col:
    st.markdown("""
    <div class="guide-box">
        <div class="section-title">Signal State Guide: TOTAL 3D</div>
        <div class="small-muted">
            - <b>Soft Bullish</b> = 3 to 4 candle closes above the 21 SMA, with the smaller Supertrend signal flipped green<br><br>
            - <b>Bullish Cross</b> = the 21 SMA crosses above the 55 SMA, a shift that often opens the door for stronger upside continuation<br><br>
            - <b>Neutral</b> = price has reclaimed the 21 SMA with 3 to 4 closes above it, but still fails to recover the 55 SMA. Price action remains above the 21 SMA while the smaller Supertrend stays red, showing partial improvement without full confirmation<br><br>
            - <b>Soft Bearish</b> = 3 to 4 candle closes below the 21 SMA, signaling early weakness<br><br>
            - <b>Bearish Cross</b> = the 21 SMA crosses below the 55 SMA, a shift that often leads to deeper bearish momentum<br><br>
            - <b>Confirmed Bearish</b> = after a bearish cross, 3 to 4 candle closes occur below both the 21 SMA and 55 SMA, confirming bearish structure. At this stage, possible bottoming conditions should also be monitored using references such as the 500 SMA, RSI positioning, and broader oversold conditions
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="guide-box">
        <div class="section-title">Signal State Guide: TOTAL 1D</div>
        <div class="small-muted">
            - <b>Soft Bearish</b> = loss of the smaller / mini bullish trend, 4 candle closes below the 30 SMA, price remains below the 30 SMA, and a mini bearish trend forms<br><br>
            - <b>Bearish Cross</b> = 30 SMA crosses below the 60 SMA and 4 candle closes occur below both the 30 SMA and 60 SMA, while the daily Supertrend bullish signal has not yet broken<br><br>
            - <b>Soft Bullish</b> = price breaks the smaller bearish trend, price is above the 30 SMA, and the 30 SMA crosses above the 60 SMA<br><br>
            - <b>Bullish</b> = daily Supertrend is bullish, 4 candle closes are above the 200 SMA, and RSI is above 50<br><br>
            - <b>Bearish</b> = daily Supertrend breaks bearish, 4 candle closes occur below the daily Supertrend, and RSI remains below 50 or cannot reclaim 50
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="guide-box">
        <div class="section-title">Macro Layer</div>
        <div class="small-muted">
            - <b>US short rates / US 10Y falling</b> generally supports risk assets<br><br>
            - <b>Japan 10Y rising</b> can be a liquidity headwind<br><br>
            - <b>DXY falling</b> is generally supportive for crypto<br><br>
            - <b>Oil rising</b> can add inflation pressure and act as a risk-asset headwind<br><br>
            - <b>Stablecoin supply expanding</b> can signal improving crypto liquidity and potential buying power<br><br>
            - <b>Global liquidity proxy improving</b> reflects easier balance sheet, credit, and dollar conditions
        </div>
    </div>
    """, unsafe_allow_html=True)
