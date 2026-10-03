#!/usr/bin/env python3
"""Atualiza os calendários e resultados do Previsor de jogos (index.html).

Só mexe em dados: nas linhas das ligas abaixo do bloco `const DS=`...`` e nos
"últimos 5 jogos" guardados (SNAP.l5), para passarem a vir do calendário
atualizado. Ecrã, cálculo e estrutura do Previsor ficam iguais.

Fontes: football-data.org (a maioria das ligas) e TheSportsDB (as restantes).

Uso:
  export FOOTBALL_DATA_TOKEN="a_tua_chave"
  python3 atualizar_previsor.py index.html
Para atualizar sozinho, agenda no cron (por exemplo de hora a hora) e volta a alojar o index.html.
"""
import difflib, json, os, re, shutil, sys, time, unicodedata, urllib.request
from datetime import datetime, timezone

HTML = sys.argv[1] if len(sys.argv) > 1 else "index.html"
FD_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "")
TSDB_KEY = os.environ.get("THESPORTSDB_KEY", "123")  # chave gratuita pública

# letra = a que o Previsor usa no DS e no LGC. casar=False: liga que o Previsor
# não traz em lista própria (os nomes ficam como a API os dá).
LIGAS = {
    "P": dict(nome="Premier League", fonte="fd", id="PL", epoca="2026", total=380, casar=True),
    "E": dict(nome="La Liga", fonte="fd", id="PD", epoca="2026", total=380, casar=True),
    "B": dict(nome="Bundesliga", fonte="fd", id="BL1", epoca="2026", total=306, casar=True),
    "T": dict(nome="Liga Portugal", fonte="fd", id="PPL", epoca="2026", total=306, casar=True),
    "S": dict(nome="Serie A", fonte="fd", id="SA", epoca="2026", total=380, casar=True),
    "F": dict(nome="Ligue 1", fonte="fd", id="FL1", epoca="2026", total=306, casar=True),
    "V": dict(nome="Eredivisie", fonte="fd", id="DED", epoca="2026", total=306, casar=True),
    "C": dict(nome="Champions League", fonte="fd", id="CL", epoca="2026", total=144, casar=True),
    "U": dict(nome="Europa League", fonte="tsdb", id=4481, epoca="2026-2027", total=144, casar=True),
    "D": dict(nome="Superliga (Dinamarca)", fonte="tsdb", id=4340, epoca="2026-2027", total=132, casar=False),
    "O": dict(nome="Noruega", fonte="tsdb", id=4358, epoca="2026", total=240, casar=False),
    "R": dict(nome="Brasileirão", fonte="fd", id="BSA", epoca="2026", total=380, casar=False),
    "J": dict(nome="Bélgica", fonte="tsdb", id=4338, epoca="2026-2027", total=306, casar=True),
}
# Nomes que as APIs dão de forma diferente do Previsor (acrescenta aqui os que o aviso final listar).
ALIAS = {"Sint-Truiden": "Sint-Truidense", "Atleti": "Atlético de Madrid", "M'gladbach": "Borussia Mönchengladbach",
         "Spurs": "Tottenham Hotspur", "Man United": "Manchester United", "Man City": "Manchester City",
         "Como 1907": "Como", "HSV": "Hamburger SV", "Olympique Lyon": "Lyon", "Stade Rennais": "Rennes",
         "Oud-Heverlee Leuven": "OH Leuven", "Union Saint-Gilloise": "Union SG",
         "Acad. Viseu": "Académico de Viseu", "PAE AEK": "AEK Athens", "Shaktar": "Shakhtar Donetsk"}
# Equipas que o Previsor não tem (qualificações europeias): ficam com o nome da API e deixam de dar aviso.
# Serve também para impedir casamentos errados (ex.: Universitatea Cluj != Universitatea Craiova).
MANTER = {"Aluminij", "Dynamo Kyiv", "Qarabağ", "Sheriff Tiraspol", "Universitatea Cluj", "Vestri", "Vojvodina", "Žilina"}
INI, FIM = datetime(2026, 7, 1, tzinfo=timezone.utc), datetime(2027, 2, 1, tzinfo=timezone.utc)
# O Previsor só distingue 2026 e janeiro de 2027: o que vier depois é ignorado.


