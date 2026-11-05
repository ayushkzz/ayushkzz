"""Build the "GitHub activity" card (assets/activity-{dark,light}.svg).

Runs daily in .github/workflows/profile-cards.yml. It reads public contribution
data from the GitHub GraphQL API with the workflow's GITHUB_TOKEN and draws it in
the same fonts and colours as the other graphics from build.py.

Usage:  GITHUB_TOKEN=... python assets/activity.py [username]
        python assets/activity.py --sample   # fake data, for previewing the design
"""

import json
import os
import random
import sys
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from build import HERE, THEMES, Svg, panel, text_width

# Languages left out of the "top languages" bar.
HIDDEN_LANGUAGES = {"HTML", "Jupyter Notebook"}

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    createdAt
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC) { totalCount }
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
      commitContributionsByRepository(maxRepositories: 100) {
        repository { primaryLanguage { name color } }
        contributions { totalCount }
      }
    }
  }
}"""


def graphql(token, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def fetch(login, token):
    """Every contribution day since the account was created, plus commit counts per language."""
    now = datetime.now(timezone.utc)
    end, days, langs, created, repos = now, {}, Counter(), None, 0
    colors = {}
    while True:
        start = end - timedelta(days=365)
        u = graphql(token, {"login": login, "from": start.isoformat(), "to": end.isoformat()})
        created = datetime.fromisoformat(u["createdAt"].replace("Z", "+00:00"))
        repos = u["repositories"]["totalCount"]
        cc = u["contributionsCollection"]
        for w in cc["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
        for item in cc["commitContributionsByRepository"]:
            lang = item["repository"]["primaryLanguage"]
            if lang:
                langs[lang["name"]] += item["contributions"]["totalCount"]
                colors[lang["name"]] = lang["color"] or "#9aa3b5"
        if start <= created:
            break
        end = start
    return dict(days=days, langs=langs, colors=colors, repos=repos, created=created.date())


def sample():
    rnd = random.Random(7)
    today = date.today()
    days = {}
    for i in range(3 * 365):
        d = today - timedelta(days=i)
        peak = 30 if 200 <= i <= 240 else 6 if 120 <= i <= 150 or 290 <= i <= 310 else 0
        days[d.isoformat()] = rnd.choice([0, 0, 1, 2, 3, 5]) if peak and rnd.random() < .6 else 0
    days[today.isoformat()] = 2
    langs = Counter({"HTML": 52, "Jupyter Notebook": 30, "Java": 21, "JavaScript": 15, "Python": 7})
    colors = {"HTML": "#e34c26", "Jupyter Notebook": "#DA5B0B", "Java": "#b07219",
              "JavaScript": "#f1e05a", "Python": "#3572A5"}
    return dict(days=days, langs=langs, colors=colors, repos=18, created=date(2023, 9, 27))


def streaks(days):
    """(current, longest) streak in days. Today not having contributions yet doesn't break the streak."""
    if not days:
        return 0, 0
    longest = run = 0
    prev = None
    for ds in sorted(days):
        if days[ds] > 0:
            d = date.fromisoformat(ds)
            run = run + 1 if prev and (d - prev).days == 1 else 1
            prev = d
            longest = max(longest, run)
    last = max(date.fromisoformat(k) for k in days)
    d = last if days[last.isoformat()] > 0 else last - timedelta(days=1)
    current = 0
    while days.get(d.isoformat(), 0) > 0:
        current += 1
        d -= timedelta(days=1)
    return current, longest


