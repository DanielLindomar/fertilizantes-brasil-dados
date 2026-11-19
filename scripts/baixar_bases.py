# -*- coding: utf-8 -*-
"""
Baixa as bases abertas mapeadas no catálogo
(Mapeamento_dados_uso_fertilizantes/Mapeamento_dados_uso_fertilizantes.xlsx)
e registra cada arquivo no manifesto dados/MANIFESTO.csv.

Uso (a partir de qualquer pasta):
    python baixar_bases.py                      # todas as fontes
    python baixar_bases.py --fontes sidra,bcb   # só algumas
    python baixar_bases.py --data 2026-11-19    # força o nome da pasta de versão

Fontes disponíveis: faostat, anda, ipeadata, sidra, comex, bcb, bancomundial, documentos

Convenções
- dados/brutos/<fonte>/<AAAA-MM-DD>/  : arquivos como vieram da fonte. Para APIs,
  a resposta JSON é convertida em CSV sem alterar valores (códigos + valor).
- dados/tratados/<fonte>/<AAAA-MM-DD>/: recortes derivados (ex.: só Brasil) para uso direto.
- CSV em UTF-8, separador vírgula, ponto decimal. Valores especiais do SIDRA
  ("-", "..", "...", "X") são mantidos como texto.
- Cada execução cria uma nova pasta datada; versões antigas não são apagadas.

Requer Python 3.9+ e, para o tratamento de PDFs e planilhas, pdfplumber e openpyxl.
"""
import argparse, csv, datetime, hashlib, io, json, os, re, sys, time, urllib.parse, urllib.request, zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../dados
UA = {"User-Agent": "Mozilla/5.0 (compatible; dados-pesquisa-fertilizantes/1.0)"}
MANIFESTO = os.path.join(BASE, "MANIFESTO.csv")
MAN_COLS = ["id_catalogo", "fonte", "arquivo", "descricao", "origem", "data_download", "bytes", "sha256", "linhas", "observacao"]
REGISTROS = []
HOJE = datetime.date.today().isoformat()

UFS = [11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53]


# ----------------------------------------------------------------- utilidades
def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def baixar(url, data=None, headers=None, tentativas=4, espera=3, timeout=300):
    h = dict(UA)
    if headers:
        h.update(headers)
    for t in range(1, tentativas + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if t == tentativas:
                raise
            log(f"  tentativa {t} falhou ({e!r:.120}); repetindo")
            time.sleep(espera * t)


def pasta(tipo, fonte):
    p = os.path.join(BASE, tipo, fonte, HOJE)
    os.makedirs(p, exist_ok=True)
    return p


def registrar(id_cat, fonte, caminho, descricao, origem, linhas="", obs=""):
    with open(caminho, "rb") as f:
        b = f.read()
    REGISTROS.append({
        "id_catalogo": id_cat, "fonte": fonte,
        "arquivo": os.path.relpath(caminho, BASE).replace("\\", "/"),
        "descricao": descricao, "origem": origem, "data_download": HOJE,
        "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(),
        "linhas": linhas, "observacao": obs,
    })


def salvar_bytes(caminho, b):
    with open(caminho, "wb") as f:
        f.write(b)


def salvar_csv(caminho, cabecalho, linhas):
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cabecalho)
        n = 0
        for r in linhas:
            w.writerow(r)
            n += 1
    return n


def gravar_manifesto():
    antigos = []
    if os.path.exists(MANIFESTO):
        with open(MANIFESTO, encoding="utf-8") as f:
            antigos = list(csv.DictReader(f))
    novos = {r["arquivo"] for r in REGISTROS}
    todos = [r for r in antigos if r["arquivo"] not in novos] + REGISTROS
    todos.sort(key=lambda r: (r["fonte"], r["arquivo"]))
    with open(MANIFESTO, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MAN_COLS)
        w.writeheader()
        w.writerows(todos)
    log(f"manifesto: {len(REGISTROS)} arquivos registrados nesta execução ({len(todos)} no total)")


