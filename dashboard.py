"""
============================================================
  ODDS MONITOR DASHBOARD v2  —  dashboard.py
  Full featured dashboard with enhanced UI and features
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
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@300;400;500;600&display=swap');
  
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
  h1, h2, h3 { font-family: 'JetBrains Mono', monospace !important; }
  
  .metric-card {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 12px;
  }
  .opp-card {
    background: #052e16;
    border: 1px solid #166534;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 10px;
  }
  .alert-card {
    background: #1c1917;
    border: 1px solid #292524;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 8px;
  }
  .bk-badge {
    display: inline-block;
    background: #1e3a5f;
    color: #93c5fd;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 500;
    margin-right: 4px;
  }
  .win-badge  { background:#052e16; color:#86efac; border-radius:6px; padding:2px 8px; font-size:12px; }
  .loss-badge { background:#450a0a; color:#fca5a5; border-radius:6px; padding:2px 8px; font-size:12px; }
  .pend-badge { background:#1c1917; color:#a8a29e; border-radius:6px; padding:2px 8px; font-size:12px; }
  
  div[data-testid="stMetric"] {
    background: #111827;
    border-radius: 12px;
    padding: 16px 20px;
    border: 1px solid #1f2937;
  }
  .stSelectbox > div { background: #111827; }
  div[data-testid="stSidebar"] { background: #0d1117; }
</style>
""", unsafe_allow_html=True)

# ── config ──────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", st.secrets.get("SUPABASE_URL", ""))
SUPABASE_KEY = os.getenv("SUPABASE_KEY", st.secrets.get("SUPABASE_KEY", ""))

BOOKMAKERS = {
    "soccer_epl":                ["Bet365", "William Hill", "1xBet", "Unibet", "Betway"],
    "soccer_uefa_champs_league": ["Bet365", "Bwin", "1xBet", "Pinnacle", "Betfair"],
    "soccer_spain_la_liga":      ["Bet365", "Bwin", "1xBet", "Betsson", "Unibet"],
    "soccer_germany_bundesliga": ["Bet365", "Bwin", "1xBet", "Betway", "Tipico"],
    "soccer_italy_serie_a":      ["Bet365", "Sisal", "1xBet", "Snai", "Unibet"],
    "soccer_france_ligue_one":   ["Bet365", "PMU", "1xBet", "Unibet", "Bwin"],
}

LEAGUE_NAMES = {
    "soccer_epl":                "Premier League 🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "soccer_uefa_champs_league": "Champions League 🏆",
    "soccer_spain_la_liga":      "La Liga 🇪🇸",
    "soccer_germany_bundesliga": "Bundesliga 🇩🇪",
    "soccer_italy_serie_a":      "Serie A 🇮🇹",
    "soccer_france_ligue_one":   "Ligue 1 🇫🇷",
}

def supabase_get(table, params={}):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table}",
                         headers=headers, params=params, timeout=15)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        return []

def supabase_patch(table, match_id, data):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?match_id=eq.{match_id}",
            headers=headers, json=data, timeout=15)
        return r.status_code in [200, 204]
    except:
        return False

@st.cache_data(ttl=300)
def load_opportunities():
    rows = supabase_get("opportunities", {"order": "spotted_at.desc", "limit": 1000})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["spotted_at"]    = pd.to_datetime(df["spotted_at"]).dt.tz_localize(None)
    df["commence_time"] = pd.to_datetime(df["commence_time"], errors="coerce").dt.tz_localize(None)
    df["date"]          = df["spotted_at"].dt.date
    df["hour"]          = df["spotted_at"].dt.hour
    df["day_of_week"]   = df["spotted_at"].dt.day_name()
    df["won"]           = df["result"].isin(["home_win", "away_win"])
    df["lost"]          = df["result"] == "draw"
    df["pending"]       = df["result"].isna()
    df["league_name"]   = df["league"].map(LEAGUE_NAMES).fillna(df["league"])
    df["avg_odds"]      = (df["home_odds"] + df["away_odds"]) / 2
    df["ev_score"]      = df["avg_odds"] - 2.0
    return df