def render(data, t, path):
    W, pad = 1000, 32
    days = data["days"]
    last = max(date.fromisoformat(k) for k in days)
    # last 53 weeks, columns start on Sunday like GitHub's own calendar
    start = last - timedelta(days=(last.weekday() + 1) % 7) - timedelta(weeks=52)
    year = [(start + timedelta(days=i)) for i in range((last - start).days + 1)]
    total = sum(days.get(d.isoformat(), 0) for d in year)
    all_time = sum(days.values())
    current, longest = streaks(days)
    plural = lambda n, w: f"{n} {w}" if n == 1 else f"{n} {w}s"

    cell, gap = 13.5, 4
    step = cell + gap
    weeks = (len(year) + 6) // 7
    grid_w = weeks * step - gap
    grid_x = (W - grid_w) / 2

    stats_y, grid_top = pad, 168
    grid_h = 7 * step - gap
    lang_top = grid_top + grid_h + 58
    H = lang_top + 92

    s = Svg(W, H, f"GitHub activity: {all_time} contributions since {data['created']:%B %Y}, {total} in the last year, "
                  f"current streak {plural(current, 'day')}, longest streak {plural(longest, 'day')}, "
                  f"{data['repos']} public repos")
    s.css.append(
        "@keyframes pop{from{opacity:0}to{opacity:1}}"
        ".wk{animation:pop .5s ease-out both}"
        "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
    )
    panel(s, t, 0, 0, W, H, 18)

    # stat tiles
    tiles = [
        (f"{all_time:,}", "contributions", f"since {data['created']:%b %Y}"),
        (str(current), "current streak", "day" if current == 1 else "days"),
        (str(longest), "longest streak", "day" if longest == 1 else "days"),
        (str(data["repos"]), "repositories", "public"),
    ]
    tw = (W - pad * 2 - 3 * 14) / 4
    for i, (num, label, sub) in enumerate(tiles):
        x = pad + i * (tw + 14)
        s.add(f'<rect x="{x + .5:.1f}" y="{stats_y + .5}" width="{tw - 1:.1f}" height="99" rx="14" '
              f'fill="{t["surface2"]}" stroke="{t["border"]}"/>')
        s.text(x + 20, stats_y + 30, label.upper(), "mono-sb", 11, t["muted"], extra='letter-spacing="1"')
        fill = t["a1"] if i == 1 else t["text"]
        s.text(x + 20, stats_y + 74, num, "display", 38, fill, extra='letter-spacing="-1"')
        nx = x + 20 + text_width(num, "display", 38) - len(num) + 8
        s.text(nx, stats_y + 74, sub, "body", 14, t["muted"])

    # month labels
    seen = set()
    for i, d in enumerate(year):
        col = i // 7
        if d.day <= 7 and d.weekday() == 6 and (d.year, d.month) not in seen and col < weeks - 1:
            seen.add((d.year, d.month))
            s.text(grid_x + col * step, grid_top - 12, d.strftime("%b"), "mono", 11, t["muted"])

    # heatmap
    # shade by quartiles of the active days, like GitHub's own graph
    active = sorted(n for n in (days.get(d.isoformat(), 0) for d in year) if n > 0) or [1]
    q = [active[min(len(active) - 1, int(len(active) * f))] for f in (.25, .5, .75)]
    def level(n):
        if n <= 0:
            return 0
        return 1 + sum(n > x for x in q)
    shades = {1: (t["a1"], .35), 2: (t["a1"], .6), 3: (t["a1"], .85), 4: (t["a2"], 1)}
    for col in range(weeks):
        s.add(f'<g class="wk" style="animation-delay:{col * 18}ms">')
        for row in range(7):
            i = col * 7 + row
            if i >= len(year):
                break
            n = days.get(year[i].isoformat(), 0)
            lv = level(n)
            x, y = grid_x + col * step, grid_top + row * step
            if lv:
                c, o = shades[lv]
                s.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell}" height="{cell}" rx="3.5" fill="{c}" fill-opacity="{o}"/>')
            else:
                s.add(f'<rect x="{x + .5:.1f}" y="{y + .5:.1f}" width="{cell - 1}" height="{cell - 1}" rx="3" '
                      f'fill="{t["surface2"]}" stroke="{t["border"]}"/>')
        s.add("</g>")

    # legend
    lx = grid_x + grid_w - 5 * step - text_width("More", "mono", 11) - 8
    ly = grid_top + grid_h + 26
    s.text(lx - 8, ly + 10.5, "Less", "mono", 11, t["muted"], anchor="end")
    for k in range(5):
        x = lx + k * step
        if k:
            c, o = shades[k]
            s.add(f'<rect x="{x:.1f}" y="{ly}" width="{cell}" height="{cell}" rx="3.5" fill="{c}" fill-opacity="{o}"/>')
        else:
            s.add(f'<rect x="{x + .5:.1f}" y="{ly + .5}" width="{cell - 1}" height="{cell - 1}" rx="3" '
                  f'fill="{t["surface2"]}" stroke="{t["border"]}"/>')
    s.text(lx + 5 * step + 2, ly + 10.5, "More", "mono", 11, t["muted"])
    s.text(grid_x, ly + 10.5, f"Last 12 months · {plural(total, 'contribution')}", "mono", 11, t["muted"])

    # languages
    s.add(f'<line x1="{pad}" x2="{W - pad}" y1="{lang_top - 18}" y2="{lang_top - 18}" stroke="{t["border"]}"/>')
    s.text(pad, lang_top + 10, "TOP LANGUAGES BY COMMIT", "mono-sb", 11, t["muted"], extra='letter-spacing="1"')
    top = [(n, v) for n, v in data["langs"].most_common() if n not in HIDDEN_LANGUAGES][:6]
    tot = sum(v for _, v in top) or 1
    bar_y, bar_w = lang_top + 26, W - pad * 2
    s.defs.append(f'<clipPath id="bar"><rect x="{pad}" y="{bar_y}" width="{bar_w}" height="10" rx="5"/></clipPath>')
    s.add('<g clip-path="url(#bar)">')
    x = pad
    for name, v in top:
        w = bar_w * v / tot
        s.add(f'<rect x="{x:.1f}" y="{bar_y}" width="{w + .5:.1f}" height="10" fill="{data["colors"][name]}"/>')
        x += w
    s.add("</g>")
    x = pad
    for name, v in top:
        label = f"{name}"
        pct = f"{100 * v / tot:.0f}%"
        s.add(f'<circle cx="{x + 5}" cy="{bar_y + 38}" r="5" fill="{data["colors"][name]}"/>')
        s.text(x + 16, bar_y + 43, label, "body-m", 14, t["text"])
        px = x + 16 + text_width(label, "body-m", 14) + 6
        s.text(px, bar_y + 43, pct, "mono", 12, t["muted"])
        x = px + text_width(pct, "mono", 12) + 22
    s.save(path)


if __name__ == "__main__":
    if "--sample" in sys.argv:
        data = sample()
    else:
        login = next((a for a in sys.argv[1:] if not a.startswith("-")), None) or os.environ.get("GITHUB_REPOSITORY_OWNER")
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not (login and token):
            raise SystemExit("Set GITHUB_TOKEN and pass a username (or run with --sample).")
        data = fetch(login, token)
    for mode, t in THEMES.items():
        render(data, t, HERE / f"activity-{mode}.svg")
    print("built activity cards:", sum(data["days"].values()), "contributions total,",
          dict(data["langs"].most_common(6)))