def get_json(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30) as r:
        return json.load(r)


def fetch_fd(l):
    d = get_json(f"https://api.football-data.org/v4/competitions/{l['id']}/matches?season={l['epoca']}",
                 {"X-Auth-Token": FD_TOKEN})
    time.sleep(7)  # plano gratuito: 10 pedidos por minuto
    out = []
    for m in d.get("matches", []):
        if not m["homeTeam"].get("name") or not m["awayTeam"].get("name"):
            continue  # eliminatórias ainda sem equipas definidas
        ft = (m.get("score") or {}).get("fullTime") or {}
        res = f"{ft['home']}-{ft['away']}" if m.get("status") == "FINISHED" and ft.get("home") is not None else ""
        out.append(dict(dt=datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")), hora=True, res=res,
                        casa=m["homeTeam"].get("shortName") or m["homeTeam"]["name"],
                        fora=m["awayTeam"].get("shortName") or m["awayTeam"]["name"]))
    return out


def fetch_tsdb(l):
    base = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}/"
    urls = [f"eventsseason.php?id={l['id']}&s={l['epoca']}",
            f"eventsnextleague.php?id={l['id']}", f"eventspastleague.php?id={l['id']}"]
    eventos = {}
    for i, u in enumerate(urls):
        try:
            d = get_json(base + u)
        except Exception:
            if i == 0:
                raise
            continue
        for e in d.get("events") or d.get("results") or []:
            if e.get("dateEvent") and e.get("strHomeTeam") and e.get("strAwayTeam"):
                eventos[(e["dateEvent"], e["strHomeTeam"], e["strAwayTeam"])] = e
    out = []
    for e in eventos.values():
        hora = bool(e.get("strTime")) and e["strTime"] != "00:00:00"
        dt = datetime.fromisoformat(f"{e['dateEvent']}T{e.get('strTime') or '00:00:00'}").replace(tzinfo=timezone.utc)
        h, a = e.get("intHomeScore"), e.get("intAwayScore")
        out.append(dict(dt=dt, hora=hora, res=f"{h}-{a}" if h is not None and a is not None else "",
                        casa=e["strHomeTeam"], fora=e["strAwayTeam"]))
    return out


FETCH = {"fd": fetch_fd, "tsdb": fetch_tsdb}


# --- nomes: usa a mesma regra do Previsor para as equipas casarem com as listas dele ---
def carregar_nomes(html):
    al = dict(re.findall(r'(\w+):"([^"]+)"', re.search(r"const AL=\{(.*?)\};", html, re.S).group(1)))
    zonas = [html[html.index("const TOP={"):html.index("const SNAP=")]]
    m = re.search(r"const INTLT=\{.*?\]\};", html, re.S)  # a lista ocupa várias linhas
    if m:
        zonas.append(m.group(0))
    vocab = sorted(set(re.findall(r'"([^"]{2,})"', "\n".join(zonas))))
    return al, vocab


def toks(x, al):
    x = "".join(c for c in unicodedata.normalize("NFD", x) if unicodedata.category(c) != "Mn")
    return [al.get(t, t) for t in x.lower().replace(".", "").split()]


def casar(nome, al, vocab, falhas):
    nome = ALIAS.get(nome, nome)
    if nome in ("PSG", "Vitória SC") or nome in MANTER:
        return nome  # o Previsor já trata estes dois nomes / equipas que ele não tem
    t = toks(nome, al)
    if any(all(x in toks(v, al) for x in t) for v in vocab):
        return nome  # o Previsor já reconhece este nome
    chave = " ".join(t)
    cand = difflib.get_close_matches(chave, [" ".join(toks(v, al)) for v in vocab], n=1, cutoff=0.72)
    if cand:
        return next(v for v in vocab if " ".join(toks(v, al)) == cand[0])
    falhas.add(nome)
    return nome


