"""
Assemble the final index.html for the client site: take tw-fantasy-league/index.html
as a template (CSS + render functions reused verbatim), swap in the client's real data
and branding, and add a safe empty-state guard for Draft Value (no draft/keeper data yet).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path("/Users/tuckerwatts/Documents/TW/Fantasy Football/tw-fantasy-league/index.html")

s1 = json.load(open(ROOT / "scripts" / "_stage1.json"))
s2 = json.load(open(ROOT / "scripts" / "_stage2.json"))
s5 = json.load(open(ROOT / "scripts" / "_stage5.json"))
s6 = json.load(open(ROOT / "scripts" / "_stage6.json"))
s7 = json.load(open(ROOT / "scripts" / "_stage7.json"))

DATA = {
    "leagueSizeByYear": s2["leagueSizeByYear"],
    "seasons": s2["seasons"],
    "records": s5["records"],
    "standings": s2["standings"],
    "finishes": s2["finishes"],
}

AWARD_CATEGORIES = [
    {"key": "trueTotal", "title": "True Total Points Award", "desc": "Awarded to the manager who scored the most total points during the season (includes total BYE weeks).", "cumulative": True},
    {"key": "QB", "title": "Best QB Points", "desc": "Awarded to the manager whose starting QB(s) scored the most total points during the season."},
    {"key": "RB", "title": "Best RB Points", "desc": "Awarded to the manager whose starting RB(s) scored the most total points during the season."},
    {"key": "WR", "title": "Best WR Points", "desc": "Awarded to the manager whose starting WR(s) scored the most total points during the season."},
    {"key": "TE", "title": "Best TE Points", "desc": "Awarded to the manager whose starting TE scored the most total points during the season."},
    {"key": "FLEX", "title": "Best FLEX Points", "desc": "Awarded to the manager whose FLEX starter(s) scored the most total points during the season."},
    {"key": "K", "title": "Best K Points", "desc": "Awarded to the manager whose starting K scored the most total points during the season."},
    {"key": "DEF", "title": "Best DEF Points", "desc": "Awarded to the manager whose starting D/ST scored the most total points during the season."},
]

def j(obj):
    return json.dumps(obj, separators=(",", ":"))

years_sorted_desc = sorted(s2["leagueSizeByYear"].keys(), key=lambda y: -int(y))
years_all_time_js = j(sorted(s2["leagueSizeByYear"].keys(), key=lambda y: int(y)))

data_block = f"""const DATA = {j(DATA)};

const AWARDS_DATA_BY_YEAR = {j(s5["AWARDS_DATA_BY_YEAR"])};

const AWARD_CATEGORIES = {j(AWARD_CATEGORIES)};

const AWARD_TEAM_COLORS_BY_YEAR = {j(s5["AWARD_TEAM_COLORS_BY_YEAR"])};

const AWARD_POSITION_WEEKLY_BY_YEAR = {j(s5["AWARD_POSITION_WEEKLY_BY_YEAR"])};

const DRAFTS_DATA = {j(s6["DRAFTS_DATA"])};

const DRAFT_VALUE_DATA = {j(s6["DRAFT_VALUE_DATA"])};

const H2H_DATA = {j(s2["H2H_DATA"])};
const PLAYOFF_H2H_DATA = {j(s2["PLAYOFF_H2H_DATA"])};
const H2H_GAMES_DATA = {j(s2["H2H_GAMES_DATA"])};
const PLAYOFF_H2H_GAMES_DATA = {j(s2["PLAYOFF_H2H_GAMES_DATA"])};

const EFFICIENCY_DATA_BY_YEAR = {j(s5["EFFICIENCY_DATA_BY_YEAR"])};

const EFFICIENCY_TEAM_TO_MANAGER = {j(s5["EFFICIENCY_TEAM_TO_MANAGER"])};

