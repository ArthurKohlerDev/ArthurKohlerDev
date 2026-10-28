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


def stats_card(annual, rolling):
    total = sum(annual.values())
    parts = [xml_start(398, 184), label(20, 28, "Estatísticas do GitHub", 17, GREEN, True, "start")]
    parts += [label(105, 93, total, 36, GREEN, True), label(105, 116, "Desde 2024", 12, MUTED),
              label(297, 93, rolling, 36, GREEN, True),
              label(297, 116, "Últimos 12 meses", 12, MUTED),
              f'<line x1="199" y1="48" x2="199" y2="123" stroke="{BORDER}"/>',
              f'<line x1="20" y1="137" x2="378" y2="137" stroke="{BORDER}"/>']
    annual_text = "   |   ".join(f"{year}: {count}" for year, count in sorted(annual.items()))
    parts.append(label(199, 164, annual_text, 12, MUTED))
    return "".join(parts) + "</svg>\n"


def streaks(day_counts, today):
    current_end = today
    if day_counts.get(current_end.isoformat(), 0) == 0:
        current_end -= timedelta(days=1)
    current = 0
    cursor = current_end
    while day_counts.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= timedelta(days=1)
    current_start = cursor + timedelta(days=1) if current else None
    longest, count, longest_end = 0, 0, None
    cursor = date(START_YEAR, 1, 1)
    while cursor <= today:
        count = count + 1 if day_counts.get(cursor.isoformat(), 0) else 0
        if count > longest:
            longest = count
            longest_end = cursor
        cursor += timedelta(days=1)
    longest_start = longest_end - timedelta(days=longest-1) if longest_end else None
    return current, longest, current_start, (current_end if current else None), longest_start, longest_end


def date_range(start, end):
    if not start or not end:
        return "Sem sequência"
    return f"{start:%d/%m} - {end:%d/%m}"


def streak_card(total, current, longest, current_start, current_end, best_start, best_end):
    parts = [xml_start(820, 224),
             f'<line x1="277" y1="30" x2="277" y2="195" stroke="{BORDER}"/>',
             f'<line x1="543" y1="30" x2="543" y2="195" stroke="{BORDER}"/>',
             label(138, 99, total, 41, GREEN, True),
             label(138, 130, "Total de contribuições", 15, TEXT),
             label(138, 156, f"Desde {START_YEAR}", 12, MUTED),
             f'<circle cx="410" cy="90" r="56" fill="none" stroke="{GREEN}" stroke-width="7"/>',
             label(410, 103, current, 43, GREEN, True),
             label(410, 181, "Sequência atual", 16, GREEN, True),
             label(410, 204, date_range(current_start, current_end), 12, MUTED),
             label(682, 99, longest, 41, GREEN, True),
             label(682, 130, "Maior sequência", 15, TEXT),
             label(682, 156, date_range(best_start, best_end), 12, MUTED)]
    return "".join(parts) + "</svg>\n"


def languages_svg(counter):
    total = sum(counter.values())
    if not total:
        return xml_start(398, 184) + label(199, 93, "Sem dados de linguagens", 15, MUTED) + "</svg>\n"
    top_languages = counter.most_common(5)
    parts = [xml_start(398, 184), label(20, 28, "Linguagens mais usadas", 17, GREEN, True, "start")]
    for idx, (name, size) in enumerate(top_languages):
        y = 57 + idx * 26
        pct = 100 * size / total
        parts += [label(20, y, name, 11, TEXT, False, "start"),
                  f'<rect x="147" y="{y-11}" width="176" height="12" rx="5" fill="{BORDER}"/>',
                  f'<rect x="147" y="{y-11}" width="{176*pct/100:.1f}" height="12" rx="5" fill="{GREEN}"/>',
                  label(379, y, f"{pct:.1f}%", 11, TEXT, False, "end")]
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
    current, longest, current_start, current_end, best_start, best_end = streaks(daily, today)
    languages = repositories_languages()
    output = Path("assets")
    output.mkdir(exist_ok=True)
    (output / "github-contribuicoes.svg").write_text(stats_card(annual, rolling_total), encoding="utf-8")
    (output / "github-streak.svg").write_text(streak_card(
        since_total, current, longest, current_start, current_end, best_start, best_end
    ), encoding="utf-8")
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

  <img width="49%" alt="Estatísticas públicas e privadas do GitHub" src="./assets/github-contribuicoes.svg" />
  <img width="49%" alt="Linguagens dos repositórios públicos e privados" src="./assets/github-linguagens.svg" />

  <img width="83%" alt="Sequência de contribuições no GitHub" src="./assets/github-streak.svg" />

</div>
'''
    readme.write_text(content[:start_pos] + new_block + content[end_pos:], encoding="utf-8")
    print("Atualizado:", {"2024+": since_total, "ultimos_12_meses": rolling_total,
                          str(today.year): annual[today.year], "sequencia": current,
                          "recorde": longest, "linguagens": len(languages)})


if __name__ == "__main__":
    main()