# ----------------------------------------------------------------- FAOSTAT
FAO = {"RFN": "A01", "RFB": "A02", "RA": "A03", "ESB": "E01", "EMN": "E02", "RFM": "G03"}


def faostat():
    log("FAOSTAT")
    cat = json.loads(baixar("https://bulks-faostat.fao.org/production/datasets_E.json").decode("utf-8"))
    ds = {d["DatasetCode"]: d for d in cat["Datasets"]["Dataset"]}
    pb, pt = pasta("brutos", "faostat"), pasta("tratados", "faostat")
    for code, idc in FAO.items():
        d = ds[code]
        url = d["FileLocation"]
        nome = url.rsplit("/", 1)[-1]
        log(f"  {code}: {nome}")
        b = baixar(url)
        cam = os.path.join(pb, nome)
        salvar_bytes(cam, b)
        registrar(idc, "faostat", cam, f"FAOSTAT {code} – {d['DatasetName']} (arquivo global, atualização {d.get('DateUpdate', '')[:10]})", url)
        # recorte Brasil (leitura em fluxo: a matriz de comércio é grande)
        camt = os.path.join(pt, f"faostat_{code}_brasil.csv")
        with zipfile.ZipFile(cam) as z:
            principal = [n for n in z.namelist() if n.endswith("All_Data_(Normalized).csv")][0]
            with z.open(principal) as fz:
                rd = csv.reader(io.TextIOWrapper(fz, encoding="latin-1", newline=""))
                cab = next(rd)
                cols_pais = [i for i, c in enumerate(cab) if c in ("Area", "Reporter Countries", "Partner Countries")]
                n = salvar_csv(camt, cab, (r for r in rd if any(r[i] == "Brazil" for i in cols_pais)))
        del b
        obs = "Linhas em que o Brasil é declarante ou parceiro." if code == "RFM" else "Linhas com Area = Brazil."
        registrar(idc, "faostat", camt, f"FAOSTAT {code}: recorte Brasil", f"{url} -> {principal}", n, obs)


# ----------------------------------------------------------------- ANDA
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]
SECOES = [("Entregues ao Mercado", "entregas"), ("Produção Nacional", "producao"),
          ("Importação de Fertilizantes", "importacao"), ("Exportações de Fertilizantes", "exportacao")]


def _parse_pi(caminho):
    """Extrai as quatro tabelas mensais de um PDF 'Principais Indicadores' da ANDA."""
    import pdfplumber
    with pdfplumber.open(caminho) as pdf:
        txt = "\n".join(p.extract_text() or "" for p in pdf.pages)
    out, secao, anos = [], None, []
    for ln in txt.split("\n"):
        s = ln.strip()
        for chave, nome in SECOES:
            if chave in s:
                secao, anos = nome, []
        if secao and re.match(r"^(19|20)\d{2}(\s+(19|20)\d{2})+", s):
            # ex.: "2022 2023 2024 2025 2025x2024" -> [2022, 2023, 2024, 2025]
            anos = [int(t) for t in s.split() if re.fullmatch(r"(19|20)\d{2}", t)]
            continue
        if secao and anos:
            # "Janeiro a Agosto" é acumulado, não o mês de janeiro
            m = re.match(r"^(" + "|".join(MESES) + r")\s+(?!a\s)(.*)$", s)
            if m:
                nums = [int(x.replace(".", "")) for x in re.findall(r"(?<![\d,])\d{1,3}(?:\.\d{3})+(?![\d,%])|(?<![\d.,])\d{1,6}(?![\d.,%])", m.group(2))]
                for ano, v in zip(anos, nums):
                    out.append((secao, ano, MESES.index(m.group(1)) + 1, v))
            if s.startswith("Relações de Troca"):
                secao, anos = None, []
    return out