const KEEPER_CHAINS_DATA = {j(s7["KEEPER_CHAINS_DATA"])};"""

html = TEMPLATE.read_text()
lines = html.split("\n")

# ---- splice out the old data block (line 975 "const DATA = " through line 1266 "};") ----
start_idx = next(i for i, l in enumerate(lines) if l.startswith("const DATA = "))
end_idx = next(i for i in range(start_idx, len(lines)) if lines[i].strip() == "};" and i > 1260 - 5)
# find precisely: the line index (0-based) that is the closing of EFFICIENCY_TEAM_TO_MANAGER (originally line 1266)
assert lines[start_idx].startswith("const DATA = "), lines[start_idx][:50]
# search forward for the EFFICIENCY_TEAM_TO_MANAGER const start, then its matching closing "};"
eff_start = next(i for i in range(start_idx, len(lines)) if lines[i].startswith("const EFFICIENCY_TEAM_TO_MANAGER"))
eff_end = next(i for i in range(eff_start, len(lines)) if lines[i].strip() == "};")
print(f"Splicing lines {start_idx+1}-{eff_end+1} (1-indexed)")
print("  first line:", lines[start_idx][:60])
print("  last line:", lines[eff_end])

new_lines = lines[:start_idx] + [data_block] + lines[eff_end + 1:]
html = "\n".join(new_lines)

# ---- branding swaps ----
html = html.replace(
    "<title>TW Fantasy League</title>",
    "<title>Trailer Park Boys Fantasy League</title>",
)
html = html.replace(
    '<meta name="description" content="TW Fantasy Football League — Champions, Records, History, and Standings" />',
    '<meta name="description" content="The Trailer Park Boys Fantasy League — Champions, Records, History, and Standings" />',
)
html = html.replace(
    '<img class="brand-logo-img" src="images/tw_logo_header.png" alt="TW Fantasy Football League logo">',
    '<div class="brand-logo-text">The Trailer Park Boys</div>',
)
html = html.replace(
    "© 2026 TW Fantasy League — ESPN Fantasy Football · Data through the 2025 season",
    "© 2026 The Trailer Park Boys Fantasy League — ESPN Fantasy Football · Data through the 2025 season",
)
html = html.replace(">EST. 2022<", ">EST. 2019<")
html = html.replace(
    "All-time regular season record vs. every opponent faced, 2022–2025.",
    "All-time regular season record vs. every opponent faced, 2019–2025.",
)
html = html.replace(
    "All-time playoff bracket record vs. every opponent faced, 2022–2025.",
    "All-time playoff bracket record vs. every opponent faced, 2019–2025.",
)
html = html.replace(
    "${instance.label} matchup history, 2022–2025 &middot;",
    "${instance.label} matchup history, 2019–2025 &middot;",
)
html = html.replace(
    "const AWARDS_ALL_TIME_YEARS = ['2022', '2023', '2024', '2025'];",
    f"const AWARDS_ALL_TIME_YEARS = {years_all_time_js};",
)
html = html.replace(
    "Regular season only. Actual points scored vs. the most optimal lineup possible each week (best available QB/RB/RB/WR/WR/TE/FLEX/K/D-ST), expressed as a percentage.",
    "Regular season only. Actual points scored vs. the most optimal lineup possible each week, using that season&rsquo;s actual starting-lineup requirements (roster rules have changed year to year in this league), expressed as a percentage.",
)

# simple text-logo style (no image asset available yet) + Keeper Picks "Kept" column
html = html.replace(
    "</style>\n</head>",
    "  .brand-logo-text { font-family: Inter, ui-sans-serif, system-ui; font-weight: 900; font-size: 17px; "
    "color: var(--gold); letter-spacing: -0.01em; white-space: nowrap; }\n"
    "  .dv-kept { width: 150px; text-align: right; flex-shrink: 0; font-weight: 700; color: var(--text2); white-space: nowrap; }\n"
    "  .dv-posrank { width: 80px; text-align: right; flex-shrink: 0; font-weight: 700; color: var(--text2); }\n"
    "  .dv-ovrpick { width: 110px; text-align: right; flex-shrink: 0; color: var(--text2); white-space: nowrap; }\n"
    "  .kp-origin { display: none; }\n"
    "  @media (max-width: 640px) {\n"
    "    .dv-kept { order: 2; flex: 1 1 100%; width: 100%; text-align: left; white-space: normal; }\n"
    "    #keeperChainsBoard .draft-pick-meta { display: none; }\n"
    "    #keeperChainsBoard .dv-posrank { display: none; }\n"
    "    #keeperChainsBoard .dv-ovrpick { display: none; }\n"
    "    #keeperChainsBoard .dv-pts { order: 3; }\n"
    "    #keeperChainsBoard .dv-value { order: 3; }\n"
    "    #keeperChainsBoard .kp-origin {\n"
    "      display: block; order: 4; flex: 1 1 100%; width: 100%; margin-top: 2px;\n"
    "      font-size: 12px; color: var(--muted);\n"
    "    }\n"
    "    #keeperChainsBoard .kp-origin b { color: var(--text2); font-weight: 700; }\n"
    "  }\n"
    "</style>\n</head>",
)

# ---- hero quick-nav tile numbers ----
top_winpct = round(max(float(s["winPct"].rstrip('%')) for s in s2["standings"]))
top_ppg = round(max(s["ppg"] for s in s2["standings"]))
top_pts = round(float([g for g in s5["records"]["singleGame"] if g["title"] == "Highest Winning Score"][0]["entries"][0]["val"].split()[0]))
top_mov = round(float([g for g in s5["records"]["singleGame"] if g["title"] == "Widest Margin of Victory"][0]["entries"][0]["val"].split()[0]))
top_eff = round(max(row["efficiency"] for rows in s5["EFFICIENCY_DATA_BY_YEAR"].values() for row in rows))
seasons_count = len(s2["seasons"])

html = html.replace(
    '<div class="tile-num"><div class="n">64%</div><div class="l">Top Win%</div></div>\n          <div class="tile-num"><div class="n">125</div><div class="l">Top PPG</div></div>',
    f'<div class="tile-num"><div class="n">{top_winpct}%</div><div class="l">Top Win%</div></div>\n          <div class="tile-num"><div class="n">{top_ppg}</div><div class="l">Top PPG</div></div>',
)
html = html.replace(
    '<div class="tile-num"><div class="n">209</div><div class="l">Top Pts</div></div>\n          <div class="tile-num"><div class="n">102</div><div class="l">Top MOV</div></div>',
    f'<div class="tile-num"><div class="n">{top_pts}</div><div class="l">Top Pts</div></div>\n          <div class="tile-num"><div class="n">{top_mov}</div><div class="l">Top MOV</div></div>',
)
latest_draft_year = max(s6["DRAFTS_DATA"].keys(), key=lambda y: int(y))
latest_picks = s6["DRAFTS_DATA"][latest_draft_year]
picks_count = len(latest_picks)
top_value = max((row[9] for row in latest_picks if row[9] is not None), default=0)
top_value_str = f"+{round(top_value)}" if top_value >= 0 else str(round(top_value))

html = html.replace(
    '<div class="tile-sub">2025 draft recaps and steals vs. busts by the numbers</div>\n        <div class="tile-nums">\n          <div class="tile-num"><div class="n">192</div><div class="l">Picks</div></div>\n          <div class="tile-num"><div class="n">+184</div><div class="l">Top Value</div></div>',
    f'<div class="tile-sub">{latest_draft_year} draft recaps and steals vs. busts by the numbers</div>\n        <div class="tile-nums">\n          <div class="tile-num"><div class="n">{picks_count}</div><div class="l">Picks</div></div>\n          <div class="tile-num"><div class="n">{top_value_str}</div><div class="l">Top Value</div></div>',
)
html = html.replace(
    '<div class="tile-num"><div class="n">92%</div><div class="l">Top Efficiency</div></div>\n          <div class="tile-num"><div class="n">4</div><div class="l">Seasons</div></div>',
    f'<div class="tile-num"><div class="n">{top_eff}%</div><div class="l">Top Efficiency</div></div>\n          <div class="tile-num"><div class="n">{seasons_count}</div><div class="l">Seasons</div></div>',
)

# ---- Draft Value card heading ----
html = html.replace("<h2>\U0001F4CA Draft Value</h2>", "<h2>\U0001F4CA Draft Value (Top 10 Scorers)</h2>")

# ---- Draft Value empty-state guard ----
old_init = """function initDraftRecap() {
  populateDraftSeasonSelect();"""
new_init = """function initDraftRecap() {
  if (!Object.keys(DRAFTS_DATA).length) {
    const msg = '<p style="margin:0;color:var(--muted);font-size:14px">Draft data for this league is coming soon.</p>';
    ['draftBoard', 'draftValueBoard', 'draftValueExtremes', 'keeperChainsBoard'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = msg;
    });
    return;
  }
  renderKeeperChains();
  populateDraftSeasonSelect();"""
assert old_init in html, "initDraftRecap guard splice point not found"
html = html.replace(old_init, new_init)

# ---- Keeper Picks card: client-only feature (TW league has no keepers), so it's
# layered on here rather than in the shared template. Cumulative value = sum of
# each kept season's already-computed value across the player's whole keeper run. ----
keeper_card_html = """    <div class="card">
      <details class="collapsible">
        <summary class="section-head">
          <h2>\U0001F517 Keeper Picks</h2>
          <span class="collapsible-chevron">▾</span>
        </summary>
        <div class="collapsible-body">
          <p style="margin:0 0 12px;color:var(--muted);font-size:13px">Keeper picks judged across every season they were kept, not just one year at a time — cumulative value is the sum of each kept season's value against that season's draft-slot expectation.</p>
          <div id="keeperChainsBoard"></div>
        </div>
      </details>
    </div>
  </div><!-- /draft -->"""
assert "  </div><!-- /draft -->" in html, "draft view closing tag not found"
html = html.replace("  </div><!-- /draft -->", keeper_card_html)

keeper_js = """function keeperChainHeaderHTML() {
  return `
      <span class="dv-player">Player</span>
      <span class="dv-team">Team</span>
      <span class="draft-pick-meta">Pos</span>
      <span class="dv-kept">Kept</span>
      <span class="dv-posrank">Draft Pick</span>
      <span class="dv-ovrpick">Ovr Pick</span>
      <span class="dv-pts">Total Pts</span>
      <span class="dv-value">Total Value</span>`;
}

function keeperChainRowHTML(k) {
  const posLabel = k.pos === 'D/ST' ? 'DEF' : k.pos;
  const span = k.startYear === k.endYear ? `${k.startYear}` : `${k.startYear}–${k.endYear}`;
  const valueText = k.cumulativeValue > 0 ? `+${k.cumulativeValue.toFixed(2)}` : k.cumulativeValue.toFixed(2);
  const valueClass = k.cumulativeValue > 0 ? 'w' : k.cumulativeValue < 0 ? 'l' : '';
  const note = k.leftCensored ? ' <span style="color:var(--muted);font-size:10px">(kept before 2019)</span>' : '';
  const originPick = `${k.originRound}.${String(k.originRoundPick).padStart(2, '0')}`;
  return `
      <span class="dv-player">${k.player}${note}</span>
      <span class="dv-team">${k.team}</span>
      <span class="draft-pick-meta">${posLabel}</span>
      <span class="dv-kept">${span} &middot; ${k.yearsKept}yr</span>
      <span class="dv-posrank">${posLabel}${k.originDraftRank}</span>
      <span class="dv-ovrpick">${originPick} (${k.startYear})</span>
      <span class="dv-pts"><span class="mobile-label">Points: </span>${k.totalPoints.toFixed(1)}</span>
      <span class="dv-value ${valueClass}"><span class="mobile-label">Difference: </span>${valueText}</span>
      <span class="kp-origin">Originally Drafted as: <b>${posLabel}${k.originDraftRank}</b> &middot; Ovr Pick: <b>${originPick}</b> (${k.startYear})</span>`;
}

function renderKeeperChains() {
  const board = document.getElementById('keeperChainsBoard');
  if (!board) return;
  if (!KEEPER_CHAINS_DATA || !KEEPER_CHAINS_DATA.length) {
    board.innerHTML = '<p style="margin:0;color:var(--muted);font-size:14px">No multi-season keeper history yet.</p>';
    return;
  }
  board.innerHTML = '';
  const sorted = [...KEEPER_CHAINS_DATA].sort((a, b) => b.cumulativeValue - a.cumulativeValue);
  const best = sorted.slice(0, 10);
  const worst = sorted.slice(-10).reverse();

  [{ label: 'Best Cumulative Value', rows: best }, { label: 'Worst Cumulative Value', rows: worst }].forEach(group => {
    const head = document.createElement('div');
    head.className = 'group-head';
    head.textContent = group.label;
    board.appendChild(head);

    const scroll = document.createElement('div');
    scroll.className = 'dv-scroll';
    board.appendChild(scroll);

    const header = document.createElement('div');
    header.className = 'dv-header';
    header.innerHTML = keeperChainHeaderHTML();
    scroll.appendChild(header);

    group.rows.forEach(k => {
      const row = document.createElement('div');
      row.className = 'draft-value-row';
      row.innerHTML = keeperChainRowHTML(k);
      scroll.appendChild(row);
    });
  });
}

function initDraftRecap() {"""
assert "function initDraftRecap() {" in html, "initDraftRecap def not found for JS insertion"
html = html.replace("function initDraftRecap() {", keeper_js, 1)

out_path = ROOT / "index.html"
out_path.write_text(html)
print(f"\nWrote {out_path} ({len(html)} bytes, {html.count(chr(10))+1} lines)")
print(f"Tile numbers: Win%={top_winpct} PPG={top_ppg} Pts={top_pts} MOV={top_mov} Eff={top_eff}% Seasons={seasons_count}")
