#!/usr/bin/env python3
"""Gera cards SVG a partir do GitHub sem divulgar nomes de repositórios privados."""
import json
import os
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

USERNAME = "ArthurKohlerDev"
START_YEAR = 2024
GREEN, TEXT, MUTED, BG, BORDER = "#3FB950", "#C9D1D9", "#8B949E", "#0D1117", "#30363D"
TZ = timezone(timedelta(hours=-3))
PROFILE_TOKEN = os.environ.get("DASHBOARD_PROFILE_TOKEN", "")
REPOS_TOKEN = os.environ.get("DASHBOARD_REPOS_TOKEN", "")
if not PROFILE_TOKEN or not REPOS_TOKEN:
    raise SystemExit("Configure os secrets DASHBOARD_PROFILE_TOKEN e DASHBOARD_REPOS_TOKEN no GitHub Actions.")


def request_json(url, token, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
               "User-Agent": "ArthurKohlerDev-readme-dashboard"}
    if body:
        headers["Content-Type"] = "application/json"
    with urlopen(Request(url, data=body, headers=headers), timeout=30) as r:
        return json.load(r)


def contributions(start, end):
    query = '''query($from:DateTime!,$to:DateTime!){viewer{
       login contributionsCollection(from:$from,to:$to){contributionCalendar{
       totalContributions weeks{contributionDays{date contributionCount}}}}}}'''
    response = request_json("https://api.github.com/graphql", PROFILE_TOKEN,
        {"query": query, "variables": {"from": start.isoformat(), "to": end.isoformat()}})
    if response.get("errors"):
        raise RuntimeError("Falha no GraphQL: " + str(response["errors"])[:500])
    viewer = response["data"]["viewer"]
    if viewer["login"].lower() != USERNAME.lower():
        raise RuntimeError("O token de perfil pertence a outra conta do GitHub.")
    calendar = viewer["contributionsCollection"]["contributionCalendar"]
    days = {d["date"]: d["contributionCount"] for week in calendar["weeks"]
            for d in week["contributionDays"]}
    return calendar["totalContributions"], days


def repositories_languages():
    totals = Counter()
    page = 1
    while True:
        url = f"https://api.github.com/user/repos?affiliation=owner&visibility=all&per_page=100&page={page}"
        repos = request_json(url, REPOS_TOKEN)
        if not isinstance(repos, list):
            raise RuntimeError("Não foi possível listar repositórios com o token granular.")
        for repo in repos:
            if repo["owner"]["login"].lower() != USERNAME.lower() or repo.get("fork"):
                continue
            repo_name = quote(repo["name"], safe="")
            details = request_json(f"https://api.github.com/repos/{USERNAME}/{repo_name}/languages", REPOS_TOKEN)
            totals.update(details)
        if len(repos) < 100:
            break
        page += 1
    return totals


def xml_start(width, height):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img">'
            f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="12" '
            f'fill="{BG}" stroke="{BORDER}"/>')


def label(x, y, value, size=15, color=TEXT, bold=False, anchor="middle"):
    weight = 'font-weight="700" ' if bold else ""
    return (f'<text x="{x}" y="{y}" fill="{color}" font-family="Arial,sans-serif" '
            f'font-size="{size}" text-anchor="{anchor}" {weight}>{escape(str(value))}</text>')


def simple_card(title, labels):
    parts = [xml_start(820, 170), label(32, 36, title, 18, GREEN, True, "start")]
    for i, (big, small) in enumerate(labels):
        x = 136 + i * 274
        parts.extend([label(x, 102, big, 35, GREEN, True), label(x, 132, small, 13, MUTED)])
        if i < len(labels) - 1:
            parts.append(f'<line x1="{x+137}" y1="60" x2="{x+137}" y2="140" stroke="{BORDER}"/>')
    return "".join(parts) + "</svg>\n"


def yearly_card(annual, rolling):
    total = sum(annual.values())
    years = list(annual)[-3:]
    parts = [xml_start(820, 238), label(32, 32, "Contribuições públicas + privadas", 18, GREEN, True, "start")]
    for x, number, caption in [(215, total, f"Desde {START_YEAR}"),
                                (610, rolling, "Últimos 12 meses")]:
        parts.extend([label(x, 91, number, 33, GREEN, True), label(x, 115, caption, 13, MUTED)])
    parts.append(f'<line x1="410" y1="56" x2="410" y2="120" stroke="{BORDER}"/>')
    parts.append(f'<line x1="32" y1="139" x2="788" y2="139" stroke="{BORDER}"/>')
    for idx, year in enumerate(years):
        x = 137 + idx * 273
        parts.extend([label(x, 188, annual[year], 27, GREEN, True), label(x, 214, str(year), 13, MUTED)])
    return "".join(parts) + "</svg>\n"


