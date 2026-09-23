"""
Generates blue/green GitHub stat cards as SVG files in ./assets
using only the GitHub GraphQL API (runs inside GitHub Actions).

Outputs:
  assets/stats.svg      - stars, commits, PRs, issues, repos, contributions
  assets/top-langs.svg  - most used languages
  assets/streak.svg     - total contributions, current & longest streak
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

LOGIN = os.environ.get("USERNAME", "Biswa-source45")
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT = os.path.join(os.path.dirname(__file__), "..", "assets")

BG, BORDER, TEXT, MUTED = "#0d1117", "#1f2937", "#c9d1d9", "#8b949e"
BLUE, GREEN = "#38bdf8", "#34d399"
PALETTE = ["#0ea5e9", "#10b981", "#38bdf8", "#34d399", "#0369a1", "#047857"]
FONT = "'Segoe UI',Ubuntu,'Helvetica Neue',Arial,sans-serif"


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    if "errors" in data:
        sys.exit(f"GraphQL error: {data['errors']}")
    return data["data"]


# ─────────────────────────── data ───────────────────────────
def fetch():
    user_q = """
    query($login:String!,$cursor:String){ user(login:$login){
      name login createdAt
      pullRequests{totalCount} issues{totalCount}
      repositories(first:100, after:$cursor, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC){
        totalCount pageInfo{hasNextPage endCursor}
        nodes{ stargazerCount
          languages(first:10, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name } } } }
      } } }"""
    cursor, repos, user = None, [], None
    while True:
        u = gql(user_q, {"login": LOGIN, "cursor": cursor})["user"]
        user = user or u
        repos += u["repositories"]["nodes"]
        page = u["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]

    cal_q = """
    query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){
      contributionsCollection(from:$from, to:$to){
        totalCommitContributions restrictedContributionsCount
        contributionCalendar{ totalContributions weeks{ contributionDays{ date contributionCount } } }
      } } }"""
    start_year = int(user["createdAt"][:4])
    now = datetime.now(timezone.utc)
    days, commits = {}, 0
    for year in range(start_year, now.year + 1):
        frm = f"{year}-01-01T00:00:00Z"
        to = now.strftime("%Y-%m-%dT%H:%M:%SZ") if year == now.year else f"{year}-12-31T23:59:59Z"
        cc = gql(cal_q, {"login": LOGIN, "from": frm, "to": to})["user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        for w in cc["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]

    return {
        "name": (user["name"] or LOGIN).split()[0],
        "stars": sum(r["stargazerCount"] for r in repos),
        "repos": user["repositories"]["totalCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "commits": commits,
        "days": days,
        "since": user["createdAt"][:10],
        "langs": langs,
    }


def streaks(days):
    today = date.today()
    ordered = sorted((date.fromisoformat(k), v) for k, v in days.items() if date.fromisoformat(k) <= today)
    longest = run = 0
    longest_range = cur_range = (None, None)
    for d, c in ordered:
        if c > 0:
            run += 1
            cur_range = (cur_range[0] if run > 1 else d, d)
            if run > longest:
                longest, longest_range = run, cur_range
        else:
            run = 0
    # current streak: count back from today (today may still be 0)
    current, d = 0, today
    if days.get(d.isoformat(), 0) == 0:
        d -= timedelta(days=1)
    end = d
    while days.get(d.isoformat(), 0) > 0:
        current += 1
        d -= timedelta(days=1)
    cur = (d + timedelta(days=1), end) if current else (None, None)
    return current, cur, longest, longest_range


# ─────────────────────────── svg helpers ───────────────────────────
def fmt(n):
    return f"{n/1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def fdate(d):
    return d.strftime("%b %d, %Y") if d else ""


def card(w, h, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<style>
 text{{font-family:{FONT}}}
 .title{{font-size:17px;font-weight:700;fill:{BLUE}}}
 .lbl{{font-size:13.5px;fill:{TEXT}}}
 .val{{font-size:13.5px;font-weight:700;fill:#fff}}
 .muted{{font-size:11.5px;fill:{MUTED}}}
 .big{{font-size:28px;font-weight:700;fill:#fff}}
 .row{{opacity:0;animation:fade .6s ease forwards}}
 .grow{{animation:grow 1.2s ease forwards}}
 @keyframes fade{{from{{opacity:0;transform:translateX(-6px)}}to{{opacity:1;transform:translateX(0)}}}}
 @keyframes grow{{from{{stroke-dashoffset:251}}}}
</style>
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{GREEN}"/></linearGradient></defs>
<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="10" fill="{BG}" stroke="{BORDER}"/>
{body}
</svg>"""