def demo_data():
    np.random.seed(42)
    n   = 120
    now = datetime.utcnow()
    leagues = list(LEAGUE_NAMES.keys())
    results = np.random.choice(["home_win","away_win","draw",None], n, p=[0.40,0.37,0.11,0.12])
    home_teams = ["Bayern","Real Madrid","Man City","Barcelona","PSG","Arsenal","Juventus","Inter","Liverpool","Dortmund"]
    away_teams = ["Atletico","Napoli","Porto","Ajax","Lazio","Milan","Sevilla","Lyon","Leicester","Freiburg"]
    bookmakers = ["Bet365","1xBet","William Hill","Bwin","Pinnacle","Unibet"]
    data = []
    for i in range(n):
        ho  = round(2.05 + np.random.exponential(0.45), 2)
        ao  = round(2.05 + np.random.exponential(0.40), 2)
        res = results[i]
        ap  = None
        league = np.random.choice(leagues)
        if res == "home_win":   ap = round(5000 * ho - 10000)
        elif res == "away_win": ap = round(5000 * ao - 10000)
        elif res == "draw":     ap = -10000
        spot = now - timedelta(days=int(np.random.uniform(0,30)), hours=int(np.random.uniform(0,24)))
        data.append({
            "match_id":            f"match_{i}",
            "home_team":           np.random.choice(home_teams),
            "away_team":           np.random.choice(away_teams),
            "league":              league,
            "league_name":         LEAGUE_NAMES[league],
            "home_odds":           ho,
            "away_odds":           ao,
            "draw_odds":           round(3.1 + np.random.normal(0, 0.3), 2),
            "home_bookmaker":      np.random.choice(bookmakers),
            "away_bookmaker":      np.random.choice(bookmakers),
            "profit_if_home_wins": round(5000 * ho - 10000),
            "profit_if_away_wins": round(5000 * ao - 10000),
            "loss_if_draw":        -10000,
            "spotted_at":          spot,
            "commence_time":       spot + timedelta(days=2),
            "result":              res,
            "actual_profit":       ap,
            "date":                spot.date(),
            "hour":                spot.hour,
            "day_of_week":         spot.strftime("%A"),
            "won":                 res in ["home_win","away_win"],
            "lost":                res == "draw",
            "pending":             res is None,
            "avg_odds":            round((ho + ao) / 2, 2),
            "ev_score":            round((ho + ao) / 2 - 2.0, 2),
            "bet_placed":          False,
            "notes":               "",
        })
    return pd.DataFrame(data)

# ══════════════════════════════════════════════════════════
#   SIDEBAR
# ══════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## ⚙️ Filters")
    days_back    = st.slider("Days to show", 1, 90, 30)
    all_leagues  = list(LEAGUE_NAMES.values())
    sel_leagues  = st.multiselect("Leagues", all_leagues, default=all_leagues)
    min_odds_filter = st.slider("Min avg odds", 2.0, 4.0, 2.0, 0.05)
    show_pending = st.checkbox("Show pending", True)
    show_resolved = st.checkbox("Show resolved", True)

    st.divider()
    st.markdown("## 📐 Simulation")
    stake = st.number_input("Stake per side ($)", 100, 50000, 5000, 500)

    st.divider()
    st.markdown("## 🔄 Actions")
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()

# ══════════════════════════════════════════════════════════
#   LOAD DATA
# ══════════════════════════════════════════════════════════

df = load_opportunities()
using_demo = df.empty
if using_demo:
    st.toast("No DB connected — showing demo data", icon="ℹ️")
    df = demo_data()

# apply filters
cutoff = datetime.utcnow() - timedelta(days=days_back)
fdf = df[df["spotted_at"] >= cutoff].copy()
fdf = fdf[fdf["league_name"].isin(sel_leagues)]
fdf = fdf[fdf["avg_odds"] >= min_odds_filter]
if not show_pending:
    fdf = fdf[~fdf["pending"]]