def linhas(letra, l, jogos, al, vocab, falhas):
    out = []
    for j in sorted(jogos, key=lambda x: x["dt"]):
        if not INI <= j["dt"] < FIM:
            continue
        c, f = j["casa"], j["fora"]
        if l["casar"]:
            c, f = casar(c, al, vocab, falhas), casar(f, al, vocab, falhas)
        else:
            c, f = ALIAS.get(c, c), ALIAS.get(f, f)
        d = j["dt"].strftime("%m-%dT%H:%MZ" if j["hora"] else "%m-%d")
        out.append(f"{letra}|{d}|{c}|{f}|{j['res']}")
    return out


def main():
    html = open(HTML, encoding="utf-8").read()
    m = re.search(r"(const DS=`)(.*?)(`\.split\()", html, re.S)
    if not m or "const TOP={" not in html or "const SNAP=" not in html:
        print("Este não parece o index.html do Previsor. Nada foi alterado.", file=sys.stderr)
        return 1
    al, vocab = carregar_nomes(html)
    atuais = {}
    for x in m.group(2).split("\n"):
        p = x.split("|")
        if len(p) >= 4 and p[0] in LIGAS:
            atuais.setdefault(p[0], {})[(p[2], p[3])] = x
    novas, falhas = [], set()
    for letra, l in LIGAS.items():
        try:
            jogos = FETCH[l["fonte"]](l)
        except Exception as ex:
            print(f"[{l['nome']}] ERRO: {ex}. Nada foi alterado.", file=sys.stderr)
            return 1
        print(f"[{l['nome']}] {len(jogos)} jogos (esperados ~{l['total']})")
        if len(jogos) < l["total"] * 0.9:
            print("  AVISO: menos jogos do que o esperado (o plano gratuito pode limitar).")
        ln = linhas(letra, l, jogos, al, vocab, falhas)
        if len(jogos) < l["total"] * 0.9:
            # A API devolveu poucos jogos: junta aos que já existem em vez de os apagar.
            d = dict(atuais.get(letra, {}))
            for x in ln:
                p = x.split("|")
                d[(p[2], p[3])] = x
            ln = list(d.values())
            print(f"  Juntei aos jogos que já existiam: {len(ln)} no total.")
        novas += ln
    mantidas = [x for x in m.group(2).split("\n") if x[:2] not in tuple(k + "|" for k in LIGAS)]
    novo = html[:m.start()] + m.group(1) + "\n".join(mantidas + novas) + m.group(3) + html[m.end():]
    # Os últimos 5 guardados ficariam parados: passam a vir do calendário atualizado.
    novo, n = re.subn(r"l5:\{.*?\}\};\n", "l5:{}};\n", novo, count=1, flags=re.S)
    shutil.copy(HTML, HTML + ".bak")
    open(HTML, "w", encoding="utf-8").write(novo)
    print(f"{HTML} atualizado: {len(novas)} jogos (cópia em {HTML}.bak).")
    if falhas:
        print("Nomes sem correspondência no Previsor (acrescenta ao ALIAS do script):", ", ".join(sorted(falhas)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
    "J": dict(nome="Bélgica", fonte="tsdb", id=4338, epoca="2026-2027", total=306, casar=True),
}
# Nomes que as APIs dão de forma diferente do Previsor (acrescenta aqui os que o aviso final listar).
ALIAS = {"Sint-Truiden": "Sint-Truidense", "Atleti": "Atlético de Madrid", "M'gladbach": "Borussia Mönchengladbach",
         "Spurs": "Tottenham Hotspur", "Man United": "Manchester United", "Man City": "Manchester City",
         "Como 1907": "Como", "HSV": "Hamburger SV", "Olympique Lyon": "Lyon", "Stade Rennais": "Rennes",
         "Oud-Heverlee Leuven": "OH Leuven", "Union Saint-Gilloise": "Union SG",
         "Acad. Viseu": "Académico de Viseu", "PAE AEK": "AEK Athens", "Shaktar": "Shakhtar Donetsk"}
# Equipas que o Previsor não tem (qualificações europeias): ficam com o nome da API e deixam de dar aviso.
# Serve também para impedir casamentos errados (ex.: Universitatea Cluj != Universitatea Craiova).
MANTER = {"Aluminij", "Dynamo Kyiv", "Qarabağ", "Sheriff Tiraspol", "Universitatea Cluj", "Vestri", "Vojvodina", "Žilina"}
INI, FIM = datetime(2026, 7, 1, tzinfo=timezone.utc), datetime(2027, 2, 1, tzinfo=timezone.utc)
# O Previsor só distingue 2026 e janeiro de 2027: o que vier depois é ignorado.


def get_json(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30) as r:
        return json.load(r)


def fetch_fd(l):
    d = get_json(f"https://api.football-data.org/v4/competitions/{l['id']}/matches?season={l['epoca']}",
                 {"X-Auth-Token": FD_TOKEN})
    time.sleep(7)  # plano gratuito: 10 pedidos por minuto
    out = []
    for m in d.get("matches", []):
        if not m["homeTeam"].get("name") or not m["awayTeam"].get("name"):
            continue  # eliminatórias ainda sem equipas definidas
        ft = (m.get("score") or {}).get("fullTime") or {}
        res = f"{ft['home']}-{ft['away']}" if m.get("status") == "FINISHED" and ft.get("home") is not None else ""
        out.append(dict(dt=datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")), hora=True, res=res,
                        casa=m["homeTeam"].get("shortName") or m["homeTeam"]["name"],
                        fora=m["awayTeam"].get("shortName") or m["awayTeam"]["name"]))
    return out


def fetch_tsdb(l):
    base = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}/"
    urls = [f"eventsseason.php?id={l['id']}&s={l['epoca']}",
            f"eventsnextleague.php?id={l['id']}", f"eventspastleague.php?id={l['id']}"]
    eventos = {}
    for i, u in enumerate(urls):
        try:
            d = get_json(base + u)
        except Exception:
            if i == 0:
                raise
            continue
        for e in d.get("events") or d.get("results") or []:
            if e.get("dateEvent") and e.get("strHomeTeam") and e.get("strAwayTeam"):
                eventos[(e["dateEvent"], e["strHomeTeam"], e["strAwayTeam"])] = e
    out = []
    for e in eventos.values():
        hora = bool(e.get("strTime")) and e["strTime"] != "00:00:00"
        dt = datetime.fromisoformat(f"{e['dateEvent']}T{e.get('strTime') or '00:00:00'}").replace(tzinfo=timezone.utc)
        h, a = e.get("intHomeScore"), e.get("intAwayScore")
        out.append(dict(dt=dt, hora=hora, res=f"{h}-{a}" if h is not None and a is not None else "",
                        casa=e["strHomeTeam"], fora=e["strAwayTeam"]))
    return out


