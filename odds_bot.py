"""
============================================================
  ODDS MONITOR BOT  —  odds_bot.py
  Runs 24/7, scans odds every hour, logs to Supabase,
  sends email alerts only for NEW opportunities
============================================================
"""

import os
import time
import logging
import requests
import base64
import pickle
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ============================================================
#   CONFIG
# ============================================================

ODDS_API_KEY   = os.getenv("ODDS_API_KEY",   "")
SUPABASE_URL   = os.getenv("SUPABASE_URL",   "")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY",   "")
EMAIL_SENDER   = os.getenv("EMAIL_SENDER",   "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER", "")

MIN_ODDS       = float(os.getenv("MIN_ODDS",       "2.0"))
STAKE_PER_SIDE = int(os.getenv("STAKE_PER_SIDE",   "5000"))
SCAN_INTERVAL  = int(os.getenv("SCAN_INTERVAL",    "3600"))

LEAGUES = [
    "soccer_uefa_champs_league",
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
]

# ============================================================
#   SUPABASE  —  plain requests, no library
# ============================================================

def supabase_headers():
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates",
    }

def log_to_db(records: list):
    if not records:
        return
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/scans",
            headers=supabase_headers(),
            json=records,
            timeout=15,
        )
        log.info(f"  Logged {len(records)} records to Supabase ({r.status_code})")
    except Exception as e:
        log.error(f"  DB write failed: {e}")

def log_opportunity(match: dict) -> bool:
    """
    Checks if this match is already in the DB.
    If NEW  → inserts it and returns True  (email it)
    If SEEN → skips insert and returns False (do not email)
    """
    profit_home = round(STAKE_PER_SIDE * match["home_odds"] - STAKE_PER_SIDE * 2)
    profit_away = round(STAKE_PER_SIDE * match["away_odds"] - STAKE_PER_SIDE * 2)
    try:
        # Check if match_id already exists
        check = requests.get(
            f"{SUPABASE_URL}/rest/v1/opportunities",
            headers=supabase_headers(),
            params={"match_id": f"eq.{match['match_id']}", "select": "match_id"},
            timeout=10,
        )
        already_exists = len(check.json()) > 0 if check.status_code == 200 else False

        if already_exists:
            return False  # Already seen — do NOT email again

        # New opportunity — insert it
        requests.post(
            f"{SUPABASE_URL}/rest/v1/opportunities",
            headers=supabase_headers(),
            json={
                "match_id":            match["match_id"],
                "home_team":           match["home_team"],
                "away_team":           match["away_team"],
                "league":              match["league"],
                "commence_time":       match["commence_time"],
                "home_odds":           match["home_odds"],
                "away_odds":           match["away_odds"],
                "draw_odds":           match["draw_odds"],
                "home_bookmaker":      match.get("home_bookmaker", ""),
                "away_bookmaker":      match.get("away_bookmaker", ""),
                "profit_if_home_wins": profit_home,
                "profit_if_away_wins": profit_away,
                "loss_if_draw":        -(STAKE_PER_SIDE * 2),
                "spotted_at":          match["scanned_at"],
            },
            timeout=15,
        )
        return True  # Brand new — email it

    except Exception as e:
        log.error(f"  Opportunity log failed: {e}")
        return False

# ============================================================
#   ODDS FETCHING — The Odds API
# ============================================================