if not show_resolved:
    fdf = fdf[fdf["pending"]]

resolved = fdf[~fdf["pending"]].copy()

# ══════════════════════════════════════════════════════════
#   HEADER
# ══════════════════════════════════════════════════════════

st.markdown("# 📊 odds monitor pro")
st.markdown(f"*Tracking both-teams-above-2x opportunities · {'Demo mode' if using_demo else 'Live data'} · Last refresh: {datetime.now().strftime('%H:%M:%S')}*")
st.divider()

# ══════════════════════════════════════════════════════════
#   TOP METRICS
# ══════════════════════════════════════════════════════════

wins     = int(fdf["won"].sum())
draws    = int(fdf["lost"].sum())
pending  = int(fdf["pending"].sum())
total    = len(fdf)
win_rate = (wins / (wins + draws) * 100) if (wins + draws) > 0 else 0
total_pl = int(resolved["actual_profit"].sum()) if not resolved.empty else 0
sim_pl   = int(resolved["actual_profit"].sum() * (stake / 5000)) if not resolved.empty else 0
best_league = fdf.groupby("league_name").size().idxmax() if not fdf.empty else "—"
avg_ev   = round(fdf["ev_score"].mean(), 2) if not fdf.empty else 0

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total opportunities", total)
c2.metric("Won", wins, f"{win_rate:.1f}% win rate")
c3.metric("Lost to draw", draws)
c4.metric("Pending results", pending)
c5.metric("Simulated P&L", f"${sim_pl:,}", delta=f"${sim_pl:,}" if sim_pl != 0 else None)
c6.metric("Avg EV score", f"+{avg_ev}" if avg_ev > 0 else str(avg_ev))

st.divider()

# ══════════════════════════════════════════════════════════
#   TABS
# ══════════════════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📈 Overview",
    "🎯 Opportunities",
    "📊 Analytics",
    "🏦 Bookmakers",
    "✏️ Update Results",
    "💰 P&L Tracker",
])

# ══════════════════════════════════════════════════════════
#   TAB 1 — OVERVIEW
# ══════════════════════════════════════════════════════════

with tab1:
    col_a, col_b = st.columns([2, 1])

    with col_a:
        st.markdown("#### opportunities per day")
        daily = fdf.groupby("date").size().reset_index(name="count")
        fig = px.bar(daily, x="date", y="count", color_discrete_sequence=["#22c55e"])
        fig.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                          font_color="#9ca3af", margin=dict(l=0,r=0,t=10,b=0), height=240,
                          xaxis=dict(showgrid=False, color="#4b5563"),
                          yaxis=dict(gridcolor="#1f2937", color="#4b5563"))
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.markdown("#### by league")
        by_league = fdf.groupby("league_name").size().reset_index(name="count").sort_values("count")
        fig2 = px.bar(by_league, x="count", y="league_name", orientation="h",
                      color_discrete_sequence=["#4ade80"])
        fig2.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                           font_color="#9ca3af", margin=dict(l=0,r=0,t=10,b=0), height=240,
                           xaxis=dict(showgrid=False), yaxis=dict(showgrid=False, title=""))
        st.plotly_chart(fig2, use_container_width=True)

    col_c, col_d = st.columns([2, 1])

    with col_c:
        st.markdown("#### cumulative P&L simulation")
        if not resolved.empty:
            r2 = resolved.sort_values("spotted_at").copy()
            r2["sim_profit"]    = r2["actual_profit"] * (stake / 5000)
            r2["cumulative_pl"] = r2["sim_profit"].cumsum()
            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=r2["spotted_at"], y=r2["cumulative_pl"],
                fill="tozeroy", fillcolor="rgba(34,197,94,0.1)",
                line=dict(color="#22c55e", width=2), name="P&L"
            ))
            fig3.add_hline(y=0, line_dash="dot", line_color="#374151")
            fig3.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                               font_color="#9ca3af", margin=dict(l=0,r=0,t=10,b=0),
                               yaxis=dict(gridcolor="#1f2937", tickprefix="$"),
                               xaxis=dict(showgrid=False), showlegend=False, height=260)
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("No resolved matches yet — P&L chart will appear once results are added.")

    with col_d:
        st.markdown("#### result breakdown")
        if wins + draws > 0:
            fig4 = go.Figure(go.Pie(
                labels=["Win (no draw)", "Draw loss"],
                values=[wins, draws], hole=0.65,
                marker_colors=["#22c55e", "#ef4444"],
                textinfo="percent+label", textfont_size=12,
            ))
            fig4.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                               font_color="#9ca3af", margin=dict(l=0,r=0,t=10,b=10),
                               showlegend=False, height=260)
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("No resolved results yet.")

    # odds landscape
    st.markdown("#### odds landscape — every dot is one opportunity")
    color_map = {"home_win":"#22c55e","away_win":"#4ade80","draw":"#ef4444","None":"#374151"}
    fig5 = px.scatter(fdf, x="home_odds", y="away_odds",
                      color=fdf["result"].fillna("None"),
                      color_discrete_map=color_map,
                      size="ev_score", size_max=15,
                      hover_data=["home_team","away_team","league_name","spotted_at"],
                      labels={"home_odds":"Home odds (x)","away_odds":"Away odds (x)",
                              "color":"Result"})
    fig5.add_vline(x=2.0, line_dash="dot", line_color="#374151",
                   annotation_text="2x threshold", annotation_font_color="#6b7280")
    fig5.add_hline(y=2.0, line_dash="dot", line_color="#374151")
    fig5.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                       font_color="#9ca3af", margin=dict(l=0,r=0,t=20,b=0),
                       xaxis=dict(gridcolor="#1f2937"), yaxis=dict(gridcolor="#1f2937"),
                       height=350)
    st.plotly_chart(fig5, use_container_width=True)