def anda():
    log("ANDA")
    pg = baixar("https://anda.org.br/recursos/").decode("utf-8", "ignore")
    links = sorted(set(re.findall(r"https?://anda\.org\.br/wp-content/uploads/[^\"'\s]+\.(?:pdf|xlsx)", pg)))
    pb, pt = pasta("brutos", "anda"), pasta("tratados", "anda")
    vint = []
    for url in links:
        nome = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        cam = os.path.join(pb, nome)
        salvar_bytes(cam, baixar(url))
        if nome.lower().endswith(".xlsx"):
            idc, desc = "A05", "ANDA – Macro indicadores (planilha do mês)"
        elif nome.lower().startswith("comentarios"):
            idc, desc = "B05", "ANDA – Comentários (release do mês: entregas acumuladas no ano pelas principais UFs, portos, produção e importação)"
        else:
            idc, desc = "A04", "ANDA – Principais Indicadores do Setor de Fertilizantes (PDF)"
        registrar(idc, "anda", cam, desc, url,
                  obs="O site só mantém o mês corrente; rodar todo mês para acumular a série por UF." if idc == "B05" else "")
        log(f"  {nome}")
        if nome.startswith("Principais_Indicadores") and nome.endswith(".pdf"):
            try:
                for secao, ano, mes, v in _parse_pi(cam):
                    vint.append([nome, secao, ano, mes, v])
            except Exception as e:  # noqa: BLE001
                log(f"  aviso: não consegui extrair {nome}: {e!r:.100}")
    if vint:
        camt = os.path.join(pt, "anda_principais_indicadores_por_edicao.csv")
        n = salvar_csv(camt, ["edicao_arquivo", "serie", "ano", "mes", "toneladas_produto"], vint)
        registrar("A04", "anda", camt, "Tabelas mensais extraídas de cada edição dos Principais Indicadores (permite comparar versões)",
                  "https://anda.org.br/recursos/", n, "Extração automática dos PDFs; conferir contra o PDF antes de citar.")


# ----------------------------------------------------------------- Ipeadata
IPEA = {"ANDA12_VFERTILIZ12": "A06", "ANDA12_MFERTILIZ12": "A06", "ANDA12_PFERTILIZ12": "A06", "ANDA12_NPKFERTILIZ12": "A06",
        "ANDA_VFERTILIZ": "A06", "ANDA_MFERTILIZ": "A06", "ANDA_PFERTILIZ": "A06",
        "GAC12_TCERMT12": "G05", "GAC12_TCERXT12": "G05"}


def ipeadata():
    log("Ipeadata")
    pb = pasta("brutos", "ipeadata")
    meta, vals = [], []
    for code in IPEA:
        m = json.loads(baixar(f"http://www.ipeadata.gov.br/api/odata4/Metadados('{code}')").decode("utf-8"))["value"][0]
        meta.append([code, m["SERNOME"], m.get("PERNOME"), m.get("UNINOME"), m.get("FNTSIGLA"), m.get("SERSTATUS"), m.get("SERATUALIZACAO")])
        v = json.loads(baixar(f"http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='{code}')").decode("utf-8"))["value"]
        vals += [[code, x["VALDATA"][:10], x["VALVALOR"]] for x in v if x["VALVALOR"] is not None]
        time.sleep(0.5)
    c1 = os.path.join(pb, "ipeadata_metadados.csv")
    salvar_csv(c1, ["codigo", "nome", "periodicidade", "unidade", "fonte", "status", "atualizacao"], meta)
    registrar("A06", "ipeadata", c1, "Metadados das séries do Ipeadata (ANDA e câmbio efetivo real)", "http://www.ipeadata.gov.br/api/odata4/Metadados", len(meta))
    c2 = os.path.join(pb, "ipeadata_series.csv")
    n = salvar_csv(c2, ["codigo", "data", "valor"], vals)
    registrar("A06", "ipeadata", c2, "Valores das séries: ANDA mensal/anual (t de produto) e câmbio efetivo real GAC12 (inativo)",
              "http://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='...')", n, "Séries GAC12_* estão marcadas como inativas (fim em 2024-12).")