FETCH = {"fd": fetch_fd, "tsdb": fetch_tsdb}


# --- nomes: usa a mesma regra do Previsor para as equipas casarem com as listas dele ---
def carregar_nomes(html):
    al = dict(re.findall(r'(\w+):"([^"]+)"', re.search(r"const AL=\{(.*?)\};", html, re.S).group(1)))
    zonas = [html[html.index("const TOP={"):html.index("const SNAP=")]]
    m = re.search(r"const INTLT=\{.*?\]\};", html, re.S)  # a lista ocupa várias linhas
    if m:
        zonas.append(m.group(0))
    vocab = sorted(set(re.findall(r'"([^"]{2,})"', "\n".join(zonas))))
    return al, vocab


def toks(x, al):
    x = "".join(c for c in unicodedata.normalize("NFD", x) if unicodedata.category(c) != "Mn")
    return [al.get(t, t) for t in x.lower().replace(".", "").split()]


def casar(nome, al, vocab, falhas):
    nome = ALIAS.get(nome, nome)
    if nome in ("PSG", "Vitória SC") or nome in MANTER:
        return nome  # o Previsor já trata estes dois nomes / equipas que ele não tem
    t = toks(nome, al)
    if any(all(x in toks(v, al) for x in t) for v in vocab):
        return nome  # o Previsor já reconhece este nome
    chave = " ".join(t)
    cand = difflib.get_close_matches(chave, [" ".join(toks(v, al)) for v in vocab], n=1, cutoff=0.72)
    if cand:
        return next(v for v in vocab if " ".join(toks(v, al)) == cand[0])
    falhas.add(nome)
    return nome


