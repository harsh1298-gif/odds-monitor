"""
============================================================
  ODDS MONITOR DASHBOARD v3  —  dashboard.py
  Enhanced UI + bet tracking + full analytics

  FIXES APPLIED:
  1.  Duplicate checkbox key crash        → unique keys via enumerate index
  2.  Tab 6 widget key namespacing        → t6_ prefix on all Tab 6 widgets
  3.  Slider key conflict sidebar vs Tab7 → Tab 7 slider uses key="wi_stake_slider"
  4.  ev_score <= 0 crash in px.scatter   → size col clamped to min 0.01
  5.  Timezone-aware tz_localize TypeError→ strip tz before localize with utc param
  6.  Column variable reuse across tabs   → renamed c1/c2 per tab (t1_, t2_, etc.)
  7.  Unsafe row.get() on pandas Series  → row[col] with explicit default via .get workaround
  8.  Division by zero in metrics & ROI  → all divisions guarded with `or 1` / `if` checks
  9.  st.secrets crash without secrets.toml → try/except around st.secrets access
  10. Expander key collisions + iterrows  → use enumerate; keys include loop index
  11. Bare except + mutable default arg   → specific Exception catches; no mutable defaults

  FEATURE ADDED:
  12. Opportunity expiration              → opportunities vanish after commence_time passes
  13. Safe timestamp formatting           → handle NaT in expander labels
============================================================
"""

import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np