# ══════════════════════════════════════════════════════════
#   TAB 2 — OPPORTUNITIES
# ══════════════════════════════════════════════════════════

with tab2:
    st.markdown("#### live opportunity feed")

    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        sort_by = st.selectbox("Sort by", ["Most recent","Highest home odds","Highest away odds","Highest EV"], key="tab2_sort_by")
    with col_filter2:
        result_filter = st.selectbox("Filter by result", ["All","Pending","Won","Lost to draw"], key="tab2_result_filter")

    dff = fdf.copy()
    if result_filter == "Pending":        dff = dff[dff["pending"]]
    elif result_filter == "Won":          dff = dff[dff["won"]]
    elif result_filter == "Lost to draw": dff = dff[dff["lost"]]

    if sort_by == "Highest home odds":   dff = dff.sort_values("home_odds", ascending=False)
    elif sort_by == "Highest away odds": dff = dff.sort_values("away_odds", ascending=False)
    elif sort_by == "Highest EV":        dff = dff.sort_values("ev_score", ascending=False)
    else:                                dff = dff.sort_values("spotted_at", ascending=False)

    st.markdown(f"Showing **{len(dff)}** opportunities")

    for _, row in dff.head(50).iterrows():
        ph = round(stake * row["home_odds"] - stake * 2)
        pa = round(stake * row["away_odds"] - stake * 2)
        result_badge = ""
        if row["won"]:    result_badge = "🟢 Won"
        elif row["lost"]: result_badge = "🔴 Draw loss"
        else:             result_badge = "⏳ Pending"

        home_bk = row.get("home_bookmaker", "Bet365")
        away_bk = row.get("away_bookmaker", "1xBet")
        if not home_bk or pd.isna(home_bk): home_bk = "Bet365"
        if not away_bk or pd.isna(away_bk): away_bk = "1xBet"

        with st.expander(f"**{row['home_team']} vs {row['away_team']}** — {row['league_name']} · {row['spotted_at'].strftime('%b %d, %H:%M')} · {result_badge}"):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(f"🏠 {row['home_team']}", f"{row['home_odds']}x", f"via {home_bk}")
            c2.metric("Draw", f"{row['draw_odds']}x")
            c3.metric(f"✈️ {row['away_team']}", f"{row['away_odds']}x", f"via {away_bk}")
            c4.metric("EV Score", f"+{row['ev_score']:.2f}")

            st.markdown("---")
            p1, p2, p3 = st.columns(3)
            p1.metric(f"If {row['home_team']} wins", f"+${ph:,}", "profit")
            p2.metric(f"If {row['away_team']} wins", f"+${pa:,}", "profit")
            p3.metric("If draw", f"-${stake*2:,}", "loss")

            st.markdown(f"**Bookmakers to check:** `{home_bk}` for home · `{away_bk}` for away")
            match_time = row["commence_time"].strftime('%b %d, %Y %H:%M') if pd.notna(row.get("commence_time")) else "TBD"
            st.caption(f"Match time: {match_time} · Spotted: {row['spotted_at'].strftime('%b %d %H:%M')}")

