"""
Pull raw ESPN Fantasy Football data for the Trailer Park Boys league (67334441)
across all available seasons and cache it locally as JSON. Run once (or per-season
as needed); downstream processing reads only from raw_data/, never re-hits the API.
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw_data"


def load_env():
    env = {}
    with open(ROOT / ".env") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k] = v
    return env


ENV = load_env()
LEAGUE_ID = ENV["LEAGUE_ID"]
COOKIES_HEADER = f"espn_s2={ENV['ESPN_S2']}; SWID={ENV['ESPN_SWID']}"
BASE = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{{year}}/segments/0/leagues/{LEAGUE_ID}"

SESSION = requests.Session()
SESSION.headers.update({"Cookie": COOKIES_HEADER, "User-Agent": "Mozilla/5.0"})


def get(year, views, **params):
    url = BASE.format(year=year)
    q = [("view", v) for v in views] + list(params.items())
    r = SESSION.get(url, params=q, timeout=30)
    r.raise_for_status()
    return r.json()


def save(year, name, data):
    d = RAW_DIR / str(year)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{name}.json", "w") as f:
        json.dump(data, f)


def already_have(year, name):
    return (RAW_DIR / str(year) / f"{name}.json").exists()


def pull_season(year, force=False):
    print(f"=== {year} ===")

    # 1. League settings + teams + members
    if force or not already_have(year, "league"):
        d = get(year, ["mTeam", "mSettings", "mStandings"])
        save(year, "league", d)
        print(f"  league: {len(d.get('teams', []))} teams")
    else:
        d = json.load(open(RAW_DIR / str(year) / "league.json"))
        print(f"  league: cached ({len(d.get('teams', []))} teams)")

    settings = d.get("settings", {})
    reg_season_weeks = settings.get("scheduleSettings", {}).get("matchupPeriodCount")
    final_period = d.get("status", {}).get("finalScoringPeriod") or d.get("status", {}).get("latestScoringPeriod")
    total_weeks = final_period or reg_season_weeks
    print(f"  reg_season_weeks={reg_season_weeks} final_period={final_period}")

    # 2. Draft results (picks, rounds, keeper flags)
    if force or not already_have(year, "draft"):
        draft = get(year, ["mDraftDetail"])
        npicks = len(draft.get("draftDetail", {}).get("picks", []))
        save(year, "draft", draft)
        print(f"  draft: {npicks} picks")
    else:
        print("  draft: cached")

    # 3. Full schedule with playoff bracket info
    if force or not already_have(year, "schedule"):
        sched = get(year, ["mMatchupScore", "mScoreboard"])
        save(year, "schedule", sched)
        print(f"  schedule: {len(sched.get('schedule', []))} matchup entries")
    else:
        print("  schedule: cached")

    # 4. Weekly boxscores (roster + lineup slot + points per player, per team, per week)
    if not total_weeks:
        print("  WARNING: could not determine total_weeks, skipping boxscores")
        return
    for wk in range(1, total_weeks + 1):
        if force or not already_have(year, f"box_wk{wk:02d}"):
            try:
                box = get(year, ["mBoxscore"], scoringPeriodId=wk)
                save(year, f"box_wk{wk:02d}", box)
                n = len(box.get("schedule", []))
                print(f"  week {wk}: {n} matchups")
            except requests.HTTPError as e:
                print(f"  week {wk}: ERROR {e}")
            time.sleep(0.15)
        else:
            pass  # already cached, skip silently


if __name__ == "__main__":
    years = [int(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else list(range(2019, 2026))
    for y in years:
        pull_season(y)
    print("Done.")