# ----------------------------------------------------------------- IBGE / SIDRA
MUN = [f"n6/in n3 {uf}" for uf in UFS]
BR_UF = ["n1/all", "n3/all"]
# (id_catalogo, tabela, arquivo, niveis, variaveis, classificacoes, periodos)
SIDRA = [
    ("B03", 768, "ids_768_kgha_nutriente_brasil", ["n1/all"], "all", "c12899/all", ["all"]),
    ("B02", 769, "ids_769_area_entregas_br_gr_uf", ["n1/all", "n2/all", "n3/all"], "all", "", ["all"]),
    ("B01", 770, "ids_770_entregas_nutriente_br_gr_uf", ["n1/all", "n2/all", "n3/all"], "all", "c12899/all", ["all"]),
    ("C01", 6847, "censo2017_6847_uso_adubacao_br_uf", BR_UF, "183", "c829/all/c12522/all", ["all"]),
    ("C01", 6847, "censo2017_6847_uso_adubacao_municipios", MUN, "183", "c829/46302/c12522/all", ["all"]),
    ("C02", 6849, "censo2017_6849_uso_calcario_br_uf", BR_UF, "183", "c829/all/c12549/all", ["all"]),
    ("C02", 6849, "censo2017_6849_uso_calcario_municipios", MUN, "183", "c829/46302/c12549/all", ["all"]),
    ("C03", 6899, "censo2017_6899_despesas_br_uf", BR_UF, "2,1996", "c829/all/c210/all", ["all"]),
    ("C03", 6899, "censo2017_6899_despesas_municipios", MUN, "2,1996", "c829/46302/c210/all", ["all"]),
    ("C03", 6900, "censo2017_6900_despesas_grupos_area_br_uf", BR_UF, "2,1996", "c210/all/c220/all", ["all"]),
    ("C04", 833, "censo2006_833_despesas_br_uf", BR_UF, "2,1996", "c210/all/c12517/all", ["all"]),
    ("C04", 833, "censo2006_833_despesas_municipios", MUN, "2,1996", "c210/all", ["all"]),
    ("C05", 1249, "censo2006_1249_produtos_adubacao_br_uf", BR_UF, "183,184", "c12586/all/c12588/all", ["all"]),
    ("C05", 1249, "censo2006_1249_produtos_adubacao_municipios", MUN, "183,184", "c12586/all", ["all"]),
    ("C06", 864, "censo2006_864_uso_adubacao_br_uf", BR_UF, "183", "c12522/all", ["all"]),
    ("C06", 864, "censo2006_864_uso_adubacao_municipios", MUN, "183", "c12522/all", ["all"]),
    ("C07", 825, "censo2006_825_lavoura_temporaria_adubacao_br_uf", [f"{n}|v{v}" for n in BR_UF for v in (183, 214, 215, 216)], None, "c226/all/c12522/all", ["all"]),
    ("F01", 5457, "pam_5457_lavouras_br_uf", BR_UF, "8331,216,214,215", "c782/all",
     ["1974-1981", "1982-1989", "1990-1997", "1998-2005", "2006-2013", "2014-2021", "2022-2030"]),
    ("F02", 3939, "ppm_3939_rebanhos_br_uf", BR_UF, "105", "c79/all", ["all"]),
    ("F02", 74, "ppm_74_producao_animal_br_uf", BR_UF, "106,215", "c80/all", ["all"]),
    ("F03", 6588, "lspa_6588_safra_mensal_brasil", ["n1/all"], "109,216,35", "c48/all", ["all"]),
]


def _sidra_consulta(tab, nivel, var, cls, per):
    if "|v" in nivel:
        nivel, var = nivel.split("|v")
    partes = [f"t/{tab}", nivel, f"v/{var}", f"p/{per}"] + ([cls] if cls else [])
    caminho = "/".join(partes).replace(" ", "%20")
    return f"https://apisidra.ibge.gov.br/values/{caminho}?formato=json"


