"""Gera os cards SVG do perfil (estatísticas + linguagens) a partir da API GraphQL do GitHub.

Uso: GITHUB_TOKEN=... python .github/scripts/stats.py
Se STATS_TOKEN (PAT com escopo `repo`) estiver definido, inclui repositórios privados.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone
from html import escape

USER = os.environ.get("GH_USER", "YangAngelo")
TOKEN = os.environ.get("STATS_TOKEN") or os.environ["GITHUB_TOKEN"]
INCLUDE_PRIVATE = bool(os.environ.get("STATS_TOKEN"))
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "assets")

BG, CARD, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED = "#e6edf3", "#8b949e"
ACCENT_A, ACCENT_B = "#00d4ff", "#a855f7"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"


def gql(query, variables=None):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def collect():
    privacy = "" if INCLUDE_PRIVATE else ", privacy: PUBLIC"
    base = gql(
        f"""query($login: String!) {{
          user(login: $login) {{
            createdAt
            followers {{ totalCount }}
            pullRequests {{ totalCount }}
            issues {{ totalCount }}
            repositories(ownerAffiliations: OWNER, first: 100, isFork: false{privacy}) {{
              totalCount
              nodes {{
                stargazerCount
                languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
                  edges {{ size node {{ name color }} }}
                }}
              }}
            }}
          }}
        }}""",
        {"login": USER},
    )["user"]

    created = datetime.fromisoformat(base["createdAt"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    commits = contributions = 0
    for year in range(created.year, now.year + 1):
        start = max(created, datetime(year, 1, 1, tzinfo=timezone.utc))
        end = min(now, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
        c = gql(
            """query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) { contributionsCollection(from: $from, to: $to) {
                totalCommitContributions restrictedContributionsCount
                contributionCalendar { totalContributions } } } }""",
            {"login": USER, "from": start.isoformat(), "to": end.isoformat()},
        )["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"]
        contributions += c["contributionCalendar"]["totalContributions"]

    cal = gql(
        """query($login: String!) { user(login: $login) { contributionsCollection {
          contributionCalendar { weeks { contributionDays { date contributionCount } } } } } }""",
        {"login": USER},
    )["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [d for w in cal for d in w["contributionDays"]][-31:]

    langs = {}
    for repo in base["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            langs.setdefault(name, [0, e["node"]["color"] or "#8b949e"])
            langs[name][0] += e["size"]

    return {
        "repos": base["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in base["repositories"]["nodes"]),
        "commits": commits,
        "contributions": contributions,
        "prs": base["pullRequests"]["totalCount"],
        "followers": base["followers"]["totalCount"],
        "since": created.year,
        "langs": sorted(langs.items(), key=lambda kv: -kv[1][0]),
        "days": days,
        "updated": now.strftime("%d/%m/%Y"),
    }


def activity_card(d):
    days = d["days"]
    w, h = 990, 260
    left, right, top, bottom = 50, 20, 60, 40
    pw, ph = w - left - right, h - top - bottom
    peak = max([x["contributionCount"] for x in days] + [4])
    step = pw / max(len(days) - 1, 1)
    pts = [
        (left + i * step, top + ph - ph * x["contributionCount"] / peak)
        for i, x in enumerate(days)
    ]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{left},{top + ph} {line} {left + pw},{top + ph}"
    grid = "".join(
        f'<line x1="{left}" x2="{left + pw}" y1="{top + ph * k / 4:.1f}" y2="{top + ph * k / 4:.1f}" stroke="{BORDER}" stroke-dasharray="3 4"/>'
        f'<text x="{left - 10}" y="{top + ph * k / 4 + 4:.1f}" class="s" text-anchor="end">{round(peak * (4 - k) / 4)}</text>'
        for k in range(5)
    )
    labels = "".join(
        f'<text x="{x:.1f}" y="{h - 14}" class="s" text-anchor="middle">{days[i]["date"][8:10]}/{days[i]["date"][5:7]}</text>'
        for i, (x, _) in enumerate(pts) if i % 5 == 0 or i == len(pts) - 1
    )
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{ACCENT_B}" stroke="{CARD}" stroke-width="1.5"/>'
        for x, y in pts
    )
    total = sum(x["contributionCount"] for x in days)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  {defs()}
  <defs><linearGradient id="a" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{ACCENT_A}" stop-opacity=".35"/><stop offset="1" stop-color="{ACCENT_A}" stop-opacity="0"/>
  </linearGradient></defs>
  <style>.ln {{ stroke-dasharray: 3000; stroke-dashoffset: 3000; animation: draw 2s ease-out forwards; }}
    @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}</style>
  <rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="{CARD}" stroke="{BORDER}"/>
  <text x="20" y="36" class="t">📅 Atividade nos últimos 31 dias</text>
  <text x="{w - 20}" y="36" class="l" text-anchor="end">{total} contribuições</text>
  {grid}
  <polygon points="{area}" fill="url(#a)" class="f" style="animation-delay:.6s"/>
  <polyline points="{line}" fill="none" stroke="url(#g)" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" class="ln"/>
  <g class="f" style="animation-delay:1.2s">{dots}</g>
  {labels}
</svg>"""


