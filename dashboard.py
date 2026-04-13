"""
============================================================
  ODDS MONITOR DASHBOARD  —  dashboard.py
  Streamlit web app — deploy free on streamlit.io
  Uses plain requests to talk to Supabase (no library)
============================================================
"""

import os
import requests
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Odds Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500&display=swap');
  html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
  h1, h2, h3 { font-family: 'DM Mono', monospace !important; letter-spacing: -0.02em; }
  div[data-testid="stMetric"] { background: #0e1117; border-radius: 10px; padding: 16px; border: 1px solid #1e2530; }
</style>
""", unsafe_allow_html=True)

# ── config ─────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", st.secrets.get("SUPABASE_URL", ""))
SUPABASE_KEY = os.getenv("SUPABASE_KEY", st.secrets.get("SUPABASE_KEY", ""))

def supabase_get(table: str, params: dict = {}) -> list:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=headers,
            params=params,
            timeout=15,
        )
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        st.error(f"DB error: {e}")
        return []

@st.cache_data(ttl=300)
def load_opportunities():
    rows = supabase_get("opportunities", {
        "order": "spotted_at.desc",
        "limit": 500,
    })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["spotted_at"]    = pd.to_datetime(df["spotted_at"])
    df["commence_time"] = pd.to_datetime(df["commence_time"], errors="coerce")
    df["date"]          = df["spotted_at"].dt.date
    df["won"]           = df["result"].isin(["home_win", "away_win"])
    df["lost"]          = df["result"] == "draw"
    df["pending"]       = df["result"].isna()
    return df

@st.cache_data(ttl=300)
def load_scans():
    since = (datetime.utcnow() - timedelta(days=30)).isoformat()
    rows  = supabase_get("scans", {
        "scanned_at": f"gte.{since}",
        "order": "scanned_at.desc",
        "limit": 2000,
    })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["scanned_at"] = pd.to_datetime(df["scanned_at"])
    df["date"]       = df["scanned_at"].dt.date
    return df

def demo_opportunities():
    import numpy as np
    np.random.seed(42)
    n   = 60
    now = datetime.utcnow()
    results = np.random.choice(["home_win","away_win","draw",None], n, p=[0.42,0.38,0.12,0.08])
    data = []
    for i in range(n):
        ho  = round(2.05 + np.random.exponential(0.4), 2)
        ao  = round(2.05 + np.random.exponential(0.35), 2)
        res = results[i]
        ap  = None
        if res == "home_win":   ap = round(5000 * ho - 10000)
        elif res == "away_win": ap = round(5000 * ao - 10000)
        elif res == "draw":     ap = -10000
        data.append({
            "home_team":           np.random.choice(["Bayern","Real Madrid","Man City","Barcelona","PSG","Arsenal"]),
            "away_team":           np.random.choice(["Dortmund","Atletico","Liverpool","Napoli","Porto","Ajax"]),
            "league":              np.random.choice(["Champions League","Premier League","La Liga","Serie A","Bundesliga"]),
            "home_odds":           ho,
            "away_odds":           ao,
            "draw_odds":           round(3.0 + np.random.normal(0, 0.3), 2),
            "profit_if_home_wins": round(5000 * ho - 10000),
            "profit_if_away_wins": round(5000 * ao - 10000),
            "loss_if_draw":        -10000,
            "spotted_at":          now - timedelta(days=int(np.random.uniform(0,30)), hours=int(np.random.uniform(0,24))),
            "result":              res,
            "actual_profit":       ap,
            "date":                (now - timedelta(days=int(np.random.uniform(0,30)))).date(),
            "won":                 res in ["home_win","away_win"],
            "lost":                res == "draw",
            "pending":             res is None,
        })
    return pd.DataFrame(data)

# ══════════════════════════════════════════════════════════
#   MAIN APP
# ══════════════════════════════════════════════════════════

st.markdown("## 📊 odds monitor dashboard")
st.markdown("*real-time tracking of both-teams-above-2x opportunities*")
st.divider()

df = load_opportunities()
using_demo = df.empty
if using_demo:
    st.info("No data yet or DB not connected — showing demo data.")
    df = demo_opportunities()

with st.sidebar:
    st.markdown("### Filters")
    days_back  = st.slider("Days to show", 7, 90, 30)
    leagues    = ["All"] + sorted(df["league"].unique().tolist())
    sel_league = st.selectbox("League", leagues)
    show_pending = st.checkbox("Include pending", True)

cutoff = datetime.utcnow() - timedelta(days=days_back)
cutoff = pd.Timestamp(cutoff).tz_localize(None)
df["spotted_at"] = df["spotted_at"].dt.tz_localize(None)
fdf = df[df["spotted_at"] >= cutoff]
if sel_league != "All":
    fdf = fdf[fdf["league"] == sel_league]
if not show_pending:
    fdf = fdf[~fdf["pending"]]

resolved = fdf[~fdf["pending"]]

# ── metrics ────────────────────────────────────────────────
wins     = int(fdf["won"].sum())
draws    = int(fdf["lost"].sum())
pending  = int(fdf["pending"].sum())
win_rate = (wins / (wins + draws) * 100) if (wins + draws) > 0 else 0
total_pl = resolved["actual_profit"].sum() if not resolved.empty else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Opportunities", len(fdf))
c2.metric("Won", wins, f"{win_rate:.0f}% win rate")
c3.metric("Lost to draw", draws)
c4.metric("Pending", pending)
c5.metric("Simulated P&L", f"${total_pl:,.0f}")

st.divider()

# ── charts row 1 ───────────────────────────────────────────
col_a, col_b = st.columns([2, 1])

with col_a:
    st.markdown("#### opportunities per day")
    daily = fdf.groupby("date").size().reset_index(name="count")
    fig   = px.bar(daily, x="date", y="count", color_discrete_sequence=["#1D9E75"])
    fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                      font_color="#a0aec0", margin=dict(l=0,r=0,t=10,b=0), height=220,
                      xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#1e2530"))
    st.plotly_chart(fig, use_container_width=True)

with col_b:
    st.markdown("#### by league")
    by_league = fdf.groupby("league").size().reset_index(name="count").sort_values("count")
    fig2 = px.bar(by_league, x="count", y="league", orientation="h",
                  color_discrete_sequence=["#5DCAA5"])
    fig2.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                       font_color="#a0aec0", margin=dict(l=0,r=0,t=10,b=0), height=220,
                       xaxis=dict(showgrid=False), yaxis=dict(showgrid=False, title=""))
    st.plotly_chart(fig2, use_container_width=True)

# ── charts row 2 ───────────────────────────────────────────
col_c, col_d = st.columns([2, 1])

with col_c:
    st.markdown("#### simulated cumulative P&L")
    if not resolved.empty:
        r2 = resolved.sort_values("spotted_at").copy()
        r2["cumulative_pl"] = r2["actual_profit"].cumsum()
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=r2["spotted_at"], y=r2["cumulative_pl"],
            fill="tozeroy", fillcolor="rgba(29,158,117,0.15)",
            line=dict(color="#1D9E75", width=2),
        ))
        fig3.add_hline(y=0, line_dash="dot", line_color="#4a5568")
        fig3.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                           font_color="#a0aec0", margin=dict(l=0,r=0,t=10,b=0),
                           yaxis=dict(gridcolor="#1e2530", tickprefix="$"),
                           xaxis=dict(showgrid=False), showlegend=False, height=240)
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No resolved matches yet.")

with col_d:
    st.markdown("#### result breakdown")
    if not resolved.empty:
        fig4 = go.Figure(go.Pie(
            labels=["Win", "Draw loss"], values=[wins, draws], hole=0.6,
            marker_colors=["#1D9E75", "#E24B4A"], textinfo="percent+label",
        ))
        fig4.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                           font_color="#a0aec0", margin=dict(l=0,r=0,t=10,b=20),
                           showlegend=False, height=240)
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("No resolved matches yet.")

# ── odds scatter ────────────────────────────────────────────
st.markdown("#### odds landscape")
fig5 = px.scatter(fdf, x="home_odds", y="away_odds", color="result",
                  color_discrete_map={"home_win":"#1D9E75","away_win":"#5DCAA5",
                                      "draw":"#E24B4A","None":"#4a5568"},
                  hover_data=["home_team","away_team","league"])
fig5.add_vline(x=2.0, line_dash="dot", line_color="#4a5568")
fig5.add_hline(y=2.0, line_dash="dot", line_color="#4a5568")
fig5.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                   font_color="#a0aec0", margin=dict(l=0,r=0,t=10,b=0),
                   xaxis=dict(gridcolor="#1e2530"), yaxis=dict(gridcolor="#1e2530"),
                   height=300)
st.plotly_chart(fig5, use_container_width=True)

# ── full table ──────────────────────────────────────────────
st.markdown("#### full opportunity log")
show_cols = ["spotted_at","home_team","away_team","league",
             "home_odds","away_odds","draw_odds",
             "profit_if_home_wins","profit_if_away_wins","result","actual_profit"]
show_df = fdf[[c for c in show_cols if c in fdf.columns]].copy()
show_df["spotted_at"] = show_df["spotted_at"].dt.strftime("%Y-%m-%d %H:%M")
st.dataframe(show_df, use_container_width=True, height=350)

st.divider()
st.markdown(f"<p style='text-align:center;color:#4a5568;font-size:12px'>Odds Monitor · {'Demo mode' if using_demo else 'Live data'} · Refreshes every 5 min</p>", unsafe_allow_html=True)