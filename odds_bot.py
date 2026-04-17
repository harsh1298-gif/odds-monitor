"""
============================================================
  ODDS MONITOR BOT  —  odds_bot.py
  Runs 24/7, scans odds every hour, logs to Supabase,
  sends email alerts when both teams > 2x

  Integrated sources:
    - The Odds API (Bet365, 1xBet, etc.)
    - Stake (custom fetcher)
    - Polymarket (custom fetcher)
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

ODDS_API_KEY   = os.getenv("ODDS_API_KEY",   "YOUR_ODDS_API_KEY")
SUPABASE_URL   = os.getenv("SUPABASE_URL",   "YOUR_SUPABASE_URL")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY",   "YOUR_SUPABASE_KEY")
EMAIL_SENDER   = os.getenv("EMAIL_SENDER",   "youremail@gmail.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "your_app_password")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER", "youremail@gmail.com")

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
    """Returns True if this is a NEW opportunity (not seen before)"""
    profit_home = round(STAKE_PER_SIDE * match["home_odds"] - STAKE_PER_SIDE * 2)
    profit_away = round(STAKE_PER_SIDE * match["away_odds"] - STAKE_PER_SIDE * 2)
    try:
        # First check if this match_id already exists
        check = requests.get(
            f"{SUPABASE_URL}/rest/v1/opportunities?match_id=eq.{match['match_id']}&select=match_id",
            headers=supabase_headers(),
            timeout=10,
        )
        already_exists = len(check.json()) > 0 if check.status_code == 200 else False

        if not already_exists:
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
                    "profit_if_home_wins": profit_home,
                    "profit_if_away_wins": profit_away,
                    "loss_if_draw":        -(STAKE_PER_SIDE * 2),
                    "spotted_at":          match["scanned_at"],
                },
                timeout=15,
            )
            return True  # NEW — should be emailed
        else:
            return False  # Already seen — skip email

    except Exception as e:
        log.error(f"  Opportunity log failed: {e}")
        return False

# ============================================================
#   ODDS FETCHING — The Odds API
# ============================================================

def fetch_odds_api(league: str) -> list:
    """Fetch odds from The Odds API for a given league."""
    url = f"https://api.the-odds-api.com/v4/sports/{league}/odds"
    params = {
        "apiKey":      ODDS_API_KEY,
        "regions":     "eu",
        "markets":     "h2h",
        "oddsFormat":  "decimal",
        "dateFormat":  "iso",
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
    """Parse a single match from The Odds API, extracting best odds and bookmaker names."""
    home = raw.get("home_team")
    away = raw.get("away_team")
    commence = raw.get("commence_time", "")

    best = {
        "home": 0.0,
        "draw": 0.0,
        "away": 0.0,
        "home_bookmaker": None,
        "away_bookmaker": None,
    }

    for bk in raw.get("bookmakers", []):
        bookmaker_name = bk.get("title")
        for mkt in bk.get("markets", []):
            if mkt.get("key") != "h2h":
                continue
            for o in mkt.get("outcomes", []):
                name = o.get("name")
                price = o.get("price", 0)
                if name == home and price > best["home"]:
                    best["home"] = price
                    best["home_bookmaker"] = bookmaker_name
                elif name == away and price > best["away"]:
                    best["away"] = price
                    best["away_bookmaker"] = bookmaker_name
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
#   CUSTOM FETCHER — Stake
#   (Placeholder – implement API or web scraping)
# ============================================================

# Mapping from our internal league keys to whatever Stake uses
STAKE_LEAGUE_MAP = {
    "soccer_epl":                "england-premier-league",
    "soccer_uefa_champs_league": "champions-league",
    "soccer_spain_la_liga":      "spain-la-liga",
    "soccer_germany_bundesliga": "germany-bundesliga",
    "soccer_italy_serie_a":      "italy-serie-a",
    "soccer_france_ligue_one":   "france-ligue-1",
}

def fetch_stake_odds(league: str) -> list:
    """
    Fetch match odds from Stake.com for a given league.
    Returns a list of dicts in a format compatible with parse_custom_match().
    """
    # TODO: Implement actual Stake API or web scraping.
    # Expected return format per match:
    # {
    #     "home_team": "Manchester City",
    #     "away_team": "Arsenal",
    #     "commence_time": "2026-04-20T15:00:00Z",
    #     "home_odds": 2.15,
    #     "away_odds": 3.10,
    #     "draw_odds": 3.50,
    #     "source": "Stake"
    # }
    log.info(f"  [Stake] {league}: (stub) no data fetched")
    return []

def parse_custom_match(match: dict, league: str) -> dict | None:
    """
    Parse a match dict from custom fetchers (Stake/Polymarket) into our standard format.
    Expects match dict to already contain home_odds, away_odds, draw_odds, and source.
    """
    home = match.get("home_team")
    away = match.get("away_team")
    if not home or not away:
        return None

    home_odds = match.get("home_odds", 0)
    away_odds = match.get("away_odds", 0)
    draw_odds = match.get("draw_odds", 0)
    source = match.get("source", "Custom")

    return {
        "match_id":       f"{home}vs{away}".replace(" ", "_"),
        "home_team":      home,
        "away_team":      away,
        "league":         league,
        "commence_time":  match.get("commence_time", ""),
        "home_odds":      round(home_odds, 2),
        "away_odds":      round(away_odds, 2),
        "draw_odds":      round(draw_odds, 2),
        "home_bookmaker": source,
        "away_bookmaker": source,
        "is_opportunity": home_odds > MIN_ODDS and away_odds > MIN_ODDS,
        "scanned_at":     datetime.now(timezone.utc).isoformat(),
    }

# ============================================================
#   CUSTOM FETCHER — Polymarket
#   (Placeholder – implement API or web scraping)
# ============================================================

# Polymarket uses event-based markets; we need to map to our leagues
POLYMARKET_LEAGUE_MAP = {
    "soccer_epl":                "EPL",
    "soccer_uefa_champs_league": "UCL",
    # ...
}

def fetch_polymarket_odds(league: str) -> list:
    """
    Fetch odds from Polymarket for a given league.
    Returns a list of dicts in the same format as Stake fetcher.
    """
    # TODO: Implement Polymarket API or scraping.
    # Polymarket odds are binary (yes/no). You'll need to convert to three‑way odds.
    log.info(f"  [Polymarket] {league}: (stub) no data fetched")
    return []

# ============================================================
#   EMAIL — SMTP (GitHub Actions) with Gmail API fallback
# ============================================================

def send_email(opportunities: list):
    rows = ""
    for o in opportunities:
        ph = round(STAKE_PER_SIDE * o["home_odds"] - STAKE_PER_SIDE * 2)
        pa = round(STAKE_PER_SIDE * o["away_odds"] - STAKE_PER_SIDE * 2)
        t  = o["commence_time"][:16].replace("T", " ") if o["commence_time"] else "TBD"
        rows += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:12px 8px">
            <strong>{o['home_team']} vs {o['away_team']}</strong><br>
            <span style="color:#888;font-size:12px">{o['league'].replace('_',' ').title()} · {t}</span>
          </td>
          <td style="padding:12px 8px;text-align:center;color:#1D9E75;font-weight:bold">{o['home_odds']}x</td>
          <td style="padding:12px 8px;text-align:center;color:#888">{o['draw_odds']}x</td>
          <td style="padding:12px 8px;text-align:center;color:#1D9E75;font-weight:bold">{o['away_odds']}x</td>
          <td style="padding:12px 8px;text-align:center;color:#1D9E75">+${ph:,}</td>
          <td style="padding:12px 8px;text-align:center;color:#1D9E75">+${pa:,}</td>
        </tr>"""

    html = f"""<html><body style="font-family:Arial,sans-serif;max-width:680px;margin:0 auto;padding:20px">
      <div style="background:#1D9E75;padding:20px;border-radius:10px;margin-bottom:20px">
        <h2 style="color:white;margin:0">Odds Alert - {len(opportunities)} Opportunit{'y' if len(opportunities)==1 else 'ies'}</h2>
        <p style="color:rgba(255,255,255,0.8);margin:6px 0 0">Both teams above {MIN_ODDS}x - Stake per side: ${STAKE_PER_SIDE:,}</p>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:14px">
        <thead><tr style="background:#f5f5f5">
          <th style="padding:10px 8px;text-align:left">Match</th>
          <th style="padding:10px 8px">Home</th>
          <th style="padding:10px 8px">Draw</th>
          <th style="padding:10px 8px">Away</th>
          <th style="padding:10px 8px">If home wins</th>
          <th style="padding:10px 8px">If away wins</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="margin-top:20px;font-size:12px;color:#aaa">Scanned {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Odds Alert: {len(opportunities)} opportunit{'y' if len(opportunities)==1 else 'ies'} found!"
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
#   UNIFIED SCANNER (merges all sources)
# ============================================================

def scan():
    log.info("-" * 50)
    log.info(f"Scan started at {datetime.now().strftime('%H:%M:%S')}")
    all_records   = []
    opportunities = []
    seen          = set()

    for league in LEAGUES:
        # 1. Fetch from The Odds API
        for raw in fetch_odds_api(league):
            parsed = parse_odds_api_match(raw, league)
            if not parsed or parsed["match_id"] in seen:
                continue
            seen.add(parsed["match_id"])
            all_records.append(parsed)
            if parsed["is_opportunity"]:
               log.info(f"  OPPORTUNITY -> {parsed['home_team']} vs {parsed['away_team']} "
             f"({parsed['home_odds']}x / {parsed['away_odds']}x)")
    is_new = log_opportunity(parsed)
    if is_new:
        opportunities.append(parsed)
        log.info(f"    -> NEW opportunity, will email")
    else:
        log.info(f"    -> Already seen, skipping email")

        # 2. Fetch from Stake
        for raw in fetch_stake_odds(league):
            parsed = parse_custom_match(raw, league)
            if not parsed or parsed["match_id"] in seen:
                continue
            seen.add(parsed["match_id"])
            all_records.append(parsed)
            if parsed["is_opportunity"]:
                log.info(f"  OPPORTUNITY -> {parsed['home_team']} vs {parsed['away_team']} "
                         f"({parsed['home_odds']}x / {parsed['away_odds']}x) [Stake]")
                opportunities.append(parsed)
                log_opportunity(parsed)

        # 3. Fetch from Polymarket
        for raw in fetch_polymarket_odds(league):
            parsed = parse_custom_match(raw, league)
            if not parsed or parsed["match_id"] in seen:
                continue
            seen.add(parsed["match_id"])
            all_records.append(parsed)
            if parsed["is_opportunity"]:
                log.info(f"  OPPORTUNITY -> {parsed['home_team']} vs {parsed['away_team']} "
                         f"({parsed['home_odds']}x / {parsed['away_odds']}x) [Polymarket]")
                opportunities.append(parsed)
                log_opportunity(parsed)

        time.sleep(1)   # Be gentle to sources

    log_to_db(all_records)

    if opportunities:
        send_email(opportunities)
        log.info(f"  {len(opportunities)} opportunit{'y' if len(opportunities)==1 else 'ies'} found and emailed")
    else:
        log.info("  No opportunities this scan")

    log.info(f"Scan done - {len(all_records)} matches logged")

def main():
    log.info("=" * 50)
    log.info("Odds Monitor Bot - Starting")
    log.info(f"Leagues: {len(LEAGUES)} | Threshold: >{MIN_ODDS}x | Interval: {SCAN_INTERVAL//60}min")
    log.info("Sources: OddsAPI + Stake + Polymarket (custom fetchers)")
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