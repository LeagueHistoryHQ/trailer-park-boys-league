"""
Process cached raw_data/{year}/*.json into the exact data shapes tw-fantasy-league's
index.html expects (DATA, AWARDS_DATA_BY_YEAR, EFFICIENCY_DATA_BY_YEAR, H2H_*, etc).
Writes processed_data.json as an inspectable intermediate before final JS generation.
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw_data"

YEARS = sorted(int(p.name) for p in RAW.iterdir() if p.is_dir() and p.name.isdigit())

POS_NAMES = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
SLOT_GROUP = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 23: "FLEX", 17: "K", 16: "DEF"}
STARTER_SLOTS = {0, 2, 4, 6, 23, 17, 16}  # excludes 20 BENCH, 21 IR
PALETTE = ["#f5b731", "#f472b6", "#ef4444", "#22c55e", "#ec4899", "#14b8a6",
           "#22d3ee", "#3b82f6", "#6366f1", "#a855f7", "#a3e635", "#eab308", "#f97316"]

NFL_TEAMS = {
    0: "FA", 1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA",
    16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI", 22: "ARI", 23: "PIT",
    24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WSH", 29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}


def load(year, name):
    with open(RAW / str(year) / f"{name}.json") as f:
        return json.load(f)


# ---------- manager identity ----------
manager_name_by_guid = {}
for yr in YEARS:
    league = load(yr, "league")
    for m in league.get("members", []):
        guid = m["id"]
        fn, ln = m.get("firstName", "").strip(), m.get("lastName", "").strip()
        name = f"{fn} {ln}".strip() or m.get("displayName", guid)
        manager_name_by_guid[guid] = name  # later years overwrite earlier -> most recent spelling wins

print(f"Managers found: {len(manager_name_by_guid)}")
for g, n in manager_name_by_guid.items():
    print(" ", n)

# ---------- per-season team info ----------
# team_info[year][teamId] = {name, manager, guid, wins, losses, ties, pointsFor, pointsAgainst,
#                              finalRank, playoffSeed}
team_info = {}
settings_by_year = {}
for yr in YEARS:
    league = load(yr, "league")
    settings = league.get("settings", {})
    settings_by_year[yr] = settings
    team_info[yr] = {}
    for t in league.get("teams", []):
        tid = t["id"]
        guid = (t.get("owners") or [None])[0]
        rec = t.get("record", {}).get("overall", {})
        team_info[yr][tid] = {
            "name": t.get("name") or f"Team {tid}",
            "manager": manager_name_by_guid.get(guid, f"Unknown ({guid})"),
            "guid": guid,
            "wins": rec.get("wins", 0),
            "losses": rec.get("losses", 0),
            "ties": rec.get("ties", 0),
            "pointsFor": rec.get("pointsFor", 0.0),
            "pointsAgainst": rec.get("pointsAgainst", 0.0),
            "finalRank": t.get("rankCalculatedFinal", 0),
            "playoffSeed": t.get("playoffSeed", 0),
        }

# ---------- schedule / games ----------
# games[year] = list of {mp, tier, home, away, homePts, awayPts, winner}  (byes excluded)
games_by_year = {}
reg_weeks_by_year = {}
for yr in YEARS:
    sched = load(yr, "schedule")
    reg_weeks = settings_by_year[yr].get("scheduleSettings", {}).get("matchupPeriodCount")
    reg_weeks_by_year[yr] = reg_weeks
    gs = []
    for m in sched.get("schedule", []):
        home, away = m.get("home"), m.get("away")
        if not home or not away:
            continue  # bye
        gs.append({
            "mp": m["matchupPeriodId"],
            "tier": m.get("playoffTierType") or "NONE",
            "home": home["teamId"], "away": away["teamId"],
            "homePts": home.get("totalPoints", 0.0), "awayPts": away.get("totalPoints", 0.0),
            "winner": m.get("winner"),
        })
    games_by_year[yr] = gs

print()
for yr in YEARS:
    print(yr, "games:", len(games_by_year[yr]), "regWeeks:", reg_weeks_by_year[yr])

with open(ROOT / "scripts" / "_stage1.json", "w") as f:
    json.dump({
        "manager_name_by_guid": manager_name_by_guid,
        "team_info": team_info,
        "games_by_year": games_by_year,
        "reg_weeks_by_year": reg_weeks_by_year,
    }, f)
print("\nStage 1 complete -> scripts/_stage1.json")


# ============================================================
# STAGE 2: seasons, records, standings, finishes, H2H
# ============================================================

def manager_of(yr, tid):
    return team_info[yr][tid]["manager"]


def reg_season_standing(yr):
    """Regular-season-only standings (ESPN tiebreak: win% desc, pointsFor desc)."""
    rec = {tid: {"w": 0, "l": 0, "t": 0, "pf": 0.0} for tid in team_info[yr]}
    for g in games_by_year[yr]:
        if g["mp"] > reg_weeks_by_year[yr]:
            continue
        rec[g["home"]]["pf"] += g["homePts"]
        rec[g["away"]]["pf"] += g["awayPts"]
        if g["homePts"] > g["awayPts"]:
            rec[g["home"]]["w"] += 1; rec[g["away"]]["l"] += 1
        elif g["awayPts"] > g["homePts"]:
            rec[g["away"]]["w"] += 1; rec[g["home"]]["l"] += 1
        else:
            rec[g["home"]]["t"] += 1; rec[g["away"]]["t"] += 1
    ranked = sorted(rec.items(), key=lambda kv: (
        -(kv[1]["w"] + 0.5 * kv[1]["t"]) / max(1, kv[1]["w"] + kv[1]["l"] + kv[1]["t"]),
        -kv[1]["pf"]))
    return ranked, rec  # ranked: [(teamId, {w,l,t,pf}), ...] best first


# ---- DATA.seasons ----
seasons = []
for yr in YEARS:
    ranked, regrec = reg_season_standing(yr)
    reg_champ_tid = ranked[0][0]
    points_champ_tid = max(regrec.items(), key=lambda kv: kv[1]["pf"])[0]
    place = {info["finalRank"]: tid for tid, info in team_info[yr].items()}
    seasons.append({
        "year": yr,
        "champion": manager_of(yr, place.get(1)) if place.get(1) else "",
        "second": manager_of(yr, place.get(2)) if place.get(2) else "",
        "third": manager_of(yr, place.get(3)) if place.get(3) else "",
        "regSeasonChamp": manager_of(yr, reg_champ_tid),
        "pointsChamp": manager_of(yr, points_champ_tid),
    })

leagueSizeByYear = {yr: len(team_info[yr]) for yr in YEARS}

# ---- DATA.finishes ----
def result_label(finalRank, playoff_teams, reg_finish):
    if finalRank == 1: return "Champion"
    if finalRank == 2: return "Runner-up"
    if finalRank == 3: return "3rd Place"
    if reg_finish is not None and reg_finish > playoff_teams:
        return "Missed Playoffs"
    ordinal = {4: "4th", 5: "5th", 6: "6th", 7: "7th", 8: "8th", 9: "9th", 10: "10th"}
    return f"{ordinal.get(finalRank, str(finalRank)+'th')} Place"

finishes = defaultdict(list)
for yr in YEARS:
    ranked, _ = reg_season_standing(yr)
    reg_finish_by_tid = {tid: i + 1 for i, (tid, _) in enumerate(ranked)}
    playoff_teams = settings_by_year[yr].get("scheduleSettings", {}).get("playoffTeamCount", 6)
    for tid, info in team_info[yr].items():
        rf = reg_finish_by_tid.get(tid)
        finishes[info["manager"]].append({
            "year": yr, "place": info["finalRank"],
            "result": result_label(info["finalRank"], playoff_teams, rf),
            "regFinish": rf,
            "record": f"{info['wins']}-{info['losses']}" + (f"-{info['ties']}" if info["ties"] else ""),
        })
for mgr in finishes:
    finishes[mgr].sort(key=lambda r: r["year"])

# ---- DATA.standings (career, all-time) ----
career = defaultdict(lambda: {"seasons": 0, "w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0,
                                "trophies": 0, "playoffApps": 0, "playoffWins": 0, "champApps": 0})
for yr in YEARS:
    playoff_teams = settings_by_year[yr].get("scheduleSettings", {}).get("playoffTeamCount", 6)
    for tid, info in team_info[yr].items():
        c = career[info["manager"]]
        c["seasons"] += 1
        c["w"] += info["wins"]; c["l"] += info["losses"]; c["t"] += info["ties"]
        c["pf"] += info["pointsFor"]; c["pa"] += info["pointsAgainst"]
        if info["finalRank"] == 1: c["trophies"] += 1
        if info["finalRank"] in (1, 2): c["champApps"] += 1
        if info["playoffSeed"] and info["playoffSeed"] <= playoff_teams: c["playoffApps"] += 1
    for g in games_by_year[yr]:
        if g["tier"] == "NONE":
            continue
        hw = g["homePts"] > g["awayPts"]
        winner_tid = g["home"] if hw else g["away"] if g["awayPts"] > g["homePts"] else None
        if winner_tid:
            career[manager_of(yr, winner_tid)]["playoffWins"] += 1

standings = []
for mgr, c in career.items():
    gp = c["w"] + c["l"] + c["t"]
    total_weeks = gp  # each game = 1 week
    ppg_val = round(c["pf"] / max(1, gp), 2)
    paG_val = round(c["pa"] / max(1, gp), 2)
    standings.append({
        "team": mgr, "seasons": c["seasons"],
        "record": f"{c['w']}-{c['l']}" + (f"-{c['t']}" if c["t"] else ""),
        "winPct": f"{(c['w'] + 0.5*c['t']) / max(1, gp) * 100:.1f}%",
        "ppg": ppg_val,
        "trophies": c["trophies"],
        "playoffApps": c["playoffApps"], "playoffWins": c["playoffWins"], "champApps": c["champApps"],
        "pointsFor": round(c["pf"], 1), "pointsAgainst": round(c["pa"], 1),
        "paG": paG_val, "diff": round(ppg_val - paG_val, 2),
    })
standings.sort(key=lambda s: -float(s["winPct"].rstrip('%')))

# ---- H2H (regular season + playoffs) ----
def build_h2h(tier_filter):
    pair_rec = defaultdict(lambda: {"winsA": 0, "winsB": 0, "ties": 0})
    pair_games = defaultdict(list)
    for yr in YEARS:
        for g in games_by_year[yr]:
            is_playoff = g["tier"] != "NONE"
            if tier_filter == "playoff" and not is_playoff:
                continue
            if tier_filter == "regular" and is_playoff:
                continue
            m_home, m_away = manager_of(yr, g["home"]), manager_of(yr, g["away"])
            if m_home == m_away:
                continue
            pair = tuple(sorted([m_home, m_away]))
            key = f"{pair[0]}__{pair[1]}"
            a_is_home = (pair[0] == m_home)
            aScore = g["homePts"] if a_is_home else g["awayPts"]
            bScore = g["awayPts"] if a_is_home else g["homePts"]
            pair_games[key].append({"year": yr, "week": g["mp"], "aScore": aScore, "bScore": bScore})
            r = pair_rec[pair]
            if aScore > bScore: r["winsA"] += 1
            elif bScore > aScore: r["winsB"] += 1
            else: r["ties"] += 1
    h2h_list = [{"a": a, "b": b, **r} for (a, b), r in pair_rec.items()]
    for key in pair_games:
        pair_games[key].sort(key=lambda x: (x["year"], x["week"]))
    return h2h_list, dict(pair_games)

H2H_DATA, H2H_GAMES_DATA = build_h2h("regular")
PLAYOFF_H2H_DATA, PLAYOFF_H2H_GAMES_DATA = build_h2h("playoff")

print(f"\nSeasons: {len(seasons)}  Standings rows: {len(standings)}")
print(f"H2H pairs (reg): {len(H2H_DATA)}  H2H pairs (playoff): {len(PLAYOFF_H2H_DATA)}")

with open(ROOT / "scripts" / "_stage2.json", "w") as f:
    json.dump({
        "seasons": seasons, "leagueSizeByYear": leagueSizeByYear,
        "finishes": dict(finishes), "standings": standings,
        "H2H_DATA": H2H_DATA, "H2H_GAMES_DATA": H2H_GAMES_DATA,
        "PLAYOFF_H2H_DATA": PLAYOFF_H2H_DATA, "PLAYOFF_H2H_GAMES_DATA": PLAYOFF_H2H_GAMES_DATA,
    }, f)
print("Stage 2 complete -> scripts/_stage2.json")


# ============================================================
# STAGE 3: records (team game-level + top player performances)
# ============================================================

def fmt_name(full):
    parts = full.split(" ", 1)
    return f"{parts[0][0]}. {parts[1]}" if len(parts) == 2 else full


def top3(items, key):
    """items: list of dicts; returns top-3 as {rank, who, val, meta} entries, val/meta pre-formatted."""
    items = sorted(items, key=key, reverse=True)[:3]
    return items


# ---- team game-level records ----
def game_entry(mgr, pts, yr, wk):
    return {"who": fmt_name(mgr), "pts": pts, "year": yr, "wk": wk}

highest_winning, widest_margin, smallest_margin = [], [], []
highest_combined, lowest_combined = [], []
highest_losing, lowest_losing, lowest_winning = [], [], []

for yr in YEARS:
    for g in games_by_year[yr]:
        hm, am = manager_of(yr, g["home"]), manager_of(yr, g["away"])
        hp, ap = g["homePts"], g["awayPts"]
        if hp == ap:
            continue  # tie, skip win/loss framing
        winner_m, winner_p = (hm, hp) if hp > ap else (am, ap)
        loser_m, loser_p = (am, ap) if hp > ap else (hm, hp)
        margin = abs(hp - ap)
        highest_winning.append(game_entry(winner_m, winner_p, yr, g["mp"]))
        lowest_winning.append(game_entry(winner_m, winner_p, yr, g["mp"]))
        highest_losing.append(game_entry(loser_m, loser_p, yr, g["mp"]))
        lowest_losing.append(game_entry(loser_m, loser_p, yr, g["mp"]))
        widest_margin.append({"who": fmt_name(winner_m), "pts": round(margin, 2), "year": yr, "wk": g["mp"]})
        smallest_margin.append({"who": fmt_name(winner_m), "pts": round(margin, 2), "year": yr, "wk": g["mp"]})
        combined = round(hp + ap, 1)
        matchup_label = f"{fmt_name(hm)} ({hp:.1f}) vs {fmt_name(am)} ({ap:.1f})"
        highest_combined.append({"who": matchup_label, "pts": combined, "year": yr, "wk": g["mp"]})
        lowest_combined.append({"who": matchup_label, "pts": combined, "year": yr, "wk": g["mp"]})

def mk_group(items, reverse, val_suffix=" pts", decimals=1):
    items = sorted(items, key=lambda x: x["pts"], reverse=reverse)[:3]
    entries = []
    for i, it in enumerate(items):
        entries.append({
            "rank": i + 1, "who": it["who"],
            "val": f"{it['pts']:.{decimals}f}{val_suffix}" if isinstance(it["pts"], float) else f"{it['pts']}{val_suffix}",
            "meta": f"Week {it['wk']}, {it['year']}",
        })
    return entries

singleGame = [
    {"title": "Highest Winning Score", "entries": mk_group(highest_winning, True)},
    {"title": "Widest Margin of Victory", "entries": mk_group(widest_margin, True)},
    {"title": "Smallest Margin of Victory", "entries": mk_group(smallest_margin, False, decimals=2)},
    {"title": "Highest Combined Scoring Matchup", "entries": mk_group(highest_combined, True)},
    {"title": "Lowest Combined Scoring Matchup", "entries": mk_group(lowest_combined, False)},
    {"title": "Highest Losing Score", "entries": mk_group(highest_losing, True)},
    {"title": "Lowest Losing Score", "entries": mk_group(lowest_losing, False)},
    {"title": "Lowest Winning Score", "entries": mk_group(lowest_winning, False)},
]

# ---- single-season team records ----
most_points, fewest_points, most_pa, most_wins = [], [], [], []
for yr in YEARS:
    for tid, info in team_info[yr].items():
        mgr = info["manager"]
        most_points.append({"who": fmt_name(mgr), "pts": info["pointsFor"], "year": yr})
        fewest_points.append({"who": fmt_name(mgr), "pts": info["pointsFor"], "year": yr})
        most_pa.append({"who": fmt_name(mgr), "pts": info["pointsAgainst"], "year": yr})
        most_wins.append({"who": fmt_name(mgr), "pts": info["wins"], "year": yr})

def mk_season_group(items, reverse, val_suffix=" pts", is_int=False):
    items = sorted(items, key=lambda x: x["pts"], reverse=reverse)[:3]
    entries = []
    for i, it in enumerate(items):
        val = f"{int(it['pts'])}{val_suffix}" if is_int else f"{it['pts']:.1f}{val_suffix}"
        entries.append({"rank": i + 1, "who": it["who"], "val": val, "meta": str(it["year"])})
    return entries

singleSeason = [
    {"title": "Most Points Scored", "entries": mk_season_group(most_points, True)},
    {"title": "Fewest Points Scored", "entries": mk_season_group(fewest_points, False)},
    {"title": "Most Points Against", "entries": mk_season_group(most_pa, True)},
    {"title": "Most Regular Season Wins", "entries": mk_season_group(most_wins, True, val_suffix="", is_int=True)},
]

with open(ROOT / "scripts" / "_stage3.json", "w") as f:
    json.dump({"singleGame": singleGame, "singleSeason": singleSeason}, f)
print("\nStage 3 (team records) complete -> scripts/_stage3.json")
for grp in singleGame + singleSeason:
    print(" ", grp["title"], "->", grp["entries"][0]["who"], grp["entries"][0]["val"], grp["entries"][0]["meta"])


# ============================================================
# STAGE 4: boxscore pass -> player records, awards, efficiency
# ============================================================

def optimal_points(players, counts):
    """players: list of (pos_group, pts) where pos_group in QB/RB/WR/TE/K/DEF.
       counts: {'QB':n,'RB':n,'WR':n,'TE':n,'FLEX':n,'K':n,'DEF':n} for that season."""
    def top(pos, n):
        vals = sorted([p for g, p in players if g == pos], reverse=True)
        return vals[:n], vals[n:]

    total = 0.0
    qb, _ = top("QB", counts.get("QB", 0)); total += sum(qb)
    k, _ = top("K", counts.get("K", 0)); total += sum(k)
    d, _ = top("DEF", counts.get("DEF", 0)); total += sum(d)

    rb_locked, rb_rest = top("RB", counts.get("RB", 0))
    wr_locked, wr_rest = top("WR", counts.get("WR", 0))
    te_locked, te_rest = top("TE", counts.get("TE", 0))
    total += sum(rb_locked) + sum(wr_locked) + sum(te_locked)
    flex_pool = sorted(rb_rest + wr_rest + te_rest, reverse=True)
    total += sum(flex_pool[:counts.get("FLEX", 0)])
    return round(total, 2)


player_season = {}   # (playerId, year) -> {name, pos, total, games}
player_games = []    # list of {playerId, name, pos, pts, year, wk}
eff_weekly = defaultdict(lambda: defaultdict(lambda: {"actual": 0.0, "optimal": 0.0}))  # eff_weekly[year][teamId]
award_slot_weekly = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))  # [year][POS][teamName][wk] = pts

for yr in YEARS:
    reg_weeks = reg_weeks_by_year[yr]
    slot_counts_raw = settings_by_year[yr].get("rosterSettings", {}).get("lineupSlotCounts", {})
    counts = {}
    for sid, c in slot_counts_raw.items():
        grp = SLOT_GROUP.get(int(sid))
        if grp and c:
            counts[grp] = int(c)
    box_files = sorted((RAW / str(yr)).glob("box_wk*.json"))
    for bf in box_files:
        wk = int(bf.stem.replace("box_wk", ""))
        d = json.load(open(bf))
        for m in d.get("schedule", []):
            if m.get("matchupPeriodId") != wk:
                continue
            for side in ("home", "away"):
                team = m.get(side)
                if not team:
                    continue
                tid = team["teamId"]
                team_name = team_info[yr][tid]["name"]
                roster = team.get("rosterForCurrentScoringPeriod", {}).get("entries", [])
                solver_players = []
                actual_pts = 0.0
                slot_week_totals = defaultdict(float)
                for e in roster:
                    slot = e.get("lineupSlotId")
                    ppe = e.get("playerPoolEntry", {})
                    pts = ppe.get("appliedStatTotal", 0.0) or 0.0
                    player = ppe.get("player", {})
                    pos = POS_NAMES.get(player.get("defaultPositionId"))
                    pos_group = "DEF" if pos == "D/ST" else pos
                    if pos_group:
                        solver_players.append((pos_group, pts))
                    if slot in STARTER_SLOTS:
                        actual_pts += pts
                        grp = SLOT_GROUP.get(slot)
                        if grp:
                            slot_week_totals[grp] += pts
                    # player record tracking (regular season only, matches site convention)
                    if wk <= reg_weeks and pos:
                        pid = player.get("id")
                        name = player.get("fullName", "?")
                        key = (pid, yr)
                        if key not in player_season:
                            player_season[key] = {"name": name, "pos": pos, "total": 0.0, "proTeamId": player.get("proTeamId")}
                        player_season[key]["total"] += pts
                        player_games.append({"name": name, "pos": pos, "pts": pts, "year": yr, "wk": wk})

                if wk <= reg_weeks:
                    eff_weekly[yr][tid]["actual"] += actual_pts
                    eff_weekly[yr][tid]["optimal"] += optimal_points(solver_players, counts)
                    for grp, v in slot_week_totals.items():
                        award_slot_weekly[yr][grp][team_name][wk] = v

with open(ROOT / "scripts" / "_stage4_raw.json", "w") as f:
    json.dump({
        "player_season": {f"{k[0]}|{k[1]}": v for k, v in player_season.items()},
        "player_games": player_games,
        "eff_weekly": {yr: dict(v) for yr, v in eff_weekly.items()},
        "award_slot_weekly": {yr: {grp: dict(teams) for grp, teams in grps.items()} for yr, grps in award_slot_weekly.items()},
    }, f)
print(f"\nStage 4 raw complete. player_season rows: {len(player_season)}  player_games rows: {len(player_games)}")


# ============================================================
# STAGE 5: derive topPlayers records, efficiency, awards
# ============================================================

POSITIONS = ["QB", "RB", "WR", "TE", "K", "D/ST"]

topPlayers = []
for pos in POSITIONS:
    season_rows = [{"who": v["name"], "pts": round(v["total"], 1), "year": yr}
                   for (pid, yr), v in player_season.items() if v["pos"] == pos]
    if not season_rows:
        continue
    entries = sorted(season_rows, key=lambda x: -x["pts"])[:3]
    topPlayers.append({"title": f"{pos} Season Points", "entries": [
        {"rank": i + 1, "who": e["who"], "val": f"{e['pts']:.1f} pts", "meta": str(e["year"])}
        for i, e in enumerate(entries)
    ]})
    game_rows = [g for g in player_games if g["pos"] == pos]
    entries_g = sorted(game_rows, key=lambda x: -x["pts"])[:3]
    topPlayers.append({"title": f"{pos} Single-Game Points", "entries": [
        {"rank": i + 1, "who": e["name"], "val": f"{e['pts']:.1f} pts", "meta": f"Week {e['wk']}, {e['year']}"}
        for i, e in enumerate(entries_g)
    ]})

records = {"singleGame": singleGame, "singleSeason": singleSeason, "topPlayers": topPlayers}

# ---- Manager Efficiency ----
EFFICIENCY_DATA_BY_YEAR = {}
EFFICIENCY_TEAM_TO_MANAGER = {}
for yr in YEARS:
    rows = []
    team_map = {}
    for tid, vals in eff_weekly[yr].items():
        team_name = team_info[yr][tid]["name"]
        actual, optimal = round(vals["actual"], 2), round(vals["optimal"], 2)
        eff = round(actual / optimal * 100, 2) if optimal else 0.0
        rows.append({"team": team_name, "actual": actual, "optimal": optimal, "efficiency": eff})
        team_map[team_name] = team_info[yr][tid]["manager"]
    rows.sort(key=lambda r: -r["efficiency"])
    EFFICIENCY_DATA_BY_YEAR[yr] = rows
    EFFICIENCY_TEAM_TO_MANAGER[yr] = team_map

# ---- Awards ----
AWARD_CATEGORY_KEYS = ["trueTotal", "QB", "RB", "WR", "TE", "FLEX", "K", "DEF"]
AWARDS_DATA_BY_YEAR = {}
AWARD_TEAM_COLORS_BY_YEAR = {}
AWARD_POSITION_WEEKLY_BY_YEAR = {}

for yr in YEARS:
    reg_weeks = reg_weeks_by_year[yr]
    team_ids_sorted = sorted(team_info[yr].keys())
    team_names_ordered = [team_info[yr][tid]["name"] for tid in team_ids_sorted]
    AWARD_TEAM_COLORS_BY_YEAR[yr] = {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(team_names_ordered)}

    # trueTotal: season total actual points per team, + weekly cumulative
    weekly_true = defaultdict(dict)
    for g in games_by_year[yr]:
        if g["mp"] > reg_weeks:
            continue
        weekly_true[team_info[yr][g["home"]]["name"]][g["mp"]] = g["homePts"]
        weekly_true[team_info[yr][g["away"]]["name"]][g["mp"]] = g["awayPts"]

    trueTotal_list = []
    weeklyCumulative = {}
    for name in team_names_ordered:
        wk_pts = weekly_true.get(name, {})
        total = sum(wk_pts.values())
        trueTotal_list.append({"team": name, "value": round(total, 1)})
        cum, run = [], 0.0
        for wk in range(1, reg_weeks + 1):
            run += wk_pts.get(wk, 0.0)
            cum.append(round(run, 1))
        weeklyCumulative[name] = cum
    trueTotal_list.sort(key=lambda x: -x["value"])

    year_awards = {"trueTotal": trueTotal_list, "weeklyCumulative": weeklyCumulative}
    year_pos_weekly = {}
    for grp in ["QB", "RB", "WR", "TE", "FLEX", "K", "DEF"]:
        team_wk = award_slot_weekly.get(yr, {}).get(grp, {})
        totals = []
        cum_by_team = {}
        for name in team_names_ordered:
            wk_map = team_wk.get(name, {})
            total = sum(wk_map.values())
            totals.append({"team": name, "value": round(total, 1)})
            cum, run = [], 0.0
            for wk in range(1, reg_weeks + 1):
                run += wk_map.get(wk, 0.0)
                cum.append(round(run, 1))
            cum_by_team[name] = cum
        totals.sort(key=lambda x: -x["value"])
        year_awards[grp] = totals
        year_pos_weekly[grp] = cum_by_team

    AWARDS_DATA_BY_YEAR[yr] = year_awards
    AWARD_POSITION_WEEKLY_BY_YEAR[yr] = year_pos_weekly

with open(ROOT / "scripts" / "_stage5.json", "w") as f:
    json.dump({
        "records": records,
        "EFFICIENCY_DATA_BY_YEAR": EFFICIENCY_DATA_BY_YEAR,
        "EFFICIENCY_TEAM_TO_MANAGER": EFFICIENCY_TEAM_TO_MANAGER,
        "AWARDS_DATA_BY_YEAR": AWARDS_DATA_BY_YEAR,
        "AWARD_TEAM_COLORS_BY_YEAR": AWARD_TEAM_COLORS_BY_YEAR,
        "AWARD_POSITION_WEEKLY_BY_YEAR": AWARD_POSITION_WEEKLY_BY_YEAR,
    }, f)
print(f"\nStage 5 complete -> scripts/_stage5.json")
print("topPlayers categories:", len(topPlayers))
print("Sample efficiency 2025:", EFFICIENCY_DATA_BY_YEAR[2025][:3])


# ============================================================
# STAGE 6: draft data (DRAFTS_DATA + DRAFT_VALUE_DATA)
#
# Keepers are drafted picks like any other (ESPN assigns them a real
# round/pick slot, just marked keeper=true) -- ranking picks by draft
# order and computing value the same way for everyone naturally folds
# keepers into the metrics, per the client's request.
#
# value formula (reverse-engineered from tw-fantasy-league's own real
# data, confirmed exact on 6/6 spot checks): for a pick with draftRank N
# at a position, value = thisPlayer'sSeasonPoints - (season points of
# whichever player actually finished ranked Nth at that position that
# year). I.e. "how many more/fewer points did you get than what the
# Nth-best finisher at that position produced" -- a direct measure of
# whether your draft slot (regardless of live-pick or keeper cost) paid off.
# ============================================================

DRAFTS_DATA = {}
DRAFT_VALUE_DATA = {}
missing_player_count = 0
pick_records_by_year = {}  # yr -> [{pid, name, pos, team, isKeeper, round, roundPick, points, seasonRank, draftRank, value}]

for yr in YEARS:
    draft_raw = json.load(open(RAW / str(yr) / "draft.json"))
    picks = draft_raw.get("draftDetail", {}).get("picks", [])
    if not picks:
        continue

    # full points-ranked list per position for this year (for seasonRank + value lookups)
    pos_ranked = defaultdict(list)  # pos -> [(points, playerId), ...] desc
    for (pid, y), v in player_season.items():
        if y == yr:
            pos_ranked[v["pos"]].append((v["total"], pid))
    for pos in pos_ranked:
        pos_ranked[pos].sort(key=lambda t: -t[0])
    # playerId -> seasonRank (1-based) per position
    season_rank_by_player = {}
    points_at_rank = {}  # pos -> {rank: points}
    for pos, lst in pos_ranked.items():
        points_at_rank[pos] = {}
        for i, (pts, pid) in enumerate(lst):
            season_rank_by_player[(pos, pid)] = i + 1
            points_at_rank[pos][i + 1] = pts

    # sort all picks by overall draft order, then assign per-position draftRank
    picks_sorted = sorted(picks, key=lambda p: (p.get("roundId", 0), p.get("roundPickNumber", 0)))
    pos_draft_counter = defaultdict(int)
    year_picks = []
    drafted_lookup = {}  # (pos, playerId) -> (draftRank, value)
    year_pick_records = []
    for p in picks_sorted:
        pid = p.get("playerId")
        info = player_season.get((pid, yr))
        if info is None:
            missing_player_count += 1
            continue  # never appeared in any boxscore this season (e.g. drafted, instantly dropped) -- skip
        pos = info["pos"]
        pos_draft_counter[pos] += 1
        draft_rank = pos_draft_counter[pos]
        pts = round(info["total"], 2)
        season_rank = season_rank_by_player.get((pos, pid))
        expected_pts = points_at_rank.get(pos, {}).get(draft_rank)
        value = round(pts - expected_pts, 2) if expected_pts is not None else None
        team_name = team_info[yr][p["teamId"]]["name"]
        pro_team = NFL_TEAMS.get(info.get("proTeamId"), "")
        year_picks.append([
            p.get("roundId"), p.get("roundPickNumber"), team_name, info["name"], pos, pro_team,
            pts, season_rank, draft_rank, value,
        ])
        drafted_lookup[(pos, pid)] = (draft_rank, value)
        year_pick_records.append({
            "pid": pid, "year": yr, "name": info["name"], "pos": pos, "team": team_name,
            "manager": team_info[yr][p["teamId"]]["manager"],
            "isKeeper": bool(p.get("keeper")), "round": p.get("roundId"), "roundPick": p.get("roundPickNumber"),
            "points": pts, "seasonRank": season_rank, "draftRank": draft_rank, "value": value,
        })

    DRAFTS_DATA[yr] = year_picks
    pick_records_by_year[yr] = year_pick_records

    # DRAFT_VALUE_DATA: top 10 by season points per position, draftRank/value null if not drafted
    dv_year = {}
    for pos, lst in pos_ranked.items():
        top10 = []
        for pts, pid in lst[:10]:
            name = player_season[(pid, yr)]["name"]
            dr, val = drafted_lookup.get((pos, pid), (None, None))
            top10.append({"player": name, "points": round(pts, 2), "seasonRank": season_rank_by_player[(pos, pid)],
                          "draftRank": dr, "value": val})
        dv_year[pos] = top10
    DRAFT_VALUE_DATA[yr] = dv_year

    print(f"{yr}: {len(year_picks)} picks processed ({len(picks) - len(year_picks)} skipped, no stats)")

print(f"\nStage 6 complete. Total picks skipped for missing stats: {missing_player_count}")

with open(ROOT / "scripts" / "_stage6.json", "w") as f:
    json.dump({"DRAFTS_DATA": DRAFTS_DATA, "DRAFT_VALUE_DATA": DRAFT_VALUE_DATA}, f)
print("Sample 2025 QB draft value:", json.dumps(DRAFT_VALUE_DATA.get(2025, {}).get("QB", [])[:3], indent=1))


# ============================================================
# STAGE 7: keeper chains -- trace each player's keeper tenure across
# consecutive years (a chain continues across a team change too, since
# keeper rights can move via trade; it resets only when the player goes
# back into a LIVE draft) and sum each season's already-computed value
# across the whole run. Per the client: keeper picks should be judged
# on cumulative return over their kept lifespan, not one season alone.
# ============================================================

active = {}       # pid -> open chain dict
finished_chains = []

for yr in YEARS:  # YEARS is sorted ascending
    records = pick_records_by_year.get(yr, [])
    picked_pids_this_year = set()
    for rec in records:
        pid = rec["pid"]
        picked_pids_this_year.add(pid)
        if rec["isKeeper"] and pid in active and active[pid]["lastYear"] == yr - 1:
            chain = active[pid]
            chain["seasons"].append(rec)
            chain["lastYear"] = yr
        else:
            if pid in active:
                finished_chains.append(active[pid])
            active[pid] = {
                "pid": pid, "name": rec["name"], "pos": rec["pos"],
                "originYear": yr, "lastYear": yr,
                "leftCensored": rec["isKeeper"] and yr == YEARS[0],
                "seasons": [rec],
            }
    for pid in list(active.keys()):
        if pid not in picked_pids_this_year:
            finished_chains.append(active.pop(pid))
finished_chains.extend(active.values())  # still ongoing as of the latest season

# only real keeper stories: at least one actual kept year, more than one season tracked
keeper_chains = [c for c in finished_chains if len(c["seasons"]) > 1 and any(s["isKeeper"] for s in c["seasons"])]

KEEPER_CHAINS_DATA = []
for c in keeper_chains:
    seasons = c["seasons"]
    cum_value = round(sum(s["value"] for s in seasons if s["value"] is not None), 2)
    cum_points = round(sum(s["points"] for s in seasons), 2)
    years_kept = sum(1 for s in seasons if s["isKeeper"])
    KEEPER_CHAINS_DATA.append({
        "player": c["name"], "pos": c["pos"],
        "team": seasons[-1]["team"], "manager": seasons[-1]["manager"],
        "originRound": seasons[0]["round"], "originRoundPick": seasons[0]["roundPick"],
        "originDraftRank": seasons[0]["draftRank"], "startYear": c["originYear"], "endYear": c["lastYear"],
        "totalSeasons": len(seasons), "yearsKept": years_kept,
        "totalPoints": cum_points, "cumulativeValue": cum_value,
        "leftCensored": c["leftCensored"],
        "seasonDetail": [
            {"year": s["year"], "team": s["team"], "round": s["round"], "roundPick": s["roundPick"],
             "draftRank": s["draftRank"], "isKeeper": s["isKeeper"], "points": s["points"],
             "seasonRank": s["seasonRank"], "value": s["value"]}
            for s in seasons
        ],
    })

KEEPER_CHAINS_DATA.sort(key=lambda k: -k["cumulativeValue"])

with open(ROOT / "scripts" / "_stage7.json", "w") as f:
    json.dump({"KEEPER_CHAINS_DATA": KEEPER_CHAINS_DATA}, f)

print(f"\nStage 7 complete. {len(KEEPER_CHAINS_DATA)} keeper chains found.")
print("Top 5 by cumulative value:")
for k in KEEPER_CHAINS_DATA[:5]:
    print(f"  {k['player']} ({k['pos']}) {k['startYear']}-{k['endYear']}, {k['yearsKept']} yrs kept, "
          f"orig R{k['originRound']}, cum value {k['cumulativeValue']:+.2f}, cum pts {k['totalPoints']:.1f}")
print("Bottom 5 (worst):")
for k in KEEPER_CHAINS_DATA[-5:]:
    print(f"  {k['player']} ({k['pos']}) {k['startYear']}-{k['endYear']}, {k['yearsKept']} yrs kept, "
          f"orig R{k['originRound']}, cum value {k['cumulativeValue']:+.2f}, cum pts {k['totalPoints']:.1f}")