def streaks(day_counts, today):
    current_day = today
    if day_counts.get(current_day.isoformat(), 0) == 0:
        current_day -= timedelta(days=1)
    current = 0
    while day_counts.get(current_day.isoformat(), 0) > 0:
        current += 1
        current_day -= timedelta(days=1)
    best = 0
    count = 0
    cursor = date(START_YEAR, 1, 1)
    while cursor <= today:
        count = count + 1 if day_counts.get(cursor.isoformat(), 0) else 0
        best = max(best, count)
        cursor += timedelta(days=1)
    return current, best


def languages_svg(counter):
    total = sum(counter.values())
    if not total:
        return xml_start(820, 100) + label(410, 62, "Sem dados de linguagens disponíveis", 18, MUTED) + "</svg>\n"
    languages = counter.most_common(6)
    height = 82 + len(languages) * 38
    parts = [xml_start(820, height), label(32, 35, "Linguagens (projetos públicos + privados)", 18, GREEN, True, "start")]
    for idx, (name, size) in enumerate(languages):
        y = 75 + idx * 38
        pct = size * 100 / total
        parts.extend([label(32, y, name, 14, TEXT, True, "start"),
                      f'<rect x="245" y="{y-13}" width="475" height="15" rx="5" fill="{BORDER}"/>',
                      f'<rect x="245" y="{y-13}" width="{475*pct/100:.1f}" height="15" rx="5" fill="{GREEN}"/>',
                      label(788, y, f"{pct:.1f}%", 14, TEXT)])
    return "".join(parts) + "</svg>\n"


def main():
    today = datetime.now(TZ).date()
    end = datetime.now(timezone.utc)
    annual, daily = {}, {}
    for year in range(START_YEAR, today.year + 1):
        start = datetime.combine(date(year, 1, 1), time.min, TZ).astimezone(timezone.utc)
        last = min(end, datetime.combine(date(year + 1, 1, 1), time.min, TZ).astimezone(timezone.utc) - timedelta(seconds=1))
        annual[year] = 0
        mid = datetime.combine(date(year, 7, 1), time.min, TZ).astimezone(timezone.utc)
        for left, right in [(start, min(last, mid - timedelta(seconds=1))), (mid, last)]:
            if left > right:
                continue
            count, days = contributions(left, right)
            annual[year] += count
            daily.update({d: n for d, n in days.items() if str(year) == d[:4]})
    try:
        previous_year = today.replace(year=today.year-1)
    except ValueError:  # 29 de fevereiro
        previous_year = date(today.year-1, 2, 28)
    rolling_start = datetime.combine(previous_year, time.min, TZ).astimezone(timezone.utc)
    rolling_total, _ = contributions(rolling_start, end)
    since_total = sum(annual.values())
    current, longest = streaks(daily, today)
    languages = repositories_languages()
    output = Path("assets")
    output.mkdir(exist_ok=True)
    (output / "github-contribuicoes.svg").write_text(yearly_card(annual, rolling_total), encoding="utf-8")
    (output / "github-streak.svg").write_text(simple_card("Sequência de contribuições", [
        (since_total, "Contribuições totais"), (current, "Sequência atual (dias)"),
        (longest, f"Recorde desde {START_YEAR} (dias)")]), encoding="utf-8")
    (output / "github-linguagens.svg").write_text(languages_svg(languages), encoding="utf-8")

    # Só modifica o painel; deixa todas as outras seções do README intactas.
    readme = Path("README.md")
    content = readme.read_text(encoding="utf-8")
    title = "## Atividade no GitHub"
    footer = '\n---\n\n<div align="center">\n\n**Software para resolver problemas reais.**'
    if title not in content or footer not in content:
        raise RuntimeError("Não foi possível localizar a seção existente e a frase final no README.")
    start_pos = content.index(title)
    end_pos = content.index(footer, start_pos)
    new_block = '''## Atividade no GitHub

<div align="center">

  <img width="100%" alt="Contribuições públicas e privadas no GitHub" src="./assets/github-contribuicoes.svg" />

  <img width="100%" alt="Linguagens dos repositórios públicos e privados" src="./assets/github-linguagens.svg" />

  <img width="100%" alt="Sequência de contribuições no GitHub" src="./assets/github-streak.svg" />

</div>
'''
    readme.write_text(content[:start_pos] + new_block + content[end_pos:], encoding="utf-8")
    print("Atualizado:", {"2024+": since_total, "ultimos_12_meses": rolling_total,
                          str(today.year): annual[today.year], "sequencia": current,
                          "recorde": longest, "linguagens": len(languages)})


if __name__ == "__main__":
    main()