def defs():
    return f"""<defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{ACCENT_A}"/><stop offset="1" stop-color="{ACCENT_B}"/>
    </linearGradient>
  </defs>
  <style>
    .t {{ font: 600 18px {FONT}; fill: {TEXT}; }}
    .l {{ font: 400 13px {FONT}; fill: {MUTED}; }}
    .v {{ font: 700 26px {FONT}; fill: {TEXT}; }}
    .s {{ font: 400 11px {FONT}; fill: {MUTED}; }}
    .f {{ opacity: 0; animation: fade .6s ease-out forwards; }}
    @keyframes fade {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}
    .bar {{ transform-box: fill-box; transform-origin: left; animation: grow 1s ease-out forwards; }}
  </style>"""


def stats_card(d):
    w, h = 495, 210
    tiles = [
        ("Repositórios", d["repos"]),
        ("Commits", d["commits"]),
        ("Contribuições", d["contributions"]),
        ("Pull Requests", d["prs"]),
        ("Linguagens", len(d["langs"])),
        ("Anos no GitHub", datetime.now().year - d["since"] + 1),
    ]
    parts = []
    tw, th, gap, x0, y0 = 145, 64, 10, 20, 56
    for i, (label, value) in enumerate(tiles):
        x = x0 + (i % 3) * (tw + gap)
        y = y0 + (i // 3) * (th + gap)
        parts.append(
            f'<g class="f" style="animation-delay:{0.1 + i * 0.08:.2f}s">'
            f'<rect x="{x}" y="{y}" width="{tw}" height="{th}" rx="10" fill="{BG}" stroke="{BORDER}"/>'
            f'<rect x="{x}" y="{y + 14}" width="3" height="{th - 28}" rx="1.5" fill="url(#g)"/>'
            f'<text x="{x + 16}" y="{y + 32}" class="v">{value}</text>'
            f'<text x="{x + 16}" y="{y + 51}" class="l">{escape(label)}</text></g>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  {defs()}
  <rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="{CARD}" stroke="{BORDER}"/>
  <text x="20" y="36" class="t">📊 Estatísticas no GitHub</text>
  <text x="{w - 20}" y="36" class="s" text-anchor="end">atualizado {d["updated"]}</text>
  {''.join(parts)}
</svg>"""


def langs_card(d):
    top = d["langs"][:6]
    total = sum(v[0] for _, v in top) or 1
    w, h = 495, 210
    bar_w, bx, by = w - 40, 20, 58
    segs, x = [], bx
    for _, (size, color) in top:
        sw = bar_w * size / total
        segs.append(f'<rect x="{x:.1f}" y="{by}" width="{sw:.1f}" height="10" fill="{color}"/>')
        x += sw
    items = []
    for i, (name, (size, color)) in enumerate(top):
        cx = 24 + (i % 2) * 235
        cy = by + 44 + (i // 2) * 34
        pct = 100 * size / total
        items.append(
            f'<g class="f" style="animation-delay:{0.3 + i * 0.08:.2f}s">'
            f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{color}"/>'
            f'<text x="{cx + 18}" y="{cy}" class="l" style="fill:{TEXT}">{escape(name)}</text>'
            f'<text x="{cx + 205}" y="{cy}" class="l" text-anchor="end">{pct:.1f}%</text></g>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  {defs()}
  <clipPath id="c"><rect x="{bx}" y="{by}" width="{bar_w}" height="10" rx="5"/></clipPath>
  <rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="{CARD}" stroke="{BORDER}"/>
  <text x="20" y="36" class="t">💻 Linguagens mais usadas</text>
  <g clip-path="url(#c)"><g class="bar">{''.join(segs)}</g></g>
  {''.join(items)}
</svg>"""


if __name__ == "__main__":
    data = collect()
    os.makedirs(OUT, exist_ok=True)
    for name, svg in (("stats.svg", stats_card(data)), ("languages.svg", langs_card(data)), ("activity.svg", activity_card(data))):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(svg)
    print(json.dumps({k: v for k, v in data.items() if k not in ("langs", "days")}, ensure_ascii=False))