def sidra():
    log("IBGE/SIDRA")
    pb = pasta("brutos", "ibge_sidra")
    dic = {}
    for idc, tab, arq, niveis, var, cls, pers in SIDRA:
        rows, cab = [], None
        consultas = [_sidra_consulta(tab, n, var, cls, p) for n in niveis for p in pers]
        for url in consultas:
            txt = baixar(url).decode("utf-8")
            if not txt.lstrip().startswith("["):
                raise RuntimeError(f"SIDRA recusou {url}: {txt[:200]}")
            d = json.loads(txt)
            h = d[0]
            dims = sorted({k[:-1] for k in h if re.match(r"D\d+C$", k)}, key=lambda x: int(x[1:]))
            if cab is None:
                def slug(s):
                    s = re.sub(r"\s*\(Código\)\s*$", "", s)
                    s = s.lower()
                    for a, b in (("áàâã", "a"), ("éê", "e"), ("í", "i"), ("óôõ", "o"), ("ú", "u"), ("ç", "c")):
                        s = re.sub("[" + a + "]", b, s)
                    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40]
                cab = ["nivel_cod", "unidade"] + ["local_cod", "local_nome"] + [slug(h[x + "C"]) + "_cod" for x in dims[1:]] + ["valor"]
                dimnomes = [h[x + "N"] for x in dims[1:]]
            for r in d[1:]:
                rows.append([r["NC"], r["MN"], r["D1C"], r["D1N"]] + [r[x + "C"] for x in dims[1:]] + [r["V"]])
                for x, nome in zip(dims[1:], dimnomes):
                    dic[(tab, nome, r[x + "C"])] = r[x + "N"]
            time.sleep(0.4)
        cam = os.path.join(pb, f"{arq}.csv")
        n = salvar_csv(cam, cab, rows)
        registrar(idc, "ibge_sidra", cam, f"SIDRA tabela {tab}: {arq}", consultas[0] + (f" (+{len(consultas) - 1} consultas)" if len(consultas) > 1 else ""), n,
                  "Códigos de variáveis e categorias em sidra_dicionario.csv. Chave territorial: nivel_cod + local_cod.")
        log(f"  {arq}: {n} linhas ({len(consultas)} consultas)")
    cam = os.path.join(pb, "sidra_dicionario.csv")
    n = salvar_csv(cam, ["tabela", "dimensao", "codigo", "nome"], [[t, d, c, nm] for (t, d, c), nm in sorted(dic.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2]))])
    registrar("", "ibge_sidra", cam, "Dicionário de códigos (variáveis, períodos e categorias) das tabelas SIDRA baixadas", "https://apisidra.ibge.gov.br/", n)


# ----------------------------------------------------------------- Comex Stat
COMEX_API = "https://api-comexstat.mdic.gov.br"
MATERIAS_PRIMAS = ["2510", "2503", "2814", "2809", "2807"]  # rocha fosfática, enxofre, amônia, ác. fosfórico, ác. sulfúrico