def fetch_odds_api(league: str) -> list:
    url = f"https://api.the-odds-api.com/v4/sports/{league}/odds"
    params = {
        "apiKey":     ODDS_API_KEY,
        "regions":    "eu",
        "markets":    "h2h",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        log.info(f"  [OddsAPI] {league}: {len(data)} matches")
        return data
    except Exception as e:
        log.error(f"  [OddsAPI] {league} fetch failed: {e}")
        return []

def parse_odds_api_match(raw: dict, league: str) -> dict | None:
    home     = raw.get("home_team")
    away     = raw.get("away_team")
    commence = raw.get("commence_time", "")
    best     = {"home": 0.0, "draw": 0.0, "away": 0.0,
                "home_bookmaker": "", "away_bookmaker": ""}

    for bk in raw.get("bookmakers", []):
        bk_name = bk.get("title", "")
        for mkt in bk.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            for o in mkt.get("outcomes", []):
                name  = o.get("name")
                price = o.get("price", 0)
                if name == home and price > best["home"]:
                    best["home"], best["home_bookmaker"] = price, bk_name
                elif name == away and price > best["away"]:
                    best["away"], best["away_bookmaker"] = price, bk_name
                elif name == "Draw" and price > best["draw"]:
                    best["draw"] = price

    if not best["home"] or not best["away"]:
        return None

    return {
        "match_id":       f"{home}vs{away}".replace(" ", "_"),
        "home_team":      home,
        "away_team":      away,
        "league":         league,
        "commence_time":  commence,
        "home_odds":      round(best["home"], 2),
        "away_odds":      round(best["away"], 2),
        "draw_odds":      round(best["draw"], 2),
        "home_bookmaker": best["home_bookmaker"],
        "away_bookmaker": best["away_bookmaker"],
        "is_opportunity": best["home"] > MIN_ODDS and best["away"] > MIN_ODDS,
        "scanned_at":     datetime.now(timezone.utc).isoformat(),
    }

# ============================================================
#   CUSTOM FETCHERS — Stake & Polymarket (stubs)
#   Implement these when you have API access
# ============================================================

def fetch_stake_odds(league: str) -> list:
    """
    TODO: Implement Stake.com odds fetching.
    Return list of dicts with keys:
      home_team, away_team, commence_time,
      home_odds, away_odds, draw_odds, source
    """
    log.info(f"  [Stake] {league}: stub — no data")
    return []

def fetch_polymarket_odds(league: str) -> list:
    """
    TODO: Implement Polymarket odds fetching.
    Return same format as fetch_stake_odds.
    """
    log.info(f"  [Polymarket] {league}: stub — no data")
    return []

def parse_custom_match(match: dict, league: str) -> dict | None:
    home      = match.get("home_team")
    away      = match.get("away_team")
    if not home or not away:
        return None
    ho = match.get("home_odds", 0)
    ao = match.get("away_odds", 0)
    do = match.get("draw_odds", 0)
    src = match.get("source", "Custom")
    return {
        "match_id":       f"{home}vs{away}".replace(" ", "_"),
        "home_team":      home,
        "away_team":      away,
        "league":         league,
        "commence_time":  match.get("commence_time", ""),
        "home_odds":      round(ho, 2),
        "away_odds":      round(ao, 2),
        "draw_odds":      round(do, 2),
        "home_bookmaker": src,
        "away_bookmaker": src,
        "is_opportunity": ho > MIN_ODDS and ao > MIN_ODDS,
        "scanned_at":     datetime.now(timezone.utc).isoformat(),
    }

# ============================================================
#   EMAIL
# ============================================================

def send_email(opportunities: list):
    rows = ""
    for o in opportunities:
        ph  = round(STAKE_PER_SIDE * o["home_odds"] - STAKE_PER_SIDE * 2)
        pa  = round(STAKE_PER_SIDE * o["away_odds"] - STAKE_PER_SIDE * 2)
        t   = o["commence_time"][:16].replace("T", " ") if o["commence_time"] else "TBD"
        hbk = o.get("home_bookmaker") or "Best available"
        abk = o.get("away_bookmaker") or "Best available"
        rows += f"""
        <tr style="border-bottom:1px solid #1a2233">
          <td style="padding:14px 10px">
            <strong style="color:#e8edf5">{o['home_team']} vs {o['away_team']}</strong><br>
            <span style="color:#5a6a82;font-size:12px">{o['league'].replace('_',' ').title()} · {t}</span>
          </td>
          <td style="padding:14px 10px;text-align:center">
            <span style="color:#00ff88;font-weight:bold;font-size:16px">{o['home_odds']}x</span><br>
            <span style="color:#5a6a82;font-size:11px">{hbk}</span>
          </td>
          <td style="padding:14px 10px;text-align:center;color:#5a6a82">{o['draw_odds']}x</td>
          <td style="padding:14px 10px;text-align:center">
            <span style="color:#00ff88;font-weight:bold;font-size:16px">{o['away_odds']}x</span><br>
            <span style="color:#5a6a82;font-size:11px">{abk}</span>
          </td>
          <td style="padding:14px 10px;text-align:center;color:#00ff88;font-weight:bold">+${ph:,}</td>
          <td style="padding:14px 10px;text-align:center;color:#00ff88;font-weight:bold">+${pa:,}</td>
        </tr>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;
    padding:20px;background:#080b10;color:#e8edf5">
      <div style="background:linear-gradient(135deg,#00c46a,#00ff88);
      padding:24px;border-radius:12px;margin-bottom:20px">
        <h2 style="color:#080b10;margin:0;font-size:22px">
          🎯 {len(opportunities)} New Opportunit{'y' if len(opportunities)==1 else 'ies'} Found
        </h2>
        <p style="color:rgba(8,11,16,0.7);margin:6px 0 0;font-size:14px">
          Both teams above {MIN_ODDS}x · Stake per side: ${STAKE_PER_SIDE:,} · Only NEW matches shown
        </p>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:14px;
      background:#0d1117;border-radius:10px;overflow:hidden">
        <thead>
          <tr style="background:#111827">
            <th style="padding:12px 10px;text-align:left;color:#5a6a82;font-size:11px;
            text-transform:uppercase;letter-spacing:0.08em">Match</th>
            <th style="padding:12px 10px;color:#5a6a82;font-size:11px;text-transform:uppercase">Home</th>
            <th style="padding:12px 10px;color:#5a6a82;font-size:11px;text-transform:uppercase">Draw</th>
            <th style="padding:12px 10px;color:#5a6a82;font-size:11px;text-transform:uppercase">Away</th>
            <th style="padding:12px 10px;color:#5a6a82;font-size:11px;text-transform:uppercase">If home wins</th>
            <th style="padding:12px 10px;color:#5a6a82;font-size:11px;text-transform:uppercase">If away wins</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="margin-top:16px;font-size:11px;color:#5a6a82;text-align:center">
        Scanned {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} · 
        Only newly discovered opportunities are included in this alert
      </p>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 {len(opportunities)} NEW Odds Opportunit{'y' if len(opportunities)==1 else 'ies'} — Act Now"
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg.attach(MIMEText(html, "html"))

    # Try Gmail API first (PythonAnywhere)
    token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.pickle")
    if os.path.exists(token_path):
        try:
            from googleapiclient.discovery import build
            from google.auth.transport.requests import Request
            with open(token_path, "rb") as f:
                creds = pickle.load(f)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, "wb") as f:
                    pickle.dump(creds, f)
            service = build("gmail", "v1", credentials=creds)
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            log.info("  Email sent via Gmail API")
            return
        except Exception as e:
            log.warning(f"  Gmail API failed, trying SMTP: {e}")

    # Fallback SMTP (GitHub Actions)
    try:
        import smtplib
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        log.info("  Email sent via SMTP")
    except Exception as e:
        log.error(f"  Email failed: {e}")

# ============================================================
#   MAIN SCANNER  —  merges OddsAPI + Stake + Polymarket
# ============================================================

def scan():
    log.info("-" * 50)
    log.info(f"Scan started at {datetime.now().strftime('%H:%M:%S')}")
    all_records   = []
    opportunities = []
    seen          = set()

    for league in LEAGUES:

        # 1 — The Odds API
        for raw in fetch_odds_api(league):
            parsed = parse_odds_api_match(raw, league)
            if not parsed or parsed["match_id"] in seen:
                continue
            seen.add(parsed["match_id"])
            all_records.append(parsed)
            if parsed["is_opportunity"]:
                log.info(f"  OPPORTUNITY -> {parsed['home_team']} vs {parsed['away_team']} "
                         f"({parsed['home_odds']}x / {parsed['away_odds']}x) "
                         f"[{parsed.get('home_bookmaker','')} / {parsed.get('away_bookmaker','')}]")
                is_new = log_opportunity(parsed)
                if is_new:
                    opportunities.append(parsed)
                    log.info(f"    -> NEW — will email")
                else:
                    log.info(f"    -> Already seen — skipping email")

        # 2 — Stake (stub)
        for raw in fetch_stake_odds(league):
            parsed = parse_custom_match(raw, league)
            if not parsed or parsed["match_id"] in seen:
                continue
            seen.add(parsed["match_id"])
            all_records.append(parsed)
            if parsed["is_opportunity"]:
                log.info(f"  OPPORTUNITY -> {parsed['home_team']} vs {parsed['away_team']} [Stake]")
                is_new = log_opportunity(parsed)
                if is_new:
                    opportunities.append(parsed)
                    log.info(f"    -> NEW — will email")
                else:
                    log.info(f"    -> Already seen — skipping email")

        # 3 — Polymarket (stub)
        for raw in fetch_polymarket_odds(league):
            parsed = parse_custom_match(raw, league)
            if not parsed or parsed["match_id"] in seen:
                continue
            seen.add(parsed["match_id"])
            all_records.append(parsed)
            if parsed["is_opportunity"]:
                log.info(f"  OPPORTUNITY -> {parsed['home_team']} vs {parsed['away_team']} [Polymarket]")
                is_new = log_opportunity(parsed)
                if is_new:
                    opportunities.append(parsed)
                    log.info(f"    -> NEW — will email")
                else:
                    log.info(f"    -> Already seen — skipping email")

        time.sleep(1)

    log_to_db(all_records)

    if opportunities:
        send_email(opportunities)
        log.info(f"  {len(opportunities)} NEW opportunit{'y' if len(opportunities)==1 else 'ies'} emailed")
    else:
        log.info("  No new opportunities this scan")

    log.info(f"Scan done — {len(all_records)} matches logged")

def main():
    log.info("=" * 50)
    log.info("Odds Monitor Bot — Starting")
    log.info(f"Leagues: {len(LEAGUES)} | Threshold: >{MIN_ODDS}x | Interval: {SCAN_INTERVAL//60}min")
    log.info("Sources: OddsAPI + Stake (stub) + Polymarket (stub)")
    log.info("=" * 50)
    while True:
        try:
            scan()
        except Exception as e:
            log.error(f"Scan error: {e}")
        log.info(f"Sleeping {SCAN_INTERVAL//60} minutes...")
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        log.info("Single scan mode")
        scan()
    else:
        main()