def stats_svg(s):
    total_contrib = sum(s["days"].values())
    rows = [("Total Stars", s["stars"]), ("Total Commits", s["commits"]), ("Pull Requests", s["prs"]),
            ("Issues", s["issues"]), ("Public Repos", s["repos"])]
    body = f'<text x="25" y="36" class="title">{s["name"]}\'s GitHub Stats</text>'
    for i, (k, v) in enumerate(rows):
        y = 70 + i * 25
        color = BLUE if i % 2 == 0 else GREEN
        body += (f'<g class="row" style="animation-delay:{0.15*i:.2f}s">'
                 f'<circle cx="31" cy="{y-4.5}" r="4" fill="{color}"/>'
                 f'<text x="44" y="{y}" class="lbl">{k}:</text>'
                 f'<text x="190" y="{y}" class="val">{fmt(v)}</text></g>')
    # ring
    body += (f'<circle cx="355" cy="105" r="40" fill="none" stroke="{BORDER}" stroke-width="7"/>'
             f'<circle cx="355" cy="105" r="40" fill="none" stroke="url(#bg)" stroke-width="7" '
             f'stroke-linecap="round" stroke-dasharray="251" stroke-dashoffset="0" class="grow" '
             f'transform="rotate(-90 355 105)"/>'
             f'<text x="355" y="110" text-anchor="middle" class="val" style="font-size:18px">{fmt(total_contrib)}</text>'
             f'<text x="355" y="165" text-anchor="middle" class="muted">contributions</text>')
    return card(450, 195, body)


def langs_svg(s):
    items = sorted(s["langs"].items(), key=lambda x: -x[1])[:6]
    total = sum(v for _, v in items) or 1
    body = '<text x="25" y="36" class="title">Most Used Languages</text>'
    body += f'<mask id="m"><rect x="25" y="55" width="400" height="9" rx="4.5" fill="#fff"/></mask><g mask="url(#m)">'
    x = 25
    for i, (_, v) in enumerate(items):
        w = 400 * v / total
        body += f'<rect x="{x:.2f}" y="55" width="{w+0.5:.2f}" height="9" fill="{PALETTE[i]}"/>'
        x += w
    body += "</g>"
    for i, (name, v) in enumerate(items):
        col, row = i % 2, i // 2
        cx, y = 30 + col * 210, 98 + row * 30
        body += (f'<g class="row" style="animation-delay:{0.12*i:.2f}s">'
                 f'<circle cx="{cx}" cy="{y-4.5}" r="5" fill="{PALETTE[i]}"/>'
                 f'<text x="{cx+13}" y="{y}" class="lbl">{name}</text>'
                 f'<text x="{cx+180}" y="{y}" text-anchor="end" class="muted">{100*v/total:.1f}%</text></g>')
    return card(450, 195, body)


def streak_svg(s):
    days = s["days"]
    total = sum(days.values())
    current, cur_r, longest, long_r = streaks(days)
    third = 300
    body = ""
    cols = [
        (fmt(total), "Total Contributions", f"{fdate(date.fromisoformat(s['since']))} - Present", BLUE),
        (str(current), "Current Streak", f"{fdate(cur_r[0])} - {fdate(cur_r[1])}" if current else "Start one today!", GREEN),
        (str(longest), "Longest Streak", f"{fdate(long_r[0])} - {fdate(long_r[1])}" if longest else "", BLUE),
    ]
    for i, (big, lbl, sub, color) in enumerate(cols):
        cx = third * i + third / 2
        if i == 1:
            body += (f'<circle cx="{cx}" cy="68" r="40" fill="none" stroke="{BORDER}" stroke-width="6"/>'
                     f'<circle cx="{cx}" cy="68" r="40" fill="none" stroke="url(#bg)" stroke-width="6" '
                     f'stroke-linecap="round" stroke-dasharray="251" class="grow" transform="rotate(-90 {cx} 68)"/>'
                     f'<text x="{cx}" y="78" text-anchor="middle" class="big">{big}</text>'
                     f'<text x="{cx}" y="138" text-anchor="middle" class="lbl" style="fill:{color};font-weight:700">{lbl}</text>'
                     f'<text x="{cx}" y="158" text-anchor="middle" class="muted">{sub}</text>')
        else:
            body += (f'<g class="row" style="animation-delay:{0.2*i:.2f}s">'
                     f'<text x="{cx}" y="78" text-anchor="middle" class="big">{big}</text>'
                     f'<text x="{cx}" y="112" text-anchor="middle" class="lbl" style="fill:{color};font-weight:700">{lbl}</text>'
                     f'<text x="{cx}" y="134" text-anchor="middle" class="muted">{sub}</text></g>')
    body += (f'<line x1="{third}" y1="30" x2="{third}" y2="150" stroke="{BORDER}"/>'
             f'<line x1="{third*2}" y1="30" x2="{third*2}" y2="150" stroke="{BORDER}"/>')
    return card(900, 180, body)


def main():
    if os.environ.get("DEMO"):
        today = date.today()
        s = {"name": "Biswabhusan", "stars": 72, "repos": 34, "prs": 21, "issues": 9, "commits": 480,
             "since": "2024-02-28",
             "days": {(today - timedelta(days=i)).isoformat(): (i % 7 != 5) * (i % 4 + 1) for i in range(400)},
             "langs": {"JavaScript": 40, "Python": 22, "HTML": 18, "TypeScript": 9, "Vue": 6, "CSS": 5}}
    else:
        if not TOKEN:
            sys.exit("GITHUB_TOKEN is not set")
        s = fetch()
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("stats.svg", stats_svg), ("top-langs.svg", langs_svg), ("streak.svg", streak_svg)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(fn(s))
    print("Cards generated.")


if __name__ == "__main__":
    main()