def _comex_post(endpoint, body):
    b = baixar(f"{COMEX_API}/{endpoint}?language=pt", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
    d = json.loads(b.decode("utf-8"))
    lst = d["data"]["list"] if isinstance(d.get("data"), dict) else d.get("data")
    if lst is None:
        raise RuntimeError(f"Comex Stat sem dados: {str(d)[:200]}")
    return lst


def comex():
    log("Comex Stat")
    pb = pasta("brutos", "comex_stat")
    upd = json.loads(baixar(f"{COMEX_API}/general/dates/updated").decode("utf-8"))["data"]
    ano_fim, mes_fim = int(upd["year"]), int(upd["monthNumber"])
    met_imp = ["metricFOB", "metricKG", "metricStatistic", "metricFreight", "metricInsurance", "metricCIF"]
    blocos = [
        ("B06", "import", [{"filter": "chapter", "values": ["31"]}], met_imp, "comex_importacao_cap31_ncm_pais_uf_mensal",
         "Importação do capítulo 31 (adubos), por NCM, país de origem e UF do produto, mensal"),
        ("B06", "import", [{"filter": "heading", "values": MATERIAS_PRIMAS}], met_imp, "comex_importacao_materias_primas_ncm_pais_uf_mensal",
         "Importação de matérias-primas (SH4 2510, 2503, 2814, 2809, 2807), por NCM, país e UF do produto, mensal"),
        ("B06", "export", [{"filter": "chapter", "values": ["31"]}], ["metricFOB", "metricKG"], "comex_exportacao_cap31_ncm_pais_uf_mensal",
         "Exportação do capítulo 31, por NCM, país de destino e UF do produto, mensal"),
    ]
    for idc, flow, filt, met, arq, desc in blocos:
        rows, cab = [], None
        for ano in range(1997, ano_fim + 1):
            fim = f"{ano}-{mes_fim:02d}" if ano == ano_fim else f"{ano}-12"
            body = {"flow": flow, "monthDetail": True, "period": {"from": f"{ano}-01", "to": fim},
                    "filters": filt, "details": ["ncm", "country", "state"], "metrics": met}
            lst = _comex_post("general", body)
            if lst and cab is None:
                cab = list(lst[0].keys())
            rows += [[x.get(k) for k in cab] for x in lst]
            time.sleep(1.5)
        cam = os.path.join(pb, f"{arq}_1997_{ano_fim}.csv")
        n = salvar_csv(cam, cab, rows)
        registrar(idc, "comex_stat", cam, desc + f", 1997-01 a {ano_fim}-{mes_fim:02d}", f"POST {COMEX_API}/general (uma consulta por ano)", n,
                  "UF do produto: na importação, UF de destino declarada da mercadoria (não é a UF de aplicação final).")
        log(f"  {arq}: {n} linhas")
    # dados históricos (NBM), 1989-1996
    nbm = json.loads(baixar(f"{COMEX_API}/tables/nbm?language=pt").decode("utf-8"))["data"]["list"]
    cods = [x["coNbm"] for x in nbm if x["coNbm"][:2] == "31" or x["coNbm"][:4] in MATERIAS_PRIMAS]
    rows, cab = [], None
    for ano in range(1989, 1997):
        body = {"flow": "import", "monthDetail": True, "period": {"from": f"{ano}-01", "to": f"{ano}-12"},
                "filters": [{"filter": "nbm", "values": cods}], "details": ["nbm", "country"], "metrics": ["metricFOB", "metricKG"]}
        lst = _comex_post("historical-data", body)
        if lst and cab is None:
            cab = list(lst[0].keys())
        rows += [[x.get(k) for k in cab] for x in lst]
        time.sleep(1.5)
    cam = os.path.join(pb, "comex_historico_nbm_importacao_fertilizantes_materias_primas_1989_1996.csv")
    n = salvar_csv(cam, cab, rows)
    registrar("B06", "comex_stat", cam, "Importação em NBM (capítulo 31 e matérias-primas), por mercadoria e país, mensal, 1989-1996",
              f"POST {COMEX_API}/historical-data", n, "A API devolve a descrição NBM sem o código; usar a tabela NBM para casar. Algumas linhas vêm com peso (metricKG) vazio na própria API.")
    cam = os.path.join(pb, "comex_tabela_nbm_fertilizantes.csv")
    n = salvar_csv(cam, ["coNbm", "nbm"], [[x["coNbm"], x["nbm"]] for x in nbm if x["coNbm"] in cods])
    registrar("B06", "comex_stat", cam, "Tabela NBM: códigos do capítulo 31 e das matérias-primas", f"{COMEX_API}/tables/nbm", n)
    # tabelas auxiliares
    for tab, arq in (("ncm", "comex_tabela_ncm"), ("countries", "comex_tabela_paises"), ("uf", "comex_tabela_uf")):
        d = json.loads(baixar(f"{COMEX_API}/tables/{tab}?language=pt").decode("utf-8"))["data"]
        lst = d["list"] if isinstance(d, dict) else d
        cab = list(lst[0].keys())
        cam = os.path.join(pb, f"{arq}.csv")
        n = salvar_csv(cam, cab, [[x.get(k) for k in cab] for x in lst])
        registrar("B06", "comex_stat", cam, f"Tabela auxiliar do Comex Stat: {tab}", f"{COMEX_API}/tables/{tab}", n)


# ----------------------------------------------------------------- Banco Central (SGS)
BCB = {11752: "Índice da taxa de câmbio real efetiva (IPCA) - Jun/1994=100",
       11753: "Índice da taxa de câmbio real (IPCA) - Jun/1994=100 - Dólar americano",
       3696: "Taxa de câmbio - Livre - Dólar americano (venda) - Fim de período - mensal",
       3698: "Taxa de câmbio - Livre - Dólar americano (venda) - Média de período - mensal",
       1: "Taxa de câmbio - Livre - Dólar americano (venda) - diário"}


def bcb():
    log("Banco Central (SGS)")
    pb = pasta("brutos", "bcb_sgs")
    rows = []
    hoje = datetime.date.today()
    for cod, nome in BCB.items():
        ini = datetime.date(1980, 1, 1)
        while ini <= hoje:
            fim = min(datetime.date(ini.year + 9, 12, 31), hoje)
            url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados?formato=json"
                   f"&dataInicial={ini:%d/%m/%Y}&dataFinal={fim:%d/%m/%Y}")
            try:
                d = json.loads(baixar(url, tentativas=3).decode("utf-8"))
            except Exception:  # janela sem dados devolve 404
                d = []
            if isinstance(d, list):
                for x in d:
                    dd, mm, aa = x["data"].split("/")
                    rows.append([cod, nome, f"{aa}-{mm}-{dd}", x["valor"]])
            ini = datetime.date(ini.year + 10, 1, 1)
            time.sleep(0.5)
    cam = os.path.join(pb, "bcb_sgs_cambio.csv")
    n = salvar_csv(cam, ["serie", "nome", "data", "valor"], rows)
    registrar("G04", "bcb_sgs", cam, "Câmbio real efetivo (11752), real bilateral (11753) e dólar comercial (1, 3696, 3698)",
              "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados (janelas de 10 anos)", n)
    log(f"  {n} linhas")