# ══════════════════════════════════════════════════════════
#   TAB 3 — ANALYTICS
# ══════════════════════════════════════════════════════════

with tab3:
    st.markdown("#### when do opportunities appear?")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### by hour of day")
        hourly = fdf.groupby("hour").size().reset_index(name="count")
        fig_h = px.bar(hourly, x="hour", y="count", color_discrete_sequence=["#22c55e"])
        fig_h.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                            font_color="#9ca3af", height=220, margin=dict(l=0,r=0,t=10,b=0),
                            xaxis=dict(showgrid=False, title="Hour (UTC)"),
                            yaxis=dict(gridcolor="#1f2937"))
        st.plotly_chart(fig_h, use_container_width=True)

    with col2:
        st.markdown("##### by day of week")
        day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        daily_dow = fdf.groupby("day_of_week").size().reindex(day_order, fill_value=0).reset_index(name="count")
        fig_d = px.bar(daily_dow, x="day_of_week", y="count", color_discrete_sequence=["#4ade80"])
        fig_d.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                            font_color="#9ca3af", height=220, margin=dict(l=0,r=0,t=10,b=0),
                            xaxis=dict(showgrid=False, title=""),
                            yaxis=dict(gridcolor="#1f2937"))
        st.plotly_chart(fig_d, use_container_width=True)

    st.markdown("#### odds distribution")
    col3, col4 = st.columns(2)

    with col3:
        st.markdown("##### home odds histogram")
        fig_ho = px.histogram(fdf, x="home_odds", nbins=20, color_discrete_sequence=["#22c55e"])
        fig_ho.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                             font_color="#9ca3af", height=220, margin=dict(l=0,r=0,t=10,b=0),
                             xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#1f2937"))
        st.plotly_chart(fig_ho, use_container_width=True)

    with col4:
        st.markdown("##### away odds histogram")
        fig_ao = px.histogram(fdf, x="away_odds", nbins=20, color_discrete_sequence=["#4ade80"])
        fig_ao.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                             font_color="#9ca3af", height=220, margin=dict(l=0,r=0,t=10,b=0),
                             xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#1f2937"))
        st.plotly_chart(fig_ao, use_container_width=True)

    st.markdown("#### league performance comparison")
    league_stats = fdf.groupby("league_name").agg(
        total=("won","count"),
        wins=("won","sum"),
        draws=("lost","sum"),
        avg_home_odds=("home_odds","mean"),
        avg_away_odds=("away_odds","mean"),
        avg_ev=("ev_score","mean"),
    ).reset_index()
    league_stats["win_rate"] = (league_stats["wins"] / (league_stats["wins"] + league_stats["draws"]) * 100).round(1)
    league_stats["avg_home_odds"] = league_stats["avg_home_odds"].round(2)
    league_stats["avg_away_odds"] = league_stats["avg_away_odds"].round(2)
    league_stats["avg_ev"]        = league_stats["avg_ev"].round(3)
    st.dataframe(league_stats, use_container_width=True, height=250)

    st.markdown("#### EV score over time")
    fdf_sorted = fdf.sort_values("spotted_at")
    fig_ev = go.Figure()
    fig_ev.add_trace(go.Scatter(
        x=fdf_sorted["spotted_at"], y=fdf_sorted["ev_score"],
        mode="markers", marker=dict(color="#22c55e", size=5, opacity=0.6),
        name="EV Score"
    ))
    fig_ev.add_hline(y=fdf["ev_score"].mean(), line_dash="dot", line_color="#f59e0b",
                     annotation_text=f"avg EV: +{fdf['ev_score'].mean():.2f}",
                     annotation_font_color="#f59e0b")
    fig_ev.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                         font_color="#9ca3af", height=280, margin=dict(l=0,r=0,t=20,b=0),
                         xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#1f2937"),
                         showlegend=False)
    st.plotly_chart(fig_ev, use_container_width=True)