def linhas(letra, l, jogos, al, vocab, falhas):
    out = []
    for j in sorted(jogos, key=lambda x: x["dt"]):
        if not INI <= j["dt"] < FIM:
            continue
        c, f = j["casa"], j["fora"]
        if l["casar"]:
            c, f = casar(c, al, vocab, falhas), casar(f, al, vocab, falhas)
        else:
            c, f = ALIAS.get(c, c), ALIAS.get(f, f)
        d = j["dt"].strftime("%m-%dT%H:%MZ" if j["hora"] else "%m-%d")
        out.append(f"{letra}|{d}|{c}|{f}|{j['res']}")
    return out


def main():
    html = open(HTML, encoding="utf-8").read()
    m = re.search(r"(const DS=`)(.*?)(`\.split\()", html, re.S)
    if not m or "const TOP={" not in html or "const SNAP=" not in html:
        print("Este não parece o index.html do Previsor. Nada foi alterado.", file=sys.stderr)
        return 1
    al, vocab = carregar_nomes(html)
    atuais = {}
    for x in m.group(2).split("\n"):
        p = x.split("|")
        if len(p) >= 4 and p[0] in LIGAS:
            atuais.setdefault(p[0], {})[(p[2], p[3])] = x
    novas, falhas = [], set()
    for letra, l in LIGAS.items():
        try:
            jogos = FETCH[l["fonte"]](l)
        except Exception as ex:
            print(f"[{l['nome']}] ERRO: {ex}. Nada foi alterado.", file=sys.stderr)
            return 1
        print(f"[{l['nome']}] {len(jogos)} jogos (esperados ~{l['total']})")
        if len(jogos) < l["total"] * 0.9:
            print("  AVISO: menos jogos do que o esperado (o plano gratuito pode limitar).")
        ln = linhas(letra, l, jogos, al, vocab, falhas)
        if len(jogos) < l["total"] * 0.9:
            # A API devolveu poucos jogos: junta aos que já existem em vez de os apagar.
            d = dict(atuais.get(letra, {}))
            for x in ln:
                p = x.split("|")
                d[(p[2], p[3])] = x
            ln = list(d.values())
            print(f"  Juntei aos jogos que já existiam: {len(ln)} no total.")
        novas += ln
    mantidas = [x for x in m.group(2).split("\n") if x[:2] not in tuple(k + "|" for k in LIGAS)]
    novo = html[:m.start()] + m.group(1) + "\n".join(mantidas + novas) + m.group(3) + html[m.end():]
    # Os últimos 5 guardados ficariam parados: passam a vir do calendário atualizado.
    novo, n = re.subn(r"l5:\{.*?\}\};\n", "l5:{}};\n", novo, count=1, flags=re.S)
    shutil.copy(HTML, HTML + ".bak")
    open(HTML, "w", encoding="utf-8").write(novo)
    print(f"{HTML} atualizado: {len(novas)} jogos (cópia em {HTML}.bak).")
    if falhas:
        print("Nomes sem correspondência no Previsor (acrescenta ao ALIAS do script):", ", ".join(sorted(falhas)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