# ----------------------------------------------------------------- Banco Mundial (Pink Sheet)
def bancomundial():
    log("Banco Mundial (Pink Sheet)")
    pb, pt = pasta("brutos", "banco_mundial"), pasta("tratados", "banco_mundial")
    pg = baixar("https://www.worldbank.org/en/research/commodity-markets").decode("utf-8", "ignore")
    links = sorted(set(re.findall(r"https?://[^\"'\s]*CMO-Historical-Data-(?:Monthly|Annual)\.xlsx", pg)))
    mensal = None
    for url in links:
        nome = url.rsplit("/", 1)[-1]
        cam = os.path.join(pb, nome)
        salvar_bytes(cam, baixar(url))
        registrar("G01", "banco_mundial", cam, f"World Bank Commodity Price Data (Pink Sheet): {nome}", url)
        if "Monthly" in nome:
            mensal = cam
    if mensal:
        import openpyxl
        wb = openpyxl.load_workbook(mensal, read_only=True, data_only=True)
        ws = wb["Monthly Prices"]
        linhas = list(ws.iter_rows(values_only=True))
        hi = next(i for i, r in enumerate(linhas[:15]) if r and any(isinstance(c, str) and c.strip().startswith("Urea") for c in r))
        nomes, unid = linhas[hi], linhas[hi + 1]
        alvo = ["Natural gas, US", "Natural gas, Europe", "Natural gas index", "Soybeans", "Maize",
                "Phosphate rock", "DAP", "TSP", "Urea", "Potassium chloride"]
        idx = [j for j, c in enumerate(nomes) if isinstance(c, str) and any(c.strip().rstrip("*").strip() == a for a in alvo)]
        cab = ["mes"] + [f"{nomes[j].strip().rstrip('*').strip()} {unid[j]}" for j in idx]
        dados = [[r[0]] + [r[j] for j in idx] for r in linhas[hi + 2:] if r and isinstance(r[0], str) and re.match(r"^\d{4}M\d{2}$", r[0])]
        camt = os.path.join(pt, "pinksheet_fertilizantes_gas_graos_mensal.csv")
        n = salvar_csv(camt, cab, dados)
        registrar("G01", "banco_mundial", camt, "Pink Sheet mensal: ureia, DAP, TSP, KCl, rocha fosfática, gás natural, soja e milho",
                  mensal, n, "KCl: FOB Vancouver até 2019-12, CFR Brasil a partir de 2020-01. Ureia: FOB Mar Negro até 2022-02, FOB Oriente Médio a partir de 2022-03.")