st.set_page_config(
    page_title="Odds Monitor Pro",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;500;600;700;800&display=swap');

:root {
  --bg:        #080b10;
  --bg2:       #0d1117;
  --bg3:       #111827;
  --border:    #1a2233;
  --border2:   #243044;
  --green:     #00ff88;
  --green2:    #00c46a;
  --red:       #ff4455;
  --yellow:    #ffd000;
  --blue:      #4488ff;
  --text:      #e8edf5;
  --muted:     #5a6a82;
  --card-glow: 0 0 24px rgba(0,255,136,0.06);
}

html, body, [class*="css"] {
  font-family: 'Syne', sans-serif;
  background: var(--bg) !important;
  color: var(--text);
}

section[data-testid="stSidebar"] {
  background: var(--bg2) !important;
  border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { font-family: 'Syne', sans-serif; }

.stTabs [data-baseweb="tab-list"] {
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  gap: 0;
}
.stTabs [data-baseweb="tab"] {
  background: transparent;
  color: var(--muted);
  font-family: 'Space Mono', monospace;
  font-size: 12px;
  padding: 10px 20px;
  border-bottom: 2px solid transparent;
}
.stTabs [aria-selected="true"] {
  background: transparent !important;
  color: var(--green) !important;
  border-bottom: 2px solid var(--green) !important;
}

div[data-testid="stMetric"] {
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: var(--card-glow);
}
div[data-testid="stMetricLabel"] { color: var(--muted) !important; font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em; }
div[data-testid="stMetricValue"] { color: var(--text) !important; font-family: 'Space Mono', monospace; }
div[data-testid="stMetricDelta"] svg { display: none; }

.stButton > button {
  background: transparent;
  border: 1px solid var(--border2);
  color: var(--text);
  font-family: 'Space Mono', monospace;
  font-size: 12px;
  border-radius: 8px;
  transition: all 0.2s;
}
.stButton > button:hover {
  border-color: var(--green);
  color: var(--green);
  box-shadow: 0 0 12px rgba(0,255,136,0.15);
}

.streamlit-expanderHeader {
  background: var(--bg3) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px !important;
  font-family: 'Syne', sans-serif !important;
}

.opp-card {
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 22px;
  margin-bottom: 10px;
  transition: border-color 0.2s;
}
.opp-card:hover { border-color: var(--border2); }
.opp-card-placed  { border-color: var(--green) !important; box-shadow: var(--card-glow); }
.opp-card-won     { border-color: var(--green2) !important; }
.opp-card-lost    { border-color: var(--red) !important; }
.opp-card-expired { border-color: var(--red) !important; opacity: 0.7; }

.badge {
  display: inline-block;
  border-radius: 6px;
  padding: 2px 10px;
  font-size: 11px;
  font-family: 'Space Mono', monospace;
  font-weight: 700;
  letter-spacing: 0.05em;
}
.badge-green  { background: rgba(0,255,136,0.1); color: var(--green); border: 1px solid rgba(0,255,136,0.2); }
.badge-red    { background: rgba(255,68,85,0.1);  color: var(--red);   border: 1px solid rgba(255,68,85,0.2); }
.badge-yellow { background: rgba(255,208,0,0.1);  color: var(--yellow);border: 1px solid rgba(255,208,0,0.2); }
.badge-blue   { background: rgba(68,136,255,0.1); color: var(--blue);  border: 1px solid rgba(68,136,255,0.2); }
.badge-muted  { background: rgba(90,106,130,0.15);color: var(--muted); border: 1px solid rgba(90,106,130,0.2); }

.stat-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }

.section-title {
  font-family: 'Space Mono', monospace;
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.bk-chip {
  display: inline-block;
  background: rgba(68,136,255,0.1);
  color: var(--blue);
  border: 1px solid rgba(68,136,255,0.2);
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 11px;
  font-family: 'Space Mono', monospace;
  margin: 2px;
}

.profit-positive { color: var(--green); font-family: 'Space Mono', monospace; font-weight: 700; }
.profit-negative { color: var(--red);   font-family: 'Space Mono', monospace; font-weight: 700; }
.divider { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
.stDataFrame { border: 1px solid var(--border) !important; border-radius: 10px !important; overflow: hidden; }
</style>
""", unsafe_allow_html=True)

# ── CHART THEME ─────────────────────────────────────────────
CHART = dict(
    plot_bgcolor="#0d1117",
    paper_bgcolor="#0d1117",
    font_color="#5a6a82",
    margin=dict(l=0, r=0, t=24, b=0),
)
GREEN  = "#00ff88"
GREEN2 = "#00c46a"
RED    = "#ff4455"
YELLOW = "#ffd000"
BLUE   = "#4488ff"
MUTED  = "#1a2233"

# ── CONFIG ───────────────────────────────────────────────────
def _secret(key: str, fallback: str = "") -> str:
    try:
        return st.secrets.get(key, fallback)
    except Exception:
        return fallback

SUPABASE_URL = os.getenv("SUPABASE_URL", _secret("SUPABASE_URL", ""))
SUPABASE_KEY = os.getenv("SUPABASE_KEY", _secret("SUPABASE_KEY", ""))

LEAGUE_NAMES = {
    "soccer_epl":                "Premier League 🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "soccer_uefa_champs_league": "Champions League 🏆",
    "soccer_spain_la_liga":      "La Liga 🇪🇸",
    "soccer_germany_bundesliga": "Bundesliga 🇩🇪",
    "soccer_italy_serie_a":      "Serie A 🇮🇹",
    "soccer_france_ligue_one":   "Ligue 1 🇫🇷",
}

BOOKMAKERS = {
    "soccer_epl":                ["Bet365", "William Hill", "1xBet", "Unibet", "Betway"],
    "soccer_uefa_champs_league": ["Bet365", "Bwin", "1xBet", "Pinnacle", "Betfair"],
    "soccer_spain_la_liga":      ["Bet365", "Bwin", "1xBet", "Betsson", "Unibet"],
    "soccer_germany_bundesliga": ["Bet365", "Bwin", "1xBet", "Betway", "Tipico"],
    "soccer_italy_serie_a":      ["Bet365", "Sisal", "1xBet", "Snai", "Unibet"],
    "soccer_france_ligue_one":   ["Bet365", "PMU", "1xBet", "Unibet", "Bwin"],
}

# ── HELPER: Safe timestamp formatting ──────────────────────
def safe_strftime(dt, fmt: str = "%b %d %H:%M") -> str:
    """Return formatted datetime string, or 'Unknown' if NaT/None."""
    if pd.isna(dt) or dt is None:
        return "Unknown"
    try:
        return dt.strftime(fmt)
    except AttributeError:
        return "Unknown"

# ── SUPABASE ─────────────────────────────────────────────────
def sb_get(table: str, params: dict | None = None) -> list:
    if params is None:
        params = {}
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}", headers=h, params=params, timeout=15
        )
        return r.json() if r.status_code == 200 else []
    except Exception as exc:
        st.warning(f"DB read error: {exc}")
        return []

def sb_patch(table: str, match_id: str, data: dict) -> bool:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?match_id=eq.{match_id}",
            headers=h, json=data, timeout=15,
        )
        return r.status_code in [200, 204]
    except Exception as exc:
        st.warning(f"DB write error: {exc}")
        return False

def _to_naive_utc(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    return parsed.dt.tz_convert(None)

@st.cache_data(ttl=180)
def load_data() -> pd.DataFrame:
    rows = sb_get("opportunities", {"order": "spotted_at.desc", "limit": 1000})
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["spotted_at"]    = _to_naive_utc(df["spotted_at"])
    df["commence_time"] = _to_naive_utc(df["commence_time"])

    df["date"]          = df["spotted_at"].dt.date
    df["hour"]          = df["spotted_at"].dt.hour
    df["dow"]           = df["spotted_at"].dt.day_name()
    df["won"]           = df["result"].isin(["home_win", "away_win"])
    df["lost"]          = df["result"] == "draw"
    df["pending"]       = df["result"].isna()
    df["league_name"]   = df["league"].map(LEAGUE_NAMES).fillna(df["league"])
    df["avg_odds"]      = ((df["home_odds"] + df["away_odds"]) / 2).round(2)
    df["ev_score"]      = (df["avg_odds"] - 2.0).round(3)

    if "bet_placed" in df.columns:
        df["bet_placed"] = df["bet_placed"].fillna(False)
    else:
        df["bet_placed"] = False

    now_utc = pd.Timestamp(datetime.utcnow())
    df["expired"] = df["commence_time"] < now_utc
    df["active"]  = ~df["expired"] & df["pending"]

    return df

def demo_data() -> pd.DataFrame:
    np.random.seed(99)
    n   = 140
    now = datetime.utcnow()
    leagues = list(LEAGUE_NAMES.keys())
    results = np.random.choice(
        ["home_win", "away_win", "draw", None], n, p=[0.40, 0.37, 0.11, 0.12]
    )
    ht = ["Bayern","Real Madrid","Man City","Barcelona","PSG","Arsenal",
          "Juventus","Inter","Liverpool","Dortmund","Napoli","Porto"]
    at = ["Atletico","Napoli","Porto","Ajax","Lazio","Milan",
          "Sevilla","Lyon","Leicester","Freiburg","Udinese","Braga"]
    bks = ["Bet365","1xBet","William Hill","Bwin","Pinnacle","Unibet"]
    data = []
    for i in range(n):
        ho  = round(2.05 + np.random.exponential(0.45), 2)
        ao  = round(2.05 + np.random.exponential(0.40), 2)
        res = results[i]
        lg  = np.random.choice(leagues)
        ap  = None
        if res == "home_win":   ap = round(5000 * ho - 10000)
        elif res == "away_win": ap = round(5000 * ao - 10000)
        elif res == "draw":     ap = -10000
        spot = now - timedelta(
            days=int(np.random.uniform(0, 30)),
            hours=int(np.random.uniform(0, 24)),
        )
        commence = spot + timedelta(days=int(np.random.uniform(1, 5)))
        placed = np.random.random() < 0.3
        data.append({
            "match_id":            f"match_{i}",
            "home_team":           np.random.choice(ht),
            "away_team":           np.random.choice(at),
            "league":              lg,
            "league_name":         LEAGUE_NAMES[lg],
            "home_odds":           ho,
            "away_odds":           ao,
            "draw_odds":           round(3.1 + np.random.normal(0, 0.3), 2),
            "home_bookmaker":      np.random.choice(bks),
            "away_bookmaker":      np.random.choice(bks),
            "profit_if_home_wins": round(5000 * ho - 10000),
            "profit_if_away_wins": round(5000 * ao - 10000),
            "loss_if_draw":        -10000,
            "spotted_at":          spot,
            "commence_time":       commence,
            "result":              res,
            "actual_profit":       ap,
            "date":                spot.date(),
            "hour":                spot.hour,
            "dow":                 spot.strftime("%A"),
            "won":                 res in ["home_win", "away_win"],
            "lost":                res == "draw",
            "pending":             res is None,
            "avg_odds":            round((ho + ao) / 2, 2),
            "ev_score":            round((ho + ao) / 2 - 2.0, 2),
            "bet_placed":          placed,
            "notes":               "",
        })

    df = pd.DataFrame(data)
    now_utc = pd.Timestamp(now)
    df["expired"] = df["commence_time"] < now_utc
    df["active"]  = ~df["expired"] & df["pending"]
    return df

def _row_get(row: pd.Series, key: str, default=None):
    try:
        val = row[key]
        return default if pd.isna(val) else val
    except (KeyError, TypeError, ValueError):
        return default

# ══════════════════════════════════════════════════════════
#   SIDEBAR
# ══════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown('<div class="section-title">⚙ Filters</div>', unsafe_allow_html=True)
    days_back = st.slider("Days", 1, 90, 30)
    all_leagues = list(LEAGUE_NAMES.values())
    sel_leagues = st.multiselect("Leagues", all_leagues, default=all_leagues)
    min_odds_filter = st.slider("Min avg odds", 2.0, 4.0, 2.0, 0.05)

    status_filter = st.selectbox(
        "Status",
        ["Active", "All", "Pending", "Won", "Lost", "Expired", "Bet Placed"],
    )
    show_expired = st.checkbox(
        "Include finished matches",
        value=False,
        key="sidebar_show_expired",
    )

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">💰 Simulation</div>', unsafe_allow_html=True)
    stake = st.number_input("Stake per side ($)", 100, 100_000, 5000, 500)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

# ══════════════════════════════════════════════════════════
#   LOAD + FILTER
# ══════════════════════════════════════════════════════════
df = load_data()
using_demo = df.empty
if using_demo:
    st.toast("Showing demo data — connect Supabase to see live data", icon="ℹ️")
    df = demo_data()

cutoff = datetime.utcnow() - timedelta(days=days_back)
fdf = df[df["spotted_at"] >= cutoff].copy()
fdf = fdf[fdf["league_name"].isin(sel_leagues)]
fdf = fdf[fdf["avg_odds"] >= min_odds_filter]

if status_filter == "Active":
    fdf = fdf[fdf["active"]]
elif status_filter == "Pending":
    fdf = fdf[fdf["pending"]]
elif status_filter == "Won":
    fdf = fdf[fdf["won"]]
elif status_filter == "Lost":
    fdf = fdf[fdf["lost"]]
elif status_filter == "Expired":
    fdf = fdf[fdf["expired"] & ~fdf["won"] & ~fdf["lost"]]
elif status_filter == "Bet Placed":
    fdf = fdf[fdf["bet_placed"] == True]

if not show_expired and status_filter not in ["All", "Expired", "Won", "Lost"]:
    fdf = fdf[~fdf["expired"] | fdf["bet_placed"] | fdf["won"] | fdf["lost"]]

resolved = fdf[~fdf["pending"]].copy()
placed   = fdf[fdf["bet_placed"] == True].copy()

# ══════════════════════════════════════════════════════════
#   HEADER
# ══════════════════════════════════════════════════════════
st.markdown("""
<div style="padding: 24px 0 8px;">
  <div style="font-family:'Space Mono',monospace;font-size:11px;color:#5a6a82;letter-spacing:0.15em;text-transform:uppercase;margin-bottom:6px">
    ODDS MONITOR PRO · LIVE
  </div>
  <div style="font-family:'Syne',sans-serif;font-size:28px;font-weight:800;color:#e8edf5;line-height:1">
    Betting Opportunity Dashboard
  </div>
</div>
""", unsafe_allow_html=True)

# ── TOP METRICS ──────────────────────────────────────────────
wins    = int(fdf["won"].sum())
draws   = int(fdf["lost"].sum())
pending = int(fdf["pending"].sum())
total   = len(fdf)

win_rate     = (wins / (wins + draws) * 100) if (wins + draws) > 0 else 0.0
total_pl     = int(resolved["actual_profit"].sum() * (stake / 5000)) if not resolved.empty else 0
n_placed     = int((fdf["bet_placed"] == True).sum())
avg_ev       = round(fdf["ev_score"].mean(), 2) if not fdf.empty else 0

active_count  = int(fdf["active"].sum())
expired_count = max(int(fdf["expired"].sum()) - wins - draws, 0)

hdr_c1, hdr_c2, hdr_c3, hdr_c4, hdr_c5, hdr_c6, hdr_c7, hdr_c8 = st.columns(8)
hdr_c1.metric("Opportunities", f"{total:,}")
hdr_c2.metric("🟢 Active", f"{active_count:,}", "pre-match")
hdr_c3.metric(
    "Bets Placed", f"{n_placed:,}",
    f"{n_placed / total * 100:.0f}% of opps" if total else "0%",
)
hdr_c4.metric("Won", f"{wins:,}", f"{win_rate:.1f}% win rate")
hdr_c5.metric("Lost to Draw", f"{draws:,}")
hdr_c6.metric("⏰ Expired", f"{expired_count:,}", "needs result")
hdr_c7.metric("Simulated P&L", f"${total_pl:,}")
hdr_c8.metric("Avg EV Score", f"+{avg_ev}" if avg_ev >= 0 else str(avg_ev))

st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#   TABS
# ══════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📈  Overview",
    "🎯  Opportunities",
    "📋  My Bets",
    "📊  Analytics",
    "🏦  Bookmakers",
    "✏️  Update Results",
    "💰  P&L Tracker",
])

# ══════════════════════════════════════════════════════════
#   TAB 1 — OVERVIEW
# ══════════════════════════════════════════════════════════
with tab1:
    t1_col_a, t1_col_b = st.columns([2, 1])

    with t1_col_a:
        st.markdown('<div class="section-title">Opportunities per day</div>', unsafe_allow_html=True)
        daily = fdf.groupby("date").size().reset_index(name="count")
        fig = px.bar(daily, x="date", y="count", color_discrete_sequence=[GREEN])
        fig.update_traces(marker_line_width=0)
        fig.update_layout(
            **CHART, height=220,
            xaxis=dict(showgrid=False, color="#374151"),
            yaxis=dict(gridcolor="#1a2233", color="#374151"),
        )
        st.plotly_chart(fig, use_container_width=True)

    with t1_col_b:
        st.markdown('<div class="section-title">By league</div>', unsafe_allow_html=True)
        by_l = (
            fdf.groupby("league_name").size()
            .reset_index(name="count")
            .sort_values("count")
        )
        fig2 = px.bar(by_l, x="count", y="league_name", orientation="h",
                      color_discrete_sequence=[GREEN2])
        fig2.update_traces(marker_line_width=0)
        fig2.update_layout(
            **CHART, height=220,
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=False, title=""),
        )
        st.plotly_chart(fig2, use_container_width=True)

    t1_col_c, t1_col_d = st.columns([2, 1])

    with t1_col_c:
        st.markdown('<div class="section-title">Cumulative P&L simulation</div>', unsafe_allow_html=True)
        if not resolved.empty:
            r2 = resolved.sort_values("spotted_at").copy()
            r2["sim"]   = r2["actual_profit"] * (stake / 5000)
            r2["cumpl"] = r2["sim"].cumsum()
            color_line  = GREEN if r2["cumpl"].iloc[-1] >= 0 else RED
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=r2["spotted_at"], y=r2["cumpl"],
                fill="tozeroy",
                fillcolor=(
                    "rgba(0,255,136,0.07)"
                    if r2["cumpl"].iloc[-1] >= 0
                    else "rgba(255,68,85,0.07)"
                ),
                line=dict(color=color_line, width=2.5), name="P&L",
            ))
            fig3.add_hline(y=0, line_dash="dot", line_color="#243044")
            fig3.update_layout(
                **CHART, height=240,
                yaxis=dict(gridcolor="#1a2233", tickprefix="$"),
                xaxis=dict(showgrid=False), showlegend=False,
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.markdown("""<div style="background:#0d1117;border:1px dashed #1a2233;border-radius:10px;
            padding:40px;text-align:center;color:#5a6a82;font-family:'Space Mono',monospace;font-size:12px">
            Add match results to see P&L curve</div>""", unsafe_allow_html=True)

    with t1_col_d:
        st.markdown('<div class="section-title">Result breakdown</div>', unsafe_allow_html=True)
        if wins + draws > 0:
            fig4 = go.Figure(go.Pie(
                labels=["Win", "Draw loss"], values=[wins, draws], hole=0.68,
                marker_colors=[GREEN, RED], textinfo="percent+label",
                textfont=dict(family="Space Mono", size=11),
            ))
            fig4.update_layout(
                **CHART, height=240, showlegend=False,
                margin=dict(l=0, r=0, t=10, b=0),
            )
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.markdown("""<div style="background:#0d1117;border:1px dashed #1a2233;border-radius:10px;
            padding:40px;text-align:center;color:#5a6a82;font-family:'Space Mono',monospace;font-size:12px">
            No results yet</div>""", unsafe_allow_html=True)

    st.markdown(
        '<div class="section-title">Odds landscape — dot size = EV score</div>',
        unsafe_allow_html=True,
    )
    color_map = {"home_win": GREEN, "away_win": GREEN2, "draw": RED, "None": MUTED}

    scatter_df = fdf.copy()
    scatter_df["ev_size"] = scatter_df["ev_score"].clip(lower=0.01)

    fig5 = px.scatter(
        scatter_df, x="home_odds", y="away_odds",
        color=scatter_df["result"].fillna("None"),
        color_discrete_map=color_map,
        size="ev_size", size_max=18,
        hover_data=["home_team", "away_team", "league_name", "avg_odds"],
    )
    fig5.add_vline(x=2.0, line_dash="dot", line_color="#243044",
                   annotation_text="2x", annotation_font_color="#5a6a82")
    fig5.add_hline(y=2.0, line_dash="dot", line_color="#243044")
    fig5.update_layout(
        **CHART, height=360,
        xaxis=dict(gridcolor="#1a2233", title="Home odds (x)"),
        yaxis=dict(gridcolor="#1a2233", title="Away odds (x)"),
    )
    st.plotly_chart(fig5, use_container_width=True)

# ══════════════════════════════════════════════════════════
#   TAB 2 — OPPORTUNITIES
# ══════════════════════════════════════════════════════════
with tab2:
    t2_c1, t2_c2, t2_c3 = st.columns(3)
    with t2_c1:
        sort_by = st.selectbox(
            "Sort by",
            ["Most recent", "Highest EV", "Highest home odds", "Highest away odds"],
            key="tab2_sort",
        )
    with t2_c2:
        opp_filter = st.selectbox(
            "Show",
            ["All", "Active only", "Pending only", "Bet placed", "Not bet placed", "Expired"],
            key="tab2_filter",
        )
    with t2_c3:
        league_quick = st.selectbox(
            "League", ["All"] + list(LEAGUE_NAMES.values()), key="tab2_league"
        )

    dff = fdf.copy()
    if opp_filter == "Active only":      dff = dff[dff["active"]]
    elif opp_filter == "Pending only":   dff = dff[dff["pending"]]
    elif opp_filter == "Bet placed":     dff = dff[dff["bet_placed"] == True]
    elif opp_filter == "Not bet placed": dff = dff[dff["bet_placed"] != True]
    elif opp_filter == "Expired":        dff = dff[dff["expired"] & ~dff["won"] & ~dff["lost"]]
    if league_quick != "All":            dff = dff[dff["league_name"] == league_quick]

    if sort_by == "Highest EV":          dff = dff.sort_values("ev_score", ascending=False)
    elif sort_by == "Highest home odds": dff = dff.sort_values("home_odds", ascending=False)
    elif sort_by == "Highest away odds": dff = dff.sort_values("away_odds", ascending=False)
    else:                                dff = dff.sort_values("spotted_at", ascending=False)

    st.markdown(
        f'<div class="section-title">Showing {len(dff)} opportunities</div>',
        unsafe_allow_html=True,
    )

    for opp_idx, (_, row) in enumerate(dff.head(60).iterrows()):
        ph = round(stake * row["home_odds"] - stake * 2)
        pa = round(stake * row["away_odds"] - stake * 2)
        is_placed = _row_get(row, "bet_placed", False) is True or _row_get(row, "bet_placed", False) == True

        if row["won"]:
            rb = '<span class="badge badge-green">✓ Won</span>'
        elif row["lost"]:
            rb = '<span class="badge badge-red">✗ Draw loss</span>'
        elif row["expired"]:
            rb = '<span class="badge badge-red">⏰ Expired</span>'
        else:
            rb = '<span class="badge badge-muted">⏳ Active</span>'

        pb = '<span class="badge badge-yellow">💰 Bet placed</span>' if is_placed else ''
        hb = _row_get(row, "home_bookmaker", "Bet365") or "Bet365"
        ab = _row_get(row, "away_bookmaker", "1xBet") or "1xBet"

        header = f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <div>
            <span style="font-family:'Syne',sans-serif;font-size:15px;font-weight:700;color:#e8edf5">
              {row['home_team']} <span style="color:#5a6a82;font-weight:400">vs</span> {row['away_team']}
            </span>
            <span style="font-size:12px;color:#5a6a82;margin-left:10px">{row['league_name']}</span>
          </div>
          <div style="display:flex;gap:6px;align-items:center">{rb} {pb}</div>
        </div>
        """

        spotted_str = safe_strftime(row["spotted_at"])
        with st.expander(
            f"{row['home_team']} vs {row['away_team']} · "
            f"{row['league_name']} · {row['avg_odds']}x avg · {spotted_str}"
        ):
            st.markdown(header, unsafe_allow_html=True)

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric(f"🏠 {row['home_team']}", f"{row['home_odds']}x", f"via {hb}")
            mc2.metric("Draw (avoid)", f"{row['draw_odds']}x")
            mc3.metric(f"✈️ {row['away_team']}", f"{row['away_odds']}x", f"via {ab}")
            mc4.metric("EV Score", f"+{row['ev_score']:.3f}")

            st.markdown("---")
            pc1, pc2, pc3 = st.columns(3)
            pc1.metric(f"If {row['home_team']} wins", f"+${ph:,}")
            pc2.metric(f"If {row['away_team']} wins", f"+${pa:,}")
            pc3.metric("If draw", f"-${stake * 2:,}")

            st.markdown(f"""
            <div style="background:#080b10;border:1px solid #1a2233;border-radius:8px;padding:12px;margin-top:8px">
              <div style="font-size:11px;color:#5a6a82;margin-bottom:6px;font-family:'Space Mono',monospace">BOOKMAKERS TO USE</div>
              <span class="bk-chip">{hb} → {row['home_team']}</span>
              <span class="bk-chip">{ab} → {row['away_team']}</span>
            </div>
            """, unsafe_allow_html=True)

            bc1, bc2 = st.columns(2)
            with bc1:
                new_placed = st.checkbox(
                    "✅ Mark as bet placed",
                    value=bool(is_placed),
                    key=f"tab2_placed_{row['match_id']}_{opp_idx}",
                )
                if new_placed != is_placed:
                    if sb_patch("opportunities", row["match_id"], {"bet_placed": new_placed}):
                        st.toast("Updated!", icon="✅")
                        st.cache_data.clear()
                        st.rerun()
            with bc2:
                mt = _row_get(row, "commence_time")
                mt_str = safe_strftime(mt, "%b %d %H:%M")
                if row["expired"] and not row["won"] and not row["lost"]:
                    st.caption(
                        f"⏰ Match started: {mt_str}\n"
                        f"Spotted: {spotted_str}\n"
                        "⚠️ Update result in Tab 6"
                    )
                else:
                    st.caption(
                        f"Match: {mt_str}\n"
                        f"Spotted: {spotted_str}"
                    )

# ══════════════════════════════════════════════════════════
#   TAB 3 — MY BETS
# ══════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-title">Bets you have placed</div>', unsafe_allow_html=True)

    if placed.empty:
        st.markdown("""<div style="background:#0d1117;border:1px dashed #1a2233;border-radius:12px;
        padding:60px;text-align:center;color:#5a6a82;font-family:'Space Mono',monospace;font-size:13px">
        No bets marked as placed yet.<br>Go to Opportunities tab and check ✅ Mark as bet placed
        </div>""", unsafe_allow_html=True)
    else:
        placed_resolved = placed[~placed["pending"]]
        placed_pending  = placed[placed["pending"]]

        t3_pm1, t3_pm2, t3_pm3, t3_pm4 = st.columns(4)
        t3_pm1.metric("Bets placed", len(placed))
        t3_pm2.metric("Resolved", len(placed_resolved))
        t3_pm3.metric("Pending result", len(placed_pending))
        placed_pl = (
            int(placed_resolved["actual_profit"].sum() * (stake / 5000))
            if not placed_resolved.empty
            else 0
        )
        t3_pm4.metric("Actual P&L", f"${placed_pl:,}")

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

        for bet_idx, (_, row) in enumerate(
            placed.sort_values("spotted_at", ascending=False).iterrows()
        ):
            ph = round(stake * row["home_odds"] - stake * 2)
            pa = round(stake * row["away_odds"] - stake * 2)
            hb = _row_get(row, "home_bookmaker", "Bet365") or "Bet365"
            ab = _row_get(row, "away_bookmaker", "1xBet") or "1xBet"

            if row["won"]:
                ap = (
                    int(row["actual_profit"] * (stake / 5000))
                    if pd.notna(_row_get(row, "actual_profit"))
                    else ph
                )
                status_html = f'<span class="badge badge-green">✓ WON +${ap:,}</span>'
            elif row["lost"]:
                status_html = f'<span class="badge badge-red">✗ DRAW LOSS -${stake * 2:,}</span>'
            elif row["expired"]:
                status_html = '<span class="badge badge-red">⏰ MATCH FINISHED — UPDATE RESULT</span>'
            else:
                status_html = '<span class="badge badge-yellow">⏳ AWAITING KICKOFF</span>'

            spotted_str = safe_strftime(row["spotted_at"], "%b %d, %H:%M")
            st.markdown(f"""
            <div class="opp-card {'opp-card-won' if row['won'] else 'opp-card-lost' if row['lost'] else 'opp-card-expired' if row['expired'] else 'opp-card-placed'}">
              <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                  <div style="font-family:'Syne',sans-serif;font-size:15px;font-weight:700;color:#e8edf5;margin-bottom:4px">
                    {row['home_team']} vs {row['away_team']}
                  </div>
                  <div style="font-size:12px;color:#5a6a82">{row['league_name']} · {spotted_str}</div>
                </div>
                {status_html}
              </div>
              <div style="display:flex;gap:24px;margin-top:14px;flex-wrap:wrap">
                <div><div style="font-size:10px;color:#5a6a82;margin-bottom:3px">HOME ODDS</div>
                  <div style="font-family:'Space Mono',monospace;color:#e8edf5">{row['home_odds']}x <span style="color:#5a6a82;font-size:11px">via {hb}</span></div></div>
                <div><div style="font-size:10px;color:#5a6a82;margin-bottom:3px">AWAY ODDS</div>
                  <div style="font-family:'Space Mono',monospace;color:#e8edf5">{row['away_odds']}x <span style="color:#5a6a82;font-size:11px">via {ab}</span></div></div>
                <div><div style="font-size:10px;color:#5a6a82;margin-bottom:3px">IF HOME WINS</div>
                  <div class="profit-positive">+${ph:,}</div></div>
                <div><div style="font-size:10px;color:#5a6a82;margin-bottom:3px">IF AWAY WINS</div>
                  <div class="profit-positive">+${pa:,}</div></div>
                <div><div style="font-size:10px;color:#5a6a82;margin-bottom:3px">IF DRAW</div>
                  <div class="profit-negative">-${stake * 2:,}</div></div>
                <div><div style="font-size:10px;color:#5a6a82;margin-bottom:3px">EV SCORE</div>
                  <div style="font-family:'Space Mono',monospace;color:#ffd000">+{row['ev_score']:.3f}</div></div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        if not placed_resolved.empty:
            st.markdown(
                '<div class="section-title" style="margin-top:20px">P&L from your bets</div>',
                unsafe_allow_html=True,
            )
            pb2 = placed_resolved.sort_values("spotted_at").copy()
            pb2["sim"]   = pb2["actual_profit"] * (stake / 5000)
            pb2["cumpl"] = pb2["sim"].cumsum()
            fig_pb = go.Figure()
            fig_pb.add_trace(go.Scatter(
                x=pb2["spotted_at"], y=pb2["cumpl"],
                fill="tozeroy", fillcolor="rgba(0,255,136,0.07)",
                line=dict(color=GREEN, width=2.5),
            ))
            fig_pb.add_hline(y=0, line_dash="dot", line_color="#243044")
            fig_pb.update_layout(
                **CHART, height=250,
                yaxis=dict(gridcolor="#1a2233", tickprefix="$"),
                xaxis=dict(showgrid=False), showlegend=False,
            )
            st.plotly_chart(fig_pb, use_container_width=True)

# ══════════════════════════════════════════════════════════
#   TAB 4 — ANALYTICS
# ══════════════════════════════════════════════════════════
with tab4:
    t4_c1, t4_c2 = st.columns(2)
    with t4_c1:
        st.markdown('<div class="section-title">By hour of day</div>', unsafe_allow_html=True)
        hourly = fdf.groupby("hour").size().reset_index(name="count")
        fig_h = px.bar(hourly, x="hour", y="count", color_discrete_sequence=[BLUE])
        fig_h.update_layout(
            **CHART, height=220,
            xaxis=dict(showgrid=False, title="Hour (UTC)"),
            yaxis=dict(gridcolor="#1a2233"),
        )
        st.plotly_chart(fig_h, use_container_width=True)

    with t4_c2:
        st.markdown('<div class="section-title">By day of week</div>', unsafe_allow_html=True)
        dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        dow = (
            fdf.groupby("dow").size()
            .reindex(dow_order, fill_value=0)
            .reset_index(name="count")
        )
        fig_d = px.bar(dow, x="dow", y="count", color_discrete_sequence=[YELLOW])
        fig_d.update_layout(
            **CHART, height=220,
            xaxis=dict(showgrid=False, title=""),
            yaxis=dict(gridcolor="#1a2233"),
        )
        st.plotly_chart(fig_d, use_container_width=True)

    t4_c3, t4_c4 = st.columns(2)
    with t4_c3:
        st.markdown('<div class="section-title">Home odds distribution</div>', unsafe_allow_html=True)
        fig_ho = px.histogram(fdf, x="home_odds", nbins=25, color_discrete_sequence=[GREEN])
        fig_ho.update_layout(
            **CHART, height=200,
            xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#1a2233"),
        )
        st.plotly_chart(fig_ho, use_container_width=True)

    with t4_c4:
        st.markdown('<div class="section-title">Away odds distribution</div>', unsafe_allow_html=True)
        fig_ao = px.histogram(fdf, x="away_odds", nbins=25, color_discrete_sequence=[GREEN2])
        fig_ao.update_layout(
            **CHART, height=200,
            xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#1a2233"),
        )
        st.plotly_chart(fig_ao, use_container_width=True)

    st.markdown('<div class="section-title">EV score over time</div>', unsafe_allow_html=True)
    fs = fdf.sort_values("spotted_at").copy()
    fig_ev = go.Figure()
    fig_ev.add_trace(go.Scatter(
        x=fs["spotted_at"], y=fs["ev_score"], mode="markers",
        marker=dict(color=GREEN, size=5, opacity=0.5), name="EV",
    ))
    if len(fs) > 5:
        fs["ev_ma"] = fs["ev_score"].rolling(7, min_periods=1).mean()
        fig_ev.add_trace(go.Scatter(
            x=fs["spotted_at"], y=fs["ev_ma"],
            line=dict(color=YELLOW, width=2), name="7-period MA",
        ))
    fig_ev.add_hline(
        y=fs["ev_score"].mean(), line_dash="dot", line_color=BLUE,
        annotation_text=f"avg +{fs['ev_score'].mean():.2f}",
        annotation_font_color=BLUE,
    )
    fig_ev.update_layout(
        **CHART, height=280,
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#1a2233"),
        showlegend=True,
    )
    st.plotly_chart(fig_ev, use_container_width=True)

    st.markdown('<div class="section-title">League performance table</div>', unsafe_allow_html=True)
    ls = fdf.groupby("league_name").agg(
        total=("won", "count"),
        wins=("won", "sum"),
        draws=("lost", "sum"),
        avg_home=("home_odds", "mean"),
        avg_away=("away_odds", "mean"),
        avg_ev=("ev_score", "mean"),
    ).reset_index()
    ls["win_rate%"] = (
        ls.apply(
            lambda r: round(r["wins"] / (r["wins"] + r["draws"]) * 100, 1)
            if (r["wins"] + r["draws"]) > 0
            else 0.0,
            axis=1,
        )
    )
    ls["avg_home"] = ls["avg_home"].round(2)
    ls["avg_away"] = ls["avg_away"].round(2)
    ls["avg_ev"]   = ls["avg_ev"].round(3)
    ls = ls.rename(columns={
        "league_name": "League", "total": "Total", "wins": "Wins",
        "draws": "Draws", "avg_home": "Avg Home", "avg_away": "Avg Away", "avg_ev": "Avg EV",
    })
    st.dataframe(ls, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════
#   TAB 5 — BOOKMAKERS
# ══════════════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="section-title">Best bookmakers per league</div>', unsafe_allow_html=True)

    for lk, ln in LEAGUE_NAMES.items():
        bks = BOOKMAKERS.get(lk, [])
        st.markdown(f"**{ln}**")
        cols = st.columns(len(bks))
        for i, bk in enumerate(bks):
            with cols[i]:
                st.markdown(f"""
                <div style="background:#0d1117;border:1px solid #1a2233;border-radius:10px;
                padding:14px 10px;text-align:center;margin-bottom:12px">
                  <div style="font-family:'Space Mono',monospace;font-size:13px;font-weight:700;color:#e8edf5">{bk}</div>
                  <div style="font-size:10px;color:#5a6a82;margin-top:4px">Check odds here</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown(
        '<div class="section-title" style="margin-top:8px">Bookmaker strategy guide</div>',
        unsafe_allow_html=True,
    )
    tips = [
        ("🏆 Bet365",      BLUE,       "Best for Champions League & EPL. Competitive odds 48hrs before kickoff. Highest liquidity."),
        ("⚡ 1xBet",       GREEN,      "Highest odds overall. Best for La Liga & Bundesliga. Check for early market releases."),
        ("🎯 Pinnacle",    YELLOW,     "Sharpest lines, highest limits. Best for large stakes. No account restrictions."),
        ("🌟 William Hill", GREEN2,    "Strong for Premier League. Good early odds 3-4 days before match."),
        ("🔥 Bwin",        RED,        "Strong for European leagues. Often releases markets earliest — good for shifts."),
        ("💫 Unibet",      "#aa88ff",  "Good secondary source. Use to verify against primary bookmaker."),
    ]
    for name, color, tip in tips:
        st.markdown(f"""
        <div style="background:#0d1117;border:1px solid #1a2233;border-radius:10px;
        padding:14px 18px;margin-bottom:8px;display:flex;gap:16px;align-items:flex-start">
          <div style="font-family:'Space Mono',monospace;font-size:13px;font-weight:700;color:{color};min-width:160px">{name}</div>
          <div style="font-size:13px;color:#9ca3af;line-height:1.5">{tip}</div>
        </div>
        """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
#   TAB 6 — UPDATE RESULTS
# ══════════════════════════════════════════════════════════
with tab6:
    st.markdown('<div class="section-title">Update match results</div>', unsafe_allow_html=True)
    st.markdown("After a match ends, update the result here to track accuracy and P&L.")

    expired_pending = (
        fdf[fdf["expired"] & fdf["pending"]]
        .sort_values("commence_time")
        .drop_duplicates(subset="match_id")
    )
    other_pending = (
        fdf[~fdf["expired"] & fdf["pending"]]
        .sort_values("commence_time")
        .drop_duplicates(subset="match_id")
    )
    pend_df = pd.concat([expired_pending, other_pending], ignore_index=True)

    if pend_df.empty:
        st.success("No pending matches!")
    else:
        if not expired_pending.empty:
            st.warning(
                f"⏰ **{len(expired_pending)} matches have already started** — "
                "enter their results below to update your P&L."
            )
        if not other_pending.empty:
            st.info(f"🟢 **{len(other_pending)} upcoming matches** awaiting kickoff.")

        st.markdown(f"**{len(pend_df)}** total matches awaiting results")

        for t6_idx, (_, row) in enumerate(pend_df.head(30).iterrows()):
            expiry_marker = "⏰ FINISHED · " if row["expired"] else "🟢 UPCOMING · "
            spotted_str = safe_strftime(row["spotted_at"], "%b %d")
            with st.expander(
                f"{expiry_marker}{row['home_team']} vs {row['away_team']} · "
                f"{row['league_name']} · {spotted_str}"
            ):
                mt = _row_get(row, "commence_time")
                mt_str = safe_strftime(mt, "%b %d %H:%M UTC")
                if row["expired"]:
                    st.markdown(
                        f'<div style="background:rgba(255,68,85,0.08);border:1px solid '
                        f'rgba(255,68,85,0.2);border-radius:8px;padding:10px 14px;'
                        f'margin-bottom:12px;font-family:Space Mono,monospace;font-size:12px;'
                        f'color:#ff4455">⏰ Match started: {mt_str} — please enter result</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="background:rgba(0,255,136,0.05);border:1px solid '
                        f'rgba(0,255,136,0.15);border-radius:8px;padding:10px 14px;'
                        f'margin-bottom:12px;font-family:Space Mono,monospace;font-size:12px;'
                        f'color:#00ff88">🟢 Kicks off: {mt_str}</div>',
                        unsafe_allow_html=True,
                    )

                uc1, uc2, uc3 = st.columns([2, 1, 1])

                with uc1:
                    sel = st.selectbox(
                        "Result",
                        ["Select...", "home_win", "away_win", "draw"],
                        key=f"t6_res_{row['match_id']}_{t6_idx}",
                    )
                with uc2:
                    if sel == "home_win":
                        p = round(stake * row["home_odds"] - stake * 2)
                        st.metric("Profit", f"+${p:,}")
                    elif sel == "away_win":
                        p = round(stake * row["away_odds"] - stake * 2)
                        st.metric("Profit", f"+${p:,}")
                    elif sel == "draw":
                        st.metric("Loss", f"-${stake * 2:,}")
                with uc3:
                    placed_check = st.checkbox(
                        "Bet was placed",
                        value=bool(_row_get(row, "bet_placed", False)),
                        key=f"t6_bp_{row['match_id']}_{t6_idx}",
                    )

                if sel != "Select...":
                    if sel == "home_win":   ap = round(5000 * row["home_odds"] - 10000)
                    elif sel == "away_win": ap = round(5000 * row["away_odds"] - 10000)
                    else:                   ap = -10000

                    if st.button("💾 Save result", key=f"t6_sv_{row['match_id']}_{t6_idx}"):
                        ok = sb_patch("opportunities", row["match_id"], {
                            "result": sel,
                            "actual_profit": ap,
                            "bet_placed": placed_check,
                        })
                        if ok:
                            st.success("Saved!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Failed — check DB connection")

# ══════════════════════════════════════════════════════════
#   TAB 7 — P&L TRACKER
# ══════════════════════════════════════════════════════════
with tab7:
    st.markdown('<div class="section-title">P&L tracker</div>', unsafe_allow_html=True)

    t7_c1, t7_c2, t7_c3, t7_c4 = st.columns(4)
    t7_c1.metric("Stake per side", f"${stake:,}")
    t7_c2.metric("Total invested (sim)", f"${stake * 2 * total:,}")
    t7_c3.metric("Net P&L (sim)", f"${total_pl:,}")
    roi = (total_pl / (stake * 2 * len(resolved)) * 100) if len(resolved) > 0 else 0.0
    t7_c4.metric("ROI", f"{roi:.1f}%")

    if not resolved.empty:
        r3 = resolved.sort_values("spotted_at").copy()
        r3["sim"]    = r3["actual_profit"] * (stake / 5000)
        r3["cumpl"]  = r3["sim"].cumsum()
        r3["wrrate"] = r3["won"].expanding().mean() * 100

        fig_pl = go.Figure()
        fig_pl.add_trace(go.Scatter(
            x=r3["spotted_at"], y=r3["cumpl"],
            fill="tozeroy", fillcolor="rgba(0,255,136,0.07)",
            line=dict(color=GREEN, width=2.5), name="All opps",
        ))
        if not placed.empty and not placed[~placed["pending"]].empty:
            pr = placed[~placed["pending"]].sort_values("spotted_at").copy()
            pr["sim"]   = pr["actual_profit"] * (stake / 5000)
            pr["cumpl"] = pr["sim"].cumsum()
            fig_pl.add_trace(go.Scatter(
                x=pr["spotted_at"], y=pr["cumpl"],
                line=dict(color=YELLOW, width=2, dash="dot"), name="My bets only",
            ))
        fig_pl.add_hline(y=0, line_dash="dot", line_color="#243044")
        fig_pl.update_layout(
            **CHART, height=300,
            yaxis=dict(gridcolor="#1a2233", tickprefix="$"),
            xaxis=dict(showgrid=False),
            legend=dict(bgcolor="#0d1117"),
        )
        st.plotly_chart(fig_pl, use_container_width=True)

        st.markdown('<div class="section-title">Rolling win rate</div>', unsafe_allow_html=True)
        fig_wr = go.Figure()
        fig_wr.add_trace(go.Scatter(
            x=r3["spotted_at"], y=r3["wrrate"],
            line=dict(color=YELLOW, width=2.5),
        ))
        fig_wr.add_hline(
            y=80, line_dash="dot", line_color=GREEN,
            annotation_text="80% target", annotation_font_color=GREEN,
        )
        fig_wr.update_layout(
            **CHART, height=220,
            yaxis=dict(gridcolor="#1a2233", ticksuffix="%", range=[0, 100]),
            xaxis=dict(showgrid=False), showlegend=False,
        )
        st.plotly_chart(fig_wr, use_container_width=True)

        st.markdown('<div class="section-title">Per-bet log</div>', unsafe_allow_html=True)
        log_df = r3[[
            "spotted_at", "home_team", "away_team", "league_name",
            "home_odds", "away_odds", "result", "sim", "cumpl",
        ]].copy()
        log_df["spotted_at"] = log_df["spotted_at"].apply(lambda x: safe_strftime(x, "%b %d %H:%M"))
        log_df["sim"]   = log_df["sim"].apply(lambda x: f"+${x:,.0f}" if x > 0 else f"-${abs(x):,.0f}")
        log_df["cumpl"] = log_df["cumpl"].apply(lambda x: f"${x:,.0f}")
        log_df.columns  = [
            "Date", "Home", "Away", "League",
            "Home Odds", "Away Odds", "Result", "Bet P&L", "Running Total",
        ]
        st.dataframe(log_df, use_container_width=True, height=350, hide_index=True)
    else:
        st.info("No resolved matches yet. Add results in the Update Results tab.")

    st.markdown(
        '<div class="section-title" style="margin-top:20px">What-if calculator</div>',
        unsafe_allow_html=True,
    )
    t7_wc1, t7_wc2, t7_wc3 = st.columns(3)
    with t7_wc1:
        wi_stake = st.slider(
            "Stake per side ($)", 100, 50_000, stake, 500,
            key="wi_stake_slider",
        )
    with t7_wc2:
        wi_pl = (
            int(resolved["actual_profit"].sum() * (wi_stake / 5000))
            if not resolved.empty
            else 0
        )
        st.metric(f"P&L with ${wi_stake:,} stake", f"${wi_pl:,}")
    with t7_wc3:
        wi_roi = (
            (wi_pl / (wi_stake * 2 * len(resolved)) * 100)
            if len(resolved) > 0
            else 0.0
        )
        st.metric("ROI", f"{wi_roi:.1f}%")