# ══════════════════════════════════════════════════════════
#   TAB 4 — BOOKMAKERS
# ══════════════════════════════════════════════════════════

with tab4:
    st.markdown("#### bookmaker reference guide")
    st.markdown("*These are the best bookmakers to check for each league when an opportunity is spotted*")

    for league_key, league_name in LEAGUE_NAMES.items():
        bookies = BOOKMAKERS.get(league_key, [])
        with st.expander(f"**{league_name}**"):
            cols = st.columns(len(bookies))
            for i, bk in enumerate(bookies):
                with cols[i]:
                    st.markdown(f"""
                    <div style="background:#111827;border:1px solid #1f2937;border-radius:8px;padding:12px;text-align:center">
                        <div style="font-size:13px;font-weight:600;color:#e5e7eb">{bk}</div>
                        <div style="font-size:11px;color:#6b7280;margin-top:4px">Check odds here</div>
                    </div>
                    """, unsafe_allow_html=True)

    st.divider()
    st.markdown("#### bookmaker odds comparison tips")

    tips = [
        ("🏆 Bet365", "Best for Champions League and Premier League. Usually offers competitive odds 48hrs before kickoff."),
        ("⚡ 1xBet", "Highest odds overall, especially for La Liga and Bundesliga. Check for early odds releases."),
        ("🎯 Pinnacle", "Known for highest limits and sharpest lines. Best for large stakes."),
        ("🌟 William Hill", "Strong for Premier League. Good for early market odds 3-4 days before match."),
        ("🔥 Bwin", "Strong for European leagues. Often releases odds earliest — good for spotting shifts."),
        ("💫 Unibet", "Good secondary source. Use to verify odds from primary bookmaker."),
    ]
    for name, tip in tips:
        st.markdown(f"**{name}** — {tip}")

# ══════════════════════════════════════════════════════════
#   TAB 5 — UPDATE RESULTS
# ══════════════════════════════════════════════════════════

with tab5:
    st.markdown("#### update match results")
    st.markdown("*After a match ends, update the result here to track your accuracy and P&L*")

    pending_df = fdf[fdf["pending"]].sort_values("commence_time").drop_duplicates(subset="match_id")

    if pending_df.empty:
        st.success("No pending matches to update!")
    else:
        st.markdown(f"**{len(pending_df)} matches** waiting for results")

        for idx, (_, row) in enumerate(pending_df.head(20).iterrows()):
            with st.expander(f"{row['home_team']} vs {row['away_team']} — {row['league_name']} · {row['spotted_at'].strftime('%b %d')}"):
                c1, c2 = st.columns([2, 1])

                with c1:
                    result = st.selectbox(
                        "Result",
                        ["Select result...", "home_win", "away_win", "draw"],
                        key=f"result_{row['match_id']}_{idx}",
                    )

                with c2:
                    if result == "home_win":
                        profit = round(stake * row["home_odds"] - stake * 2)
                        st.metric("Actual profit", f"+${profit:,}")
                    elif result == "away_win":
                        profit = round(stake * row["away_odds"] - stake * 2)
                        st.metric("Actual profit", f"+${profit:,}")
                    elif result == "draw":
                        st.metric("Actual loss", f"-${stake*2:,}")

                if result != "Select result...":
                    if result == "home_win":   ap = round(5000 * row["home_odds"] - 10000)
                    elif result == "away_win": ap = round(5000 * row["away_odds"] - 10000)
                    else:                      ap = -10000

                    if st.button("Save result", key=f"save_{row['match_id']}_{idx}"):
                        success = supabase_patch("opportunities", row["match_id"], {
                            "result": result,
                            "actual_profit": ap,
                        })
                        if success:
                            st.success("Result saved!")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("Failed to save — check DB connection")