# ----------------------------------------------------------------- Documentos (PDF)
DOCS = [
    ("A08", "ibge_anuario", "https://anuario.ibge.gov.br/images/aeb/2024/s4/2_pdf/s4t1210.pdf", "AEB 2024, tabela 4.1.2.10: produção de fertilizantes N, P e K, 2021-2023"),
    ("A08", "ibge_anuario", "https://anuario.ibge.gov.br/images/aeb/2024/s4/2_pdf/s4t1211.pdf", "AEB 2024, tabela 4.1.2.11: consumo aparente de matérias-primas, 2021-2023"),
    ("B04", "infra_sa", "https://ontl.infrasa.gov.br/wp-content/uploads/2026/02/BOLETIM-DE-FERTILIZANTE-FEV_-rev-04_sirlea.pdf", "ONTL/Infra S.A.: Boletim de Logística – mercado de fertilizantes (fev/2026)"),
    ("A09", "pnf_2050", "https://static.poder360.com.br/2022/03/plano-nacional-de-fertilizantes-brasil-2050.pdf", "Plano Nacional de Fertilizantes 2050 (SAE/PR, 2021)"),
    ("E04", "mcti", "https://repositorio.mctic.gov.br/bitstream/mctic/5248/1/2020_solos_manejados_calagem_aplicacao_ureia_final.pdf", "MCTI: relatório de referência – solos manejados, calagem e aplicação de ureia"),
    ("E03", "seeg", "https://seeg.eco.br/wp-content/uploads/2026/01/SEEG13-NM-AGROPECUARIA-BR.pdf", "SEEG coleção 13: nota metodológica de Agropecuária"),
]


def documentos():
    log("Documentos (PDF)")
    for idc, fonte, url, desc in DOCS:
        pb = pasta("brutos", fonte)
        nome = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        cam = os.path.join(pb, nome)
        try:
            b = baixar(url, tentativas=2)
            if not b.startswith(b"%PDF"):
                raise RuntimeError("resposta não é PDF")
            salvar_bytes(cam, b)
            registrar(idc, fonte, cam, desc, url)
            log(f"  ok: {nome}")
        except Exception as e:  # noqa: BLE001
            log(f"  FALHOU: {nome} ({e!r:.120})")
            if os.path.exists(cam):
                os.remove(cam)
            if not os.listdir(pb):
                os.rmdir(pb)
                if not os.listdir(os.path.dirname(pb)):
                    os.rmdir(os.path.dirname(pb))


FONTES = {"faostat": faostat, "anda": anda, "ipeadata": ipeadata, "sidra": sidra, "comex": comex,
          "bcb": bcb, "bancomundial": bancomundial, "documentos": documentos}


def main():
    global HOJE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fontes", default=",".join(FONTES))
    ap.add_argument("--data", default=HOJE, help="nome da pasta de versão (AAAA-MM-DD)")
    a = ap.parse_args()
    HOJE = a.data
    falhas = []
    for f in [x.strip() for x in a.fontes.split(",") if x.strip()]:
        try:
            FONTES[f]()
        except Exception as e:  # noqa: BLE001
            log(f"ERRO em {f}: {e!r:.300}")
            falhas.append(f)
        gravar_manifesto()  # grava a cada fonte, para não perder o que já foi baixado
        REGISTROS.clear()
    if falhas:
        log("fontes com erro: " + ", ".join(falhas))
        sys.exit(1)
    log("concluído")


if __name__ == "__main__":
    main()