# ══════════════════════════════════════════════════════════
#   TAB 6 — P&L TRACKER
# ══════════════════════════════════════════════════════════

with tab6:
    st.markdown("#### P&L tracker — if you had bet every opportunity")

    col1, col2, col3 = st.columns(3)
    col1.metric("Stake per side", f"${stake:,}")
    col2.metric("Total invested", f"${stake * 2 * total:,}")
    col3.metric("Net P&L", f"${sim_pl:,}", delta=f"${sim_pl:,}" if sim_pl != 0 else "Pending")

    if not resolved.empty:
        r3 = resolved.sort_values("spotted_at").copy()
        r3["sim_profit"]       = r3["actual_profit"] * (stake / 5000)
        r3["cumulative_pl"]    = r3["sim_profit"].cumsum()
        r3["running_win_rate"] = r3["won"].expanding().mean() * 100

        fig_pl = go.Figure()
        fig_pl.add_trace(go.Scatter(
            x=r3["spotted_at"], y=r3["cumulative_pl"],
            name="Cumulative P&L", fill="tozeroy",
            fillcolor="rgba(34,197,94,0.1)",
            line=dict(color="#22c55e", width=2.5),
        ))
        fig_pl.add_hline(y=0, line_dash="dot", line_color="#374151")
        fig_pl.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                             font_color="#9ca3af", height=300,
                             margin=dict(l=0,r=0,t=20,b=0),
                             yaxis=dict(gridcolor="#1f2937", tickprefix="$"),
                             xaxis=dict(showgrid=False))
        st.plotly_chart(fig_pl, use_container_width=True)

        st.markdown("#### per-bet breakdown")
        pb = r3[["spotted_at","home_team","away_team","league_name",
                  "home_odds","away_odds","result","sim_profit","cumulative_pl"]].copy()
        pb["spotted_at"]    = pb["spotted_at"].dt.strftime("%b %d %H:%M")
        pb["sim_profit"]    = pb["sim_profit"].apply(lambda x: f"+${x:,.0f}" if x > 0 else f"-${abs(x):,.0f}")
        pb["cumulative_pl"] = pb["cumulative_pl"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(pb, use_container_width=True, height=350)

        st.markdown("#### rolling win rate")
        fig_wr = go.Figure()
        fig_wr.add_trace(go.Scatter(
            x=r3["spotted_at"], y=r3["running_win_rate"],
            line=dict(color="#f59e0b", width=2), name="Win rate %"
        ))
        fig_wr.add_hline(y=80, line_dash="dot", line_color="#22c55e",
                         annotation_text="80% target", annotation_font_color="#22c55e")
        fig_wr.update_layout(plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                             font_color="#9ca3af", height=250,
                             margin=dict(l=0,r=0,t=20,b=0),
                             yaxis=dict(gridcolor="#1f2937", ticksuffix="%", range=[0,100]),
                             xaxis=dict(showgrid=False), showlegend=False)
        st.plotly_chart(fig_wr, use_container_width=True)
    else:
        st.info("Add match results in the 'Update Results' tab to see P&L tracking.")

    st.divider()
    st.markdown("#### what-if calculator")
    st.markdown("Simulate different staking strategies")
    wc1, wc2 = st.columns(2)
    with wc1:
        what_if_stake = st.slider("What if stake was...", 500, 50000, stake, 500)
    with wc2:
        what_if_pl = int(resolved["actual_profit"].sum() * (what_if_stake / 5000)) if not resolved.empty else 0
        st.metric(f"P&L with ${what_if_stake:,} stake", f"${what_if_pl:,}")