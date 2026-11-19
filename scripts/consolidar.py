# -*- coding: utf-8 -*-
"""
Consolida as bases de dados/brutos e dados/tratados em séries prontas para análise.

Uso (a partir de qualquer pasta):
    python consolidar.py                 # usa a versão (pasta datada) mais recente de cada fonte
    python consolidar.py --sem-site      # não copia os arquivos para docs/dados

Saídas
- dados/consolidados/*.csv        : séries consolidadas (UTF-8, vírgula, ponto decimal)
- dados/consolidados/DICIONARIO.csv : uma linha por coluna (descrição, unidade, fonte)
- dados/consolidados/metadados.json : versão de cada fonte, cobertura e nº de linhas
- dados/docs/dados/               : cópia usada pelo site (GitHub Pages)

Convenções
- Datas mensais no primeiro dia do mês (AAAA-MM-01).
- Quantidades em toneladas (t); valores em US$ ou mil R$ correntes, como na fonte.
- Símbolos do IBGE: "-" vira 0; "X" (sigilo), ".." e "..." viram vazio.
- Nada é interpolado nem extrapolado: onde a fonte não tem dado, a célula fica vazia.

Requer Python 3.9+ e pandas.
"""
import argparse, datetime, json, os, re, shutil, sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../dados
SAIDA = os.path.join(BASE, "consolidados")
SITE = os.path.join(BASE, "docs", "dados")
VERSOES = {}   # fonte -> pasta datada usada
DIC = []       # linhas do dicionário
RESUMO = {}    # arquivo -> {linhas, colunas, periodo}

UF = pd.DataFrame(
    [(11, "RO", "Rondônia", "Norte"), (12, "AC", "Acre", "Norte"), (13, "AM", "Amazonas", "Norte"),
     (14, "RR", "Roraima", "Norte"), (15, "PA", "Pará", "Norte"), (16, "AP", "Amapá", "Norte"),
     (17, "TO", "Tocantins", "Norte"), (21, "MA", "Maranhão", "Nordeste"), (22, "PI", "Piauí", "Nordeste"),
     (23, "CE", "Ceará", "Nordeste"), (24, "RN", "Rio Grande do Norte", "Nordeste"), (25, "PB", "Paraíba", "Nordeste"),
     (26, "PE", "Pernambuco", "Nordeste"), (27, "AL", "Alagoas", "Nordeste"), (28, "SE", "Sergipe", "Nordeste"),
     (29, "BA", "Bahia", "Nordeste"), (31, "MG", "Minas Gerais", "Sudeste"), (32, "ES", "Espírito Santo", "Sudeste"),
     (33, "RJ", "Rio de Janeiro", "Sudeste"), (35, "SP", "São Paulo", "Sudeste"), (41, "PR", "Paraná", "Sul"),
     (42, "SC", "Santa Catarina", "Sul"), (43, "RS", "Rio Grande do Sul", "Sul"), (50, "MS", "Mato Grosso do Sul", "Centro-Oeste"),
     (51, "MT", "Mato Grosso", "Centro-Oeste"), (52, "GO", "Goiás", "Centro-Oeste"), (53, "DF", "Distrito Federal", "Centro-Oeste")],
    columns=["uf_cod", "uf", "uf_nome", "regiao"])
REGIOES = {1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste"}

GRUPOS = {"3101": "Orgânicos (origem animal ou vegetal)", "3102": "Nitrogenados", "3103": "Fosfatados",
          "3104": "Potássicos", "3105": "NPK, MAP, DAP e outros mistos", "31": "Capítulo 31 (total)"}
MATERIAS = {"2503": "Enxofre", "2510": "Rocha fosfática", "2807": "Ácido sulfúrico",
            "2809": "Ácido fosfórico", "2814": "Amônia"}

# arquivo -> (nível territorial, frequência, conteúdo, fonte); vai para metadados.json e para o site
DESCRICOES = {
    "painel_br_anual.csv": ("Brasil", "anual", "Painel integrado: FAOSTAT, ANDA, Comex Stat, PAM, preços e câmbio numa linha por ano", "várias"),
    "painel_br_mensal.csv": ("Brasil", "mensal", "Painel integrado: ANDA, Comex Stat, preços e câmbio numa linha por mês", "várias"),
    "painel_uf_anual.csv": ("UF", "anual", "Painel balanceado por UF e ano: PAM, Comex Stat, IDS e Censos", "várias"),
    "br_anual_nutrientes_faostat.csv": ("Brasil", "anual", "Produção, importação, exportação e uso agrícola de N, P2O5 e K2O; kg/ha; dependência de importação", "FAOSTAT RFN"),
    "br_anual_produtos_faostat.csv": ("Brasil", "anual", "Produção, comércio e uso por produto (ureia, MAP, KCl e outros 20)", "FAOSTAT RFB"),
    "br_anual_balanco_nutrientes_faostat.csv": ("Brasil", "anual", "Balanço de N, P e K em lavouras: entradas, saídas e eficiência de uso", "FAOSTAT ESB"),
    "br_mensal_anda.csv": ("Brasil", "mensal", "Entregas ao mercado, produção nacional, importação e exportação de fertilizantes", "ANDA (PDFs e Ipeadata)"),
    "br_mensal_precos_cambio.csv": ("Brasil", "mensal", "Preços internacionais de fertilizantes, gás natural, soja e milho; câmbio nominal e real; relações de troca", "Banco Mundial e BCB"),
    "br_mensal_comercio_comex.csv": ("Brasil", "mensal", "Importação e exportação do capítulo 31 por posição (3101 a 3105)", "Comex Stat"),
    "br_mensal_importacao_ncm.csv": ("Brasil", "mensal", "Importação por NCM de 8 dígitos", "Comex Stat"),
    "br_mensal_importacao_materias_primas.csv": ("Brasil", "mensal", "Importação de enxofre, rocha fosfática, ácidos sulfúrico e fosfórico e amônia", "Comex Stat"),
    "br_anual_importacao_origem.csv": ("Brasil", "anual", "Importação por país de origem e posição, com participação", "Comex Stat"),
    "uf_anual_importacao_comex.csv": ("UF", "anual", "Importação por UF do produto e posição", "Comex Stat"),
    "uf_anual_entregas_nutriente_ids.csv": ("UF", "anual", "Entregas por nutriente e kg/ha, por UF, região e Brasil", "IBGE, IDS"),
    "uf_anual_area_culturas_pam.csv": ("UF", "anual", "Área plantada e colhida, quantidade e valor: total das lavouras e nove culturas", "IBGE, PAM"),
    "uf_censo_adubacao.csv": ("UF", "2006 e 2017", "Adoção de adubação e calagem e despesa com adubos e corretivos", "IBGE, Censo Agropecuário"),
    "mun_censo_adubacao.csv": ("Município", "2006 e 2017", "Adoção de adubação e calagem e despesa com adubos e corretivos", "IBGE, Censo Agropecuário"),
}


# ----------------------------------------------------------------- utilidades
def log(*a):
    print(datetime.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def ultima(tipo, fonte):
    """Caminho da pasta datada mais recente de uma fonte (brutos ou tratados)."""
    raiz = os.path.join(BASE, tipo, fonte)
    datas = sorted(d for d in os.listdir(raiz) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d))
    if not datas:
        raise FileNotFoundError(f"sem versão datada em {raiz}")
    VERSOES[f"{tipo}/{fonte}"] = datas[-1]
    return os.path.join(raiz, datas[-1])


def num(s):
    """Converte texto do IBGE em número: '-' = 0; 'X', '..', '...' = vazio."""
    s = s.astype("string").str.strip()
    return pd.to_numeric(s.where(s != "-", "0"), errors="coerce")


def razao(a, b, k=1.0):
    """a / b * k, vazio quando o denominador é zero ou ausente."""
    a = pd.to_numeric(a, errors="coerce").astype(float)
    b = pd.to_numeric(b, errors="coerce").astype(float)
    return (a / b.where(b > 0) * k)


def salvar(df, nome, colunas, periodo=None):
    """Grava o CSV e registra o dicionário. colunas: lista de (coluna, descrição, unidade, fonte)."""
    ordem = [c[0] for c in colunas]
    faltam = [c for c in ordem if c not in df.columns]
    sobram = [c for c in df.columns if c not in ordem]
    if faltam or sobram:
        raise ValueError(f"{nome}: colunas sem descrição {sobram} ou ausentes {faltam}")
    df = df[ordem]
    os.makedirs(SAIDA, exist_ok=True)
    df.to_csv(os.path.join(SAIDA, nome), index=False, encoding="utf-8", lineterminator="\n", float_format="%.10g")
    for col, desc, unid, fonte in colunas:
        DIC.append({"arquivo": nome, "coluna": col, "descricao": desc, "unidade": unid, "fonte": fonte})
    RESUMO[nome] = {"linhas": int(len(df)), "colunas": int(df.shape[1]), "periodo": periodo or ""}
    log(f"  {nome}: {len(df):,}".replace(",", ".") + f" linhas, {df.shape[1]} colunas")
    return df


def mensal(ano, mes):
    return pd.to_datetime(dict(year=ano.astype(int), month=mes.astype(int), day=1)).dt.strftime("%Y-%m-%d")


# ----------------------------------------------------------------- FAOSTAT
def faostat():
    p = ultima("tratados", "faostat")
    F = "FAOSTAT"
    # --- RFN: nutrientes
    rfn = pd.read_csv(os.path.join(p, "faostat_RFN_brasil.csv"))
    nomes = {"Nutrient nitrogen N (total)": "N", "Nutrient phosphate P2O5 (total)": "P2O5", "Nutrient potash K2O (total)": "K2O"}
    elem = {"Production": "producao_t", "Import quantity": "importacao_t", "Export quantity": "exportacao_t",
            "Agricultural Use": "uso_agricola_t", "Use per area of cropland": "uso_kg_ha"}
    rfn["nutriente"] = rfn["Item"].map(nomes)
    x = rfn[rfn["Element"].isin(elem)].copy()
    x["col"] = x["Element"].map(elem)
    w = x.pivot(index=["Year", "nutriente"], columns="col", values="Value").reset_index()
    flag = (rfn[rfn["Element"] == "Agricultural Use"].set_index(["Year", "nutriente"])["Flag"].rename("flag_uso"))
    w = w.join(flag, on=["Year", "nutriente"])
    tot = w.groupby("Year")[list(elem.values())].sum(min_count=3).reset_index()
    tot["nutriente"] = "NPK"
    tot["flag_uso"] = ""
    w = pd.concat([w, tot], ignore_index=True).rename(columns={"Year": "ano"})
    w["consumo_aparente_t"] = w["producao_t"] + w["importacao_t"] - w["exportacao_t"]
    w["dependencia_importacao_pct"] = razao(w["importacao_t"], w["uso_agricola_t"], 100).round(2)
    w["dependencia_liquida_pct"] = razao(w["importacao_t"] - w["exportacao_t"], w["consumo_aparente_t"], 100).round(2)
    w["nutriente"] = pd.Categorical(w["nutriente"], ["N", "P2O5", "K2O", "NPK"])
    w = w.sort_values(["ano", "nutriente"]).reset_index(drop=True)
    w["nutriente"] = w["nutriente"].astype(str)
    nut = salvar(w, "br_anual_nutrientes_faostat.csv", [
        ("ano", "Ano civil", "ano", F),
        ("nutriente", "Nutriente: N, P2O5, K2O ou NPK (soma dos três)", "", F + " RFN"),
        ("producao_t", "Produção nacional de fertilizantes, em nutriente", "t de nutriente", F + " RFN, elemento 5510"),
        ("importacao_t", "Importação, em nutriente", "t de nutriente", F + " RFN, elemento 5610"),
        ("exportacao_t", "Exportação, em nutriente", "t de nutriente", F + " RFN, elemento 5910"),
        ("uso_agricola_t", "Uso agrícola, em nutriente", "t de nutriente", F + " RFN, elemento 5157"),
        ("uso_kg_ha", "Uso por área de lavoura (cropland)", "kg/ha", F + " RFN, elemento 5159"),
        ("flag_uso", "Flag da FAO para o uso agrícola (A oficial, E estimado, I imputado, X internacional)", "", F + " RFN"),
        ("consumo_aparente_t", "Consumo aparente = produção + importação - exportação", "t de nutriente", "cálculo próprio"),
        ("dependencia_importacao_pct", "Importação dividida pelo uso agrícola", "%", "cálculo próprio"),
        ("dependencia_liquida_pct", "Importação líquida dividida pelo consumo aparente", "%", "cálculo próprio"),
    ], f"{w.ano.min()}-{w.ano.max()}")

    # --- RFB: produtos
    rfb = pd.read_csv(os.path.join(p, "faostat_RFB_brasil.csv"))
    pt = {"Ammonia, anhydrous": "Amônia anidra", "Ammonium nitrate (AN)": "Nitrato de amônio",
          "Ammonium sulphate": "Sulfato de amônio",
          "Calcium ammonium nitrate (CAN) and other mixtures with calcium carbonate": "Nitrocálcio (CAN) e misturas com carbonato de cálcio",
          "Diammonium phosphate (DAP)": "Fosfato diamônico (DAP)", "Fertilizers n.e.c.": "Fertilizantes não especificados",
          "Monoammonium phosphate (MAP)": "Fosfato monoamônico (MAP)", "NPK fertilizers": "Fertilizantes NPK",
          "Other nitrogenous fertilizers, n.e.c.": "Outros nitrogenados", "Other NK compounds": "Outros compostos NK",
          "Other NP compounds": "Outros compostos NP", "Other phosphatic fertilizers, n.e.c.": "Outros fosfatados",
          "Other potassic fertilizers, n.e.c.": "Outros potássicos", "Phosphate rock": "Rocha fosfática",
          "PK compounds": "Compostos PK", "Potassium chloride (muriate of potash) (MOP)": "Cloreto de potássio (KCl)",
          "Potassium nitrate": "Nitrato de potássio", "Potassium sulphate (sulphate of potash) (SOP)": "Sulfato de potássio",
          "Sodium nitrate": "Nitrato de sódio", "Superphosphates above 35%": "Superfosfatos acima de 35% (TSP)",
          "Superphosphates, other": "Superfosfatos, outros (SSP)", "Urea": "Ureia",
          "Urea and ammonium nitrate solutions (UAN)": "Soluções de ureia e nitrato de amônio (UAN)"}
    elem = {"Production": "producao_t", "Import quantity": "importacao_t", "Export quantity": "exportacao_t",
            "Agricultural Use": "uso_agricola_t", "Import value": "importacao_mil_usd", "Export value": "exportacao_mil_usd"}
    rfb["col"] = rfb["Element"].map(elem)
    w = rfb.pivot(index=["Year", "Item Code", "Item"], columns="col", values="Value").reset_index()
    w = w.rename(columns={"Year": "ano", "Item Code": "item_cod", "Item": "produto_fao"})
    w["produto"] = w["produto_fao"].map(pt)
    for c in elem.values():
        if c not in w.columns:
            w[c] = np.nan
    w = w.sort_values(["ano", "produto"]).reset_index(drop=True)
    salvar(w, "br_anual_produtos_faostat.csv", [
        ("ano", "Ano civil", "ano", F),
        ("item_cod", "Código do item na FAOSTAT", "", F + " RFB"),
        ("produto_fao", "Nome do produto na FAOSTAT (inglês)", "", F + " RFB"),
        ("produto", "Nome do produto em português", "", "tradução própria"),
        ("producao_t", "Produção nacional", "t de produto", F + " RFB"),
        ("importacao_t", "Importação", "t de produto", F + " RFB"),
        ("exportacao_t", "Exportação", "t de produto", F + " RFB"),
        ("uso_agricola_t", "Uso agrícola", "t de produto", F + " RFB"),
        ("importacao_mil_usd", "Valor da importação", "mil US$", F + " RFB"),
        ("exportacao_mil_usd", "Valor da exportação", "mil US$", F + " RFB"),
    ], f"{w.ano.min()}-{w.ano.max()}")

    # --- ESB: balanço de nutrientes em lavouras
    esb = pd.read_csv(os.path.join(p, "faostat_ESB_brasil.csv"))
    itens = {"Mineral fertilizers": "fertilizante_mineral", "Manure applied": "esterco_aplicado",
             "Atmospheric deposition": "deposicao_atmosferica", "Biological fixation": "fixacao_biologica",
             "Seed": "sementes", "Input": "entradas", "Crop harvest removal": "remocao_colheita",
             "Crop residue removal": "remocao_residuos", "Leaching": "lixiviacao", "Volatilisation": "volatilizacao",
             "Outputs": "saidas", "Nutrient balance": "balanco"}
    nutr = {"nitrogen": "N", "phosphorus": "P", "potassium": "K"}
    esb["nutriente"] = esb["Element"].str.extract(r"Cropland (\w+)")[0].map(nutr)
    esb["tipo"] = np.select([esb["Element"].str.contains("per unit area"), esb["Element"].str.contains("efficiency")], ["kg_ha", "pct"], "t")
    esb["col"] = esb["Item"].map(itens) + "_" + esb["tipo"]
    w = esb.pivot(index=["Year", "nutriente"], columns="col", values="Value").reset_index()
    w = w.rename(columns={"Year": "ano", "balanco_pct": "eficiencia_uso_pct"})
    cols_t = [v + "_t" for v in itens.values()]
    for c in cols_t:
        if c not in w.columns:
            w[c] = np.nan
    w = w[["ano", "nutriente"] + cols_t + ["balanco_kg_ha", "fertilizante_mineral_kg_ha", "eficiencia_uso_pct"]]
    w["nutriente"] = pd.Categorical(w["nutriente"], ["N", "P", "K"])
    w = w.sort_values(["ano", "nutriente"]).reset_index(drop=True)
    w["nutriente"] = w["nutriente"].astype(str)
    E = F + " ESB (Ludemann et al., 2024)"
    desc = {"fertilizante_mineral": "Entrada por fertilizantes minerais", "esterco_aplicado": "Entrada por esterco aplicado",
            "deposicao_atmosferica": "Entrada por deposição atmosférica (só N)", "fixacao_biologica": "Entrada por fixação biológica (só N)",
            "sementes": "Entrada por sementes", "entradas": "Total de entradas", "remocao_colheita": "Remoção pela colheita",
            "remocao_residuos": "Remoção por resíduos de cultura", "lixiviacao": "Perda por lixiviação (só N)",
            "volatilizacao": "Perda por volatilização (só N)", "saidas": "Total de saídas", "balanco": "Balanço (entradas - saídas)"}
    salvar(w, "br_anual_balanco_nutrientes_faostat.csv",
           [("ano", "Ano civil", "ano", F), ("nutriente", "Nutriente elementar: N, P ou K (não é P2O5 nem K2O)", "", E)]
           + [(v + "_t", desc[v] + ", em lavouras", "t de nutriente elementar", E) for v in itens.values()]
           + [("balanco_kg_ha", "Balanço por área de lavoura", "kg/ha", E),
              ("fertilizante_mineral_kg_ha", "Fertilizante mineral por área de lavoura", "kg/ha", E),
              ("eficiencia_uso_pct", "Eficiência de uso do nutriente (saídas / entradas)", "%", E)],
           f"{w.ano.min()}-{w.ano.max()}")
    return nut


# ----------------------------------------------------------------- ANDA
def anda():
    pdfs = pd.read_csv(os.path.join(ultima("tratados", "anda"), "anda_principais_indicadores_por_edicao.csv"))
    pdfs["edicao"] = pdfs["edicao_arquivo"].str.extract(r"_(\d{4})")[0].astype(int)
    # Para cada mês vale a edição mais recente que o publica (cada edição revisa os 3 anos anteriores).
    # De 2013 em diante os PDFs são preferidos ao Ipeadata: as edições concordam entre si e o Ipeadata
    # tem erros de digitação (ex.: jun/2014 repete o valor de mar/2014).
    pdfs = pdfs.dropna(subset=["toneladas_produto"]).sort_values("edicao")
    ult = pdfs.groupby(["serie", "ano", "mes"], as_index=False).last()
    a = ult.pivot(index=["ano", "mes"], columns="serie", values="toneladas_produto").reset_index()
    a["fonte"] = "ANDA, Principais Indicadores (PDF)"

    ipea = pd.read_csv(os.path.join(ultima("brutos", "ipeadata"), "ipeadata_series.csv"))
    cod = {"ANDA12_VFERTILIZ12": "entregas", "ANDA12_PFERTILIZ12": "producao", "ANDA12_MFERTILIZ12": "importacao",
           "ANDA12_NPKFERTILIZ12": "exportacao"}
    i = ipea[ipea["codigo"].isin(cod)].copy()
    i["serie"] = i["codigo"].map(cod)
    i["ano"] = i["data"].str[:4].astype(int)
    i["mes"] = i["data"].str[5:7].astype(int)
    i = i.pivot(index=["ano", "mes"], columns="serie", values="valor").reset_index()
    i["fonte"] = "ANDA, via Ipeadata"

    chave = set(zip(a["ano"], a["mes"]))
    antes = i[[k not in chave for k in zip(i["ano"], i["mes"])]]
    m = pd.concat([antes, a], ignore_index=True).sort_values(["ano", "mes"]).reset_index(drop=True)
    for c in ["entregas", "producao", "importacao", "exportacao"]:
        m[c + "_t"] = m[c] if c in m.columns else np.nan
    # coluna de conferência: o que o Ipeadata publica para o mesmo mês
    conf = i.set_index(["ano", "mes"])["entregas"].rename("entregas_ipeadata_t")
    m = m.join(conf, on=["ano", "mes"])
    m["data"] = mensal(m["ano"], m["mes"])
    m = m[["data", "ano", "mes", "entregas_t", "producao_t", "importacao_t", "exportacao_t", "entregas_ipeadata_t", "fonte"]]
    A = "ANDA"
    salvar(m, "br_mensal_anda.csv", [
        ("data", "Mês de referência (primeiro dia)", "AAAA-MM-DD", A),
        ("ano", "Ano", "ano", A), ("mes", "Mês", "1-12", A),
        ("entregas_t", "Fertilizantes entregues ao mercado", "t de produto", A),
        ("producao_t", "Produção nacional de fertilizantes intermediários", "t de produto", A),
        ("importacao_t", "Importação de fertilizantes intermediários", "t de produto", A),
        ("exportacao_t", "Exportação de fertilizantes e formulações NPK (a partir de 2013)", "t de produto", A),
        ("entregas_ipeadata_t", "Entregas segundo o Ipeadata, para conferência (diverge em alguns anos)", "t de produto", "ANDA, via Ipeadata"),
        ("fonte", "Origem do valor das quatro séries: PDF da ANDA (2013 em diante) ou Ipeadata (1998-2012)", "", ""),
    ], f"{m.data.min()[:7]} a {m.data.max()[:7]}")
    return m


# ----------------------------------------------------------------- preços e câmbio
def precos():
    pk = pd.read_csv(os.path.join(ultima("tratados", "banco_mundial"), "pinksheet_fertilizantes_gas_graos_mensal.csv"), dtype=str)
    ren = {"Natural gas, US ($/mmbtu)": "gas_natural_eua_usd_mmbtu", "Natural gas, Europe ($/mmbtu)": "gas_natural_europa_usd_mmbtu",
           "Natural gas index (2010=100)": "gas_natural_indice", "Soybeans ($/mt)": "soja_usd_t", "Maize ($/mt)": "milho_usd_t",
           "Phosphate rock ($/mt)": "rocha_fosfatica_usd_t", "DAP ($/mt)": "dap_usd_t", "TSP ($/mt)": "tsp_usd_t",
           "Urea ($/mt)": "ureia_usd_t", "Potassium chloride ($/mt)": "kcl_usd_t"}
    falta = [c for c in ren if c not in pk.columns]
    if falta:
        raise ValueError(f"Pink Sheet sem as colunas {falta}")
    d = pd.DataFrame({"data": pd.to_datetime(pk["mes"].str.replace("M", "-") + "-01").dt.strftime("%Y-%m-%d")})
    for o, n in ren.items():
        d[n] = pd.to_numeric(pk[o], errors="coerce")

    bcb = pd.read_csv(os.path.join(ultima("brutos", "bcb_sgs"), "bcb_sgs_cambio.csv"))
    series = {3698: "cambio_brl_usd_media", 3696: "cambio_brl_usd_fim", 11752: "cambio_real_efetivo_indice", 11753: "cambio_real_usd_indice"}
    b = bcb[bcb["serie"].isin(series)].copy()
    b["col"] = b["serie"].map(series)
    b = b.pivot(index="data", columns="col", values="valor").reset_index()
    d = d.merge(b, on="data", how="outer").sort_values("data").reset_index(drop=True)
    d["ano"] = d["data"].str[:4].astype(int)
    d["mes"] = d["data"].str[5:7].astype(int)
    # preços em reais só a partir do Plano Real (jul/1994): antes, a série do câmbio muda de moeda
    real = d["data"] >= "1994-07-01"
    for f in ["ureia", "dap", "tsp", "kcl", "rocha_fosfatica"]:
        d[f + "_brl_t"] = (d[f + "_usd_t"] * d["cambio_brl_usd_media"]).where(real).round(2)
    d["rt_ureia_milho"] = razao(d["ureia_usd_t"], d["milho_usd_t"]).round(3)
    d["rt_kcl_soja"] = razao(d["kcl_usd_t"], d["soja_usd_t"]).round(3)
    d["rt_dap_soja"] = razao(d["dap_usd_t"], d["soja_usd_t"]).round(3)
    usd = list(ren.values())
    d = d[["data", "ano", "mes"] + usd + list(series.values()) + [f + "_brl_t" for f in ["ureia", "dap", "tsp", "kcl", "rocha_fosfatica"]]
          + ["rt_ureia_milho", "rt_kcl_soja", "rt_dap_soja"]]
    P = "Banco Mundial, Pink Sheet"
    B = "BCB-SGS"
    nomes = {"gas_natural_eua_usd_mmbtu": ("Gás natural, EUA (Henry Hub)", "US$/mmbtu"), "gas_natural_europa_usd_mmbtu": ("Gás natural, Europa", "US$/mmbtu"),
             "gas_natural_indice": ("Índice de gás natural", "2010 = 100"), "soja_usd_t": ("Soja", "US$/t"), "milho_usd_t": ("Milho", "US$/t"),
             "rocha_fosfatica_usd_t": ("Rocha fosfática", "US$/t"), "dap_usd_t": ("Fosfato diamônico (DAP)", "US$/t"),
             "tsp_usd_t": ("Superfosfato triplo (TSP)", "US$/t"),
             "ureia_usd_t": ("Ureia (a partir de mar/2022, FOB Oriente Médio)", "US$/t"),
             "kcl_usd_t": ("Cloreto de potássio (a partir de jan/2020, CFR Brasil)", "US$/t")}
    salvar(d, "br_mensal_precos_cambio.csv",
           [("data", "Mês de referência (primeiro dia)", "AAAA-MM-DD", ""), ("ano", "Ano", "ano", ""), ("mes", "Mês", "1-12", "")]
           + [(c, "Preço internacional: " + nomes[c][0], nomes[c][1], P) for c in usd]
           + [("cambio_brl_usd_media", "Taxa de câmbio livre, dólar (venda), média do mês (antes de jul/1994, na moeda da época)", "R$/US$", B + " 3698"),
              ("cambio_brl_usd_fim", "Taxa de câmbio livre, dólar (venda), fim do mês (antes de jul/1994, na moeda da época)", "R$/US$", B + " 3696"),
              ("cambio_real_efetivo_indice", "Taxa de câmbio real efetiva (IPCA)", "jun/1994 = 100", B + " 11752"),
              ("cambio_real_usd_indice", "Taxa de câmbio real bilateral com o dólar (IPCA)", "jun/1994 = 100", B + " 11753")]
           + [(f + "_brl_t", f"Preço internacional convertido pelo câmbio médio do mês ({f}); só a partir de jul/1994", "R$/t", "cálculo próprio")
              for f in ["ureia", "dap", "tsp", "kcl", "rocha_fosfatica"]]
           + [("rt_ureia_milho", "Relação de troca: t de milho para comprar 1 t de ureia (preços internacionais)", "t/t", "cálculo próprio"),
              ("rt_kcl_soja", "Relação de troca: t de soja para comprar 1 t de KCl (preços internacionais)", "t/t", "cálculo próprio"),
              ("rt_dap_soja", "Relação de troca: t de soja para comprar 1 t de DAP (preços internacionais)", "t/t", "cálculo próprio")],
           f"{d.data.min()[:7]} a {d.data.max()[:7]}")
    return d


# ----------------------------------------------------------------- Comex Stat
def comex():
    p = ultima("brutos", "comex_stat")
    C = "Comex Stat (MDIC/Secex)"
    imp = pd.read_csv(os.path.join(p, "comex_importacao_cap31_ncm_pais_uf_mensal_1997_2026.csv"), dtype={"coNcm": str})
    exp = pd.read_csv(os.path.join(p, "comex_exportacao_cap31_ncm_pais_uf_mensal_1997_2026.csv"), dtype={"coNcm": str})
    mp = pd.read_csv(os.path.join(p, "comex_importacao_materias_primas_ncm_pais_uf_mensal_1997_2026.csv"), dtype={"coNcm": str})
    hist = pd.read_csv(os.path.join(p, "comex_historico_nbm_importacao_fertilizantes_materias_primas_1989_1996.csv"))
    nbm = pd.read_csv(os.path.join(p, "comex_tabela_nbm_fertilizantes.csv"), dtype=str)
    for d in (imp, exp, mp):
        d["sh4"] = d["coNcm"].str[:4]
    if nbm["nbm"].duplicated().any():
        raise ValueError("descrição NBM repetida: não dá para casar o histórico pelo nome")
    hist = hist.merge(nbm, on="nbm", how="left", validate="many_to_one")
    if hist["coNbm"].isna().any():
        raise ValueError("linhas do histórico NBM sem código na tabela comex_tabela_nbm_fertilizantes.csv")
    hist["sh4"] = hist["coNbm"].str[:4]
    hist["metricKG"] = pd.to_numeric(hist["metricKG"], errors="coerce")
    ultimo = imp.loc[imp["year"] == imp["year"].max(), "monthNumber"].max()
    ano_parcial = int(imp["year"].max()) if ultimo < 12 else None

    def com_total(d, chaves, vals):
        """Agrega por grupo SH4 e acrescenta a linha do capítulo 31."""
        g = d.groupby(chaves + ["sh4"], as_index=False)[vals].sum(min_count=1)
        t = d.groupby(chaves, as_index=False)[vals].sum(min_count=1)
        t["sh4"] = "31"
        return pd.concat([g, t], ignore_index=True)

    # --- mensal por grupo (NCM 1997+ e NBM 1989-1996)
    vi = ["metricKG", "metricFOB", "metricCIF", "metricFreight"]
    gi = com_total(imp, ["year", "monthNumber"], vi)
    gi["nomenclatura"] = "NCM"
    h31 = hist[hist["sh4"].str.startswith("31")]
    gh = com_total(h31, ["year", "monthNumber"], ["metricKG", "metricFOB"])
    gh["nomenclatura"] = "NBM"
    ge = com_total(exp, ["year", "monthNumber"], ["metricKG", "metricFOB"]).rename(
        columns={"metricKG": "exportacao_kg", "metricFOB": "exportacao_fob_usd"})
    g = pd.concat([gh, gi], ignore_index=True).merge(ge, on=["year", "monthNumber", "sh4"], how="outer")
    g["nomenclatura"] = g["nomenclatura"].fillna("NCM")
    g = g.rename(columns={"year": "ano", "monthNumber": "mes", "sh4": "grupo_sh4", "metricFOB": "importacao_fob_usd",
                          "metricCIF": "importacao_cif_usd", "metricFreight": "importacao_frete_usd"})
    ncm = g["nomenclatura"] == "NCM"
    g["importacao_t"] = (g["metricKG"] / 1000).where(~(ncm & g["metricKG"].isna()), 0.0)
    for c in ["importacao_fob_usd", "importacao_cif_usd", "importacao_frete_usd"]:
        g[c] = g[c].where(~(ncm & g[c].isna()), 0.0)
    g["exportacao_t"] = (g["exportacao_kg"] / 1000).where(~ncm, (g["exportacao_kg"] / 1000).fillna(0.0))
    g["exportacao_fob_usd"] = g["exportacao_fob_usd"].where(~ncm, g["exportacao_fob_usd"].fillna(0.0))
    g["preco_medio_importacao_fob_usd_t"] = razao(g["importacao_fob_usd"], g["importacao_t"]).round(2)
    g["preco_medio_importacao_cif_usd_t"] = razao(g["importacao_cif_usd"], g["importacao_t"]).round(2)
    g["grupo"] = g["grupo_sh4"].map(GRUPOS)
    g["data"] = mensal(g["ano"], g["mes"])
    g = g.sort_values(["data", "grupo_sh4"]).reset_index(drop=True)
    g = g[["data", "ano", "mes", "grupo_sh4", "grupo", "importacao_t", "importacao_fob_usd", "importacao_cif_usd", "importacao_frete_usd",
           "exportacao_t", "exportacao_fob_usd", "preco_medio_importacao_fob_usd_t", "preco_medio_importacao_cif_usd_t", "nomenclatura"]]
    periodo = f"{g.data.min()[:7]} a {g.data.max()[:7]}"
    salvar(g, "br_mensal_comercio_comex.csv", [
        ("data", "Mês de referência (primeiro dia)", "AAAA-MM-DD", C), ("ano", "Ano", "ano", C), ("mes", "Mês", "1-12", C),
        ("grupo_sh4", "Posição do Sistema Harmonizado (3101 a 3105) ou 31 para o capítulo inteiro", "", C),
        ("grupo", "Nome do grupo de fertilizantes", "", "classificação própria"),
        ("importacao_t", "Importação, peso líquido", "t de produto", C),
        ("importacao_fob_usd", "Importação, valor FOB", "US$", C),
        ("importacao_cif_usd", "Importação, valor CIF (só NCM, 1997 em diante)", "US$", C),
        ("importacao_frete_usd", "Importação, frete (só NCM, 1997 em diante)", "US$", C),
        ("exportacao_t", "Exportação, peso líquido (só NCM, 1997 em diante)", "t de produto", C),
        ("exportacao_fob_usd", "Exportação, valor FOB (só NCM, 1997 em diante)", "US$", C),
        ("preco_medio_importacao_fob_usd_t", "Valor FOB dividido pelo peso importado", "US$/t", "cálculo próprio"),
        ("preco_medio_importacao_cif_usd_t", "Valor CIF dividido pelo peso importado", "US$/t", "cálculo próprio"),
        ("nomenclatura", "NBM (1989-1996, só importação; há linhas sem peso na fonte) ou NCM (1997 em diante)", "", C),
    ], periodo)

    # --- mensal por NCM
    n = imp.groupby(["year", "monthNumber", "coNcm", "sh4"], as_index=False)[["metricKG", "metricFOB", "metricCIF"]].sum()
    desc = imp.drop_duplicates("coNcm").set_index("coNcm")["ncm"]
    n["descricao"] = n["coNcm"].map(desc)
    n["importacao_t"] = n["metricKG"] / 1000
    n["data"] = mensal(n["year"], n["monthNumber"])
    n = n.rename(columns={"year": "ano", "monthNumber": "mes", "coNcm": "ncm", "sh4": "grupo_sh4",
                          "metricFOB": "importacao_fob_usd", "metricCIF": "importacao_cif_usd"})
    n = n.sort_values(["data", "ncm"]).reset_index(drop=True)
    n = n[["data", "ano", "mes", "ncm", "descricao", "grupo_sh4", "importacao_t", "importacao_fob_usd", "importacao_cif_usd"]]
    salvar(n, "br_mensal_importacao_ncm.csv", [
        ("data", "Mês de referência (primeiro dia)", "AAAA-MM-DD", C), ("ano", "Ano", "ano", C), ("mes", "Mês", "1-12", C),
        ("ncm", "Código NCM de 8 dígitos (capítulo 31)", "", C), ("descricao", "Descrição da NCM", "", C),
        ("grupo_sh4", "Posição do Sistema Harmonizado (4 dígitos)", "", C),
        ("importacao_t", "Importação, peso líquido", "t de produto", C),
        ("importacao_fob_usd", "Importação, valor FOB", "US$", C), ("importacao_cif_usd", "Importação, valor CIF", "US$", C),
    ], f"{n.data.min()[:7]} a {n.data.max()[:7]}")

    # --- mensal de matérias-primas
    r = mp.groupby(["year", "monthNumber", "sh4"], as_index=False)[["metricKG", "metricFOB", "metricCIF"]].sum()
    r["materia_prima"] = r["sh4"].map(MATERIAS)
    r["importacao_t"] = r["metricKG"] / 1000
    r["data"] = mensal(r["year"], r["monthNumber"])
    r = r.rename(columns={"year": "ano", "monthNumber": "mes", "sh4": "posicao_sh4", "metricFOB": "importacao_fob_usd", "metricCIF": "importacao_cif_usd"})
    r = r.sort_values(["data", "posicao_sh4"]).reset_index(drop=True)
    r = r[["data", "ano", "mes", "posicao_sh4", "materia_prima", "importacao_t", "importacao_fob_usd", "importacao_cif_usd"]]
    salvar(r, "br_mensal_importacao_materias_primas.csv", [
        ("data", "Mês de referência (primeiro dia)", "AAAA-MM-DD", C), ("ano", "Ano", "ano", C), ("mes", "Mês", "1-12", C),
        ("posicao_sh4", "Posição do Sistema Harmonizado: 2503, 2510, 2807, 2809 ou 2814", "", C),
        ("materia_prima", "Enxofre, rocha fosfática, ácido sulfúrico, ácido fosfórico ou amônia", "", "classificação própria"),
        ("importacao_t", "Importação, peso líquido", "t de produto", C),
        ("importacao_fob_usd", "Importação, valor FOB", "US$", C), ("importacao_cif_usd", "Importação, valor CIF", "US$", C),
    ], f"{r.data.min()[:7]} a {r.data.max()[:7]}")

    # --- anual por país de origem
    o = com_total(imp, ["year", "country"], ["metricKG", "metricFOB"])
    o["nomenclatura"] = "NCM"
    oh = com_total(h31, ["year", "country"], ["metricKG", "metricFOB"])
    oh["nomenclatura"] = "NBM"
    o = pd.concat([oh, o], ignore_index=True).rename(columns={"year": "ano", "country": "pais", "sh4": "grupo_sh4", "metricFOB": "importacao_fob_usd"})
    o["importacao_t"] = o["metricKG"] / 1000
    o["grupo"] = o["grupo_sh4"].map(GRUPOS)
    tot = o.groupby(["ano", "grupo_sh4"])["importacao_t"].transform("sum")
    o["participacao_pct"] = razao(o["importacao_t"], tot, 100).round(3)
    o["ano_parcial"] = (o["ano"] == ano_parcial).astype(int)
    o = o.sort_values(["ano", "grupo_sh4", "importacao_t"], ascending=[True, True, False]).reset_index(drop=True)
    o = o[["ano", "pais", "grupo_sh4", "grupo", "importacao_t", "importacao_fob_usd", "participacao_pct", "ano_parcial", "nomenclatura"]]
    salvar(o, "br_anual_importacao_origem.csv", [
        ("ano", "Ano civil", "ano", C), ("pais", "País de origem", "", C),
        ("grupo_sh4", "Posição do Sistema Harmonizado (3101 a 3105) ou 31 para o capítulo inteiro", "", C),
        ("grupo", "Nome do grupo de fertilizantes", "", "classificação própria"),
        ("importacao_t", "Importação, peso líquido", "t de produto", C), ("importacao_fob_usd", "Importação, valor FOB", "US$", C),
        ("participacao_pct", "Participação do país no peso importado do grupo naquele ano", "%", "cálculo próprio"),
        ("ano_parcial", f"1 quando o ano não está completo na fonte (hoje: {ano_parcial}, até o mês {ultimo})", "0/1", ""),
        ("nomenclatura", "NBM (1989-1996) ou NCM (1997 em diante)", "", C),
    ], f"{o.ano.min()}-{o.ano.max()}")

    # --- anual por UF
    u = com_total(imp, ["year", "state"], ["metricKG", "metricFOB", "metricCIF"])
    u = u.merge(UF, left_on="state", right_on="uf_nome", how="left")
    if u["uf"].isna().any():
        raise ValueError(f"UF sem correspondência no Comex Stat: {sorted(u.loc[u.uf.isna(), 'state'].unique())}")
    u = u.rename(columns={"year": "ano", "sh4": "grupo_sh4", "metricFOB": "importacao_fob_usd", "metricCIF": "importacao_cif_usd"})
    u["importacao_t"] = u["metricKG"] / 1000
    u["grupo"] = u["grupo_sh4"].map(GRUPOS)
    u["ano_parcial"] = (u["ano"] == ano_parcial).astype(int)
    u = u.sort_values(["ano", "uf_cod", "grupo_sh4"]).reset_index(drop=True)
    u = u[["ano", "uf_cod", "uf", "uf_nome", "regiao", "grupo_sh4", "grupo", "importacao_t", "importacao_fob_usd", "importacao_cif_usd", "ano_parcial"]]
    salvar(u, "uf_anual_importacao_comex.csv", [
        ("ano", "Ano civil", "ano", C), ("uf_cod", "Código IBGE da UF", "", "IBGE"), ("uf", "Sigla da UF", "", "IBGE"),
        ("uf_nome", "Nome da UF", "", "IBGE"), ("regiao", "Grande Região", "", "IBGE"),
        ("grupo_sh4", "Posição do Sistema Harmonizado (3101 a 3105) ou 31 para o capítulo inteiro", "", C),
        ("grupo", "Nome do grupo de fertilizantes", "", "classificação própria"),
        ("importacao_t", "Importação, peso líquido, por UF do produto (destino declarado, não a UF de aplicação)", "t de produto", C),
        ("importacao_fob_usd", "Importação, valor FOB", "US$", C), ("importacao_cif_usd", "Importação, valor CIF", "US$", C),
        ("ano_parcial", f"1 quando o ano não está completo na fonte (hoje: {ano_parcial}, até o mês {ultimo})", "0/1", ""),
    ], f"{u.ano.min()}-{u.ano.max()}")
    return g, u, ano_parcial, int(ultimo)


# ----------------------------------------------------------------- IBGE: IDS, PAM e Censos
def ids():
    p = ultima("brutos", "ibge_sidra")
    nut = {"119127": "Total", "119128": "N", "119129": "P2O5", "119130": "K2O"}
    t = pd.read_csv(os.path.join(p, "ids_770_entregas_nutriente_br_gr_uf.csv"), dtype=str)
    t["v"] = num(t["valor"])
    t["col"] = t["variavel_cod"].map({"2397": "entregas_t", "2398": "kg_ha"})
    w = t.pivot(index=["nivel_cod", "local_cod", "local_nome", "ano_cod", "tipo_de_nutriente_cod"], columns="col", values="v").reset_index()
    a = pd.read_csv(os.path.join(p, "ids_769_area_entregas_br_gr_uf.csv"), dtype=str)
    a = a[a["variavel_cod"] == "2396"].assign(area_plantada_ha=lambda d: num(d["valor"]))
    w = w.merge(a[["nivel_cod", "local_cod", "ano_cod", "area_plantada_ha"]], on=["nivel_cod", "local_cod", "ano_cod"], how="left")
    # tabela 768: kg/ha do Brasil desde 1992 (antes de 2007 não há a quantidade entregue)
    k = pd.read_csv(os.path.join(p, "ids_768_kgha_nutriente_brasil.csv"), dtype=str)
    k = k[k["ano_cod"].astype(int) < int(w["ano_cod"].min())].assign(kg_ha=lambda d: num(d["valor"]))
    k = k[["nivel_cod", "local_cod", "local_nome", "ano_cod", "tipo_de_nutriente_cod", "kg_ha"]]
    w = pd.concat([k, w], ignore_index=True)
    w["nivel"] = w["nivel_cod"].map({"1": "BR", "2": "GR", "3": "UF"})
    w["nutriente"] = w["tipo_de_nutriente_cod"].map(nut)
    w["ano"] = w["ano_cod"].astype(int)
    w["local_cod"] = w["local_cod"].astype(int)
    w = w.merge(UF[["uf_cod", "uf"]], left_on="local_cod", right_on="uf_cod", how="left")
    w["uf"] = w["uf"].where(w["nivel"] == "UF", "")
    w["nutriente"] = pd.Categorical(w["nutriente"], ["Total", "N", "P2O5", "K2O"])
    w["nivel"] = pd.Categorical(w["nivel"], ["BR", "GR", "UF"])
    w = w.sort_values(["ano", "nivel", "local_cod", "nutriente"]).reset_index(drop=True)
    w[["nivel", "nutriente"]] = w[["nivel", "nutriente"]].astype(str)
    w = w[["ano", "nivel", "local_cod", "local_nome", "uf", "nutriente", "entregas_t", "kg_ha", "area_plantada_ha"]]
    I = "IBGE, Indicadores de Desenvolvimento Sustentável"
    salvar(w, "uf_anual_entregas_nutriente_ids.csv", [
        ("ano", "Ano civil", "ano", I),
        ("nivel", "Nível territorial: BR (Brasil), GR (Grande Região) ou UF", "", I),
        ("local_cod", "Código do local no nível (atenção: 1 é Brasil no nível BR e Norte no nível GR)", "", I),
        ("local_nome", "Nome do local", "", I), ("uf", "Sigla da UF (vazio para BR e GR)", "", "IBGE"),
        ("nutriente", "Total, N, P2O5 ou K2O", "", I),
        ("entregas_t", "Fertilizantes entregues ao consumidor final, em nutriente (2007-2014)", "t de nutriente", I + ", SIDRA 770"),
        ("kg_ha", "Fertilizantes por área plantada (Brasil desde 1992, pela tabela 768)", "kg/ha", I + ", SIDRA 770 e 768"),
        ("area_plantada_ha", "Área plantada das principais culturas (igual para todos os nutrientes)", "ha", I + ", SIDRA 769"),
    ], f"{w.ano.min()}-{w.ano.max()}")
    return w


def pam():
    p = ultima("brutos", "ibge_sidra")
    culturas = {"0": "Total", "40124": "Soja", "40122": "Milho", "40106": "Cana-de-açúcar", "40099": "Algodão herbáceo",
                "40139": "Café", "40102": "Arroz", "40112": "Feijão", "40127": "Trigo", "40151": "Laranja"}
    col = "produto_das_lavouras_temporarias_e_perma_cod"
    t = pd.read_csv(os.path.join(p, "pam_5457_lavouras_br_uf.csv"), dtype=str)
    t = t[t[col].isin(culturas)].copy()
    t["v"] = num(t["valor"])
    # valor da produção só em reais (1994 em diante); moedas anteriores ficam vazias
    t.loc[(t["variavel_cod"] == "215") & (t["unidade"] != "Mil Reais"), "v"] = np.nan
    t["col"] = t["variavel_cod"].map({"8331": "area_plantada_ha", "216": "area_colhida_ha", "214": "quantidade_t", "215": "valor_producao_mil_reais"})
    w = t.pivot(index=["nivel_cod", "local_cod", "ano_cod", col], columns="col", values="v").reset_index()
    w["nivel"] = w["nivel_cod"].map({"1": "BR", "3": "UF"})
    w["cultura"] = w[col].map(culturas)
    w["ano"] = w["ano_cod"].astype(int)
    w["local_cod"] = w["local_cod"].astype(int)
    w = w.merge(UF, left_on="local_cod", right_on="uf_cod", how="left")
    br = w["nivel"] == "BR"
    w["uf"] = w["uf"].where(~br, "BR")
    w["uf_nome"] = w["uf_nome"].where(~br, "Brasil")
    w["uf_cod"] = w["uf_cod"].where(~br, 0).astype(int)
    w["regiao"] = w["regiao"].where(~br, "")
    w.loc[w["cultura"] == "Total", "quantidade_t"] = np.nan  # o IBGE não soma toneladas de produtos diferentes
    w["cultura"] = pd.Categorical(w["cultura"], list(culturas.values()))
    w = w.sort_values(["ano", "uf_cod", "cultura"]).reset_index(drop=True)
    w["cultura"] = w["cultura"].astype(str)
    w = w[["ano", "nivel", "uf_cod", "uf", "uf_nome", "regiao", "cultura", "area_plantada_ha", "area_colhida_ha", "quantidade_t", "valor_producao_mil_reais"]]
    w = w.dropna(subset=["area_plantada_ha", "area_colhida_ha", "quantidade_t", "valor_producao_mil_reais"], how="all")
    P = "IBGE, PAM, SIDRA 5457"
    salvar(w, "uf_anual_area_culturas_pam.csv", [
        ("ano", "Ano civil", "ano", P), ("nivel", "BR (Brasil) ou UF", "", P),
        ("uf_cod", "Código IBGE da UF (0 para o Brasil)", "", "IBGE"), ("uf", "Sigla da UF (BR para o Brasil)", "", "IBGE"),
        ("uf_nome", "Nome da UF", "", "IBGE"), ("regiao", "Grande Região", "", "IBGE"),
        ("cultura", "Total das lavouras ou uma das nove culturas principais", "", P),
        ("area_plantada_ha", "Área plantada ou destinada à colheita (1988 em diante)", "ha", P + ", variável 8331"),
        ("area_colhida_ha", "Área colhida", "ha", P + ", variável 216"),
        ("quantidade_t", "Quantidade produzida (vazio para o total; laranja em t só a partir de 2001)", "t", P + ", variável 214"),
        ("valor_producao_mil_reais", "Valor da produção, em reais correntes (1994 em diante)", "mil R$", P + ", variável 215"),
    ], f"{w.ano.min()}-{w.ano.max()}")
    return w


def censos():
    p = ultima("brutos", "ibge_sidra")
    saidas = {}
    for nivel in ("br_uf", "municipios"):
        def ler(nome):
            return pd.read_csv(os.path.join(p, f"{nome}_{nivel}.csv"), dtype=str).assign(v=lambda d: num(d["valor"]))

        chave = ["nivel_cod", "local_cod", "local_nome"]

        def larga(d, col, mapa, extra=None):
            d = d[d[col].isin(mapa)]
            if extra is not None:
                d = d[extra(d)]
            return d.assign(c=d[col].map(mapa)).pivot(index=chave, columns="c", values="v").reset_index()

        # --- 2017
        a17 = ler("censo2017_6847_uso_adubacao")
        a17 = larga(a17[a17["tipologia_cod"] == "46302"], "uso_de_adubacao_cod",
                    {"46545": "estab_total", "46546": "estab_adubou_no_ano", "46547": "estab_so_quimica", "46548": "estab_so_organica",
                     "46549": "estab_quimica_e_organica", "46552": "_costuma"})
        a17["estab_costuma_adubar"] = a17["estab_adubou_no_ano"] + a17["_costuma"]
        a17["estab_adubacao_quimica"] = a17["estab_so_quimica"] + a17["estab_quimica_e_organica"]
        c17 = ler("censo2017_6849_uso_calcario")
        c17 = larga(c17[c17["tipologia_cod"] == "46302"], "uso_de_calcario_e_ou_outros_corretivos_d_cod", {"46554": "estab_aplicou_calcario"})
        d17 = ler("censo2017_6899_despesas")
        d17 = d17[d17["tipologia_cod"] == "46302"]
        v17 = larga(d17[d17["variavel_cod"] == "1996"], "tipo_de_despesa_cod",
                    {"113946": "despesa_total_mil_reais", "45953": "despesa_adubos_corretivos_mil_reais", "111966": "despesa_agrotoxicos_mil_reais"})
        n17 = larga(d17[d17["variavel_cod"] == "2"], "tipo_de_despesa_cod", {"45953": "estab_com_despesa_adubos_corretivos"})
        c2017 = a17.merge(c17, on=chave, how="left").merge(v17, on=chave, how="left").merge(n17, on=chave, how="left")
        c2017["ano_censo"] = 2017

        # --- 2006
        a06 = larga(ler("censo2006_864_uso_adubacao"), "uso_de_adubacao_cod",
                    {"0": "estab_total", "114541": "estab_costuma_adubar", "112008": "_nao_precisou"})
        a06["estab_adubou_no_ano"] = a06["estab_costuma_adubar"] - a06["_nao_precisou"]
        d06 = ler("censo2006_833_despesas")
        d06 = d06[d06["grupos_de_atividade_economica_cod"] == "113601"]
        v06 = larga(d06[d06["variavel_cod"] == "1996"], "tipo_de_despesa_cod",
                    {"113946": "despesa_total_mil_reais", "111960": "despesa_adubos_mil_reais", "111961": "despesa_corretivos_mil_reais",
                     "111966": "despesa_agrotoxicos_mil_reais"})
        v06["despesa_adubos_corretivos_mil_reais"] = v06["despesa_adubos_mil_reais"] + v06["despesa_corretivos_mil_reais"]
        n06 = larga(d06[d06["variavel_cod"] == "2"], "tipo_de_despesa_cod",
                    {"111960": "estab_com_despesa_adubos", "111961": "estab_com_despesa_corretivos"})
        c2006 = a06.merge(v06, on=chave, how="left").merge(n06, on=chave, how="left")
        c2006["ano_censo"] = 2006

        c = pd.concat([c2006, c2017], ignore_index=True)
        c["pct_adubou_no_ano"] = razao(c["estab_adubou_no_ano"], c["estab_total"], 100).round(2)
        c["pct_costuma_adubar"] = razao(c["estab_costuma_adubar"], c["estab_total"], 100).round(2)
        c["pct_adubacao_quimica"] = razao(c["estab_adubacao_quimica"], c["estab_total"], 100).round(2)
        c["pct_aplicou_calcario"] = razao(c["estab_aplicou_calcario"], c["estab_total"], 100).round(2)
        c["pct_despesa_adubos_corretivos"] = razao(c["despesa_adubos_corretivos_mil_reais"], c["despesa_total_mil_reais"], 100).round(2)
        c["local_cod"] = c["local_cod"].astype(int)
        ind = ["estab_total", "estab_adubou_no_ano", "estab_costuma_adubar", "pct_adubou_no_ano", "pct_costuma_adubar",
               "estab_so_quimica", "estab_so_organica", "estab_quimica_e_organica", "estab_adubacao_quimica", "pct_adubacao_quimica",
               "estab_aplicou_calcario", "pct_aplicou_calcario",
               "estab_com_despesa_adubos", "estab_com_despesa_corretivos", "estab_com_despesa_adubos_corretivos",
               "despesa_adubos_mil_reais", "despesa_corretivos_mil_reais", "despesa_adubos_corretivos_mil_reais",
               "despesa_agrotoxicos_mil_reais", "despesa_total_mil_reais", "pct_despesa_adubos_corretivos"]
        S = "IBGE, Censo Agropecuário"
        dic_ind = [
            ("estab_total", "Estabelecimentos agropecuários", "unidades", S + ", SIDRA 864 (2006) e 6847 (2017)"),
            ("estab_adubou_no_ano", "Estabelecimentos que adubaram no ano de referência (2006: 'usa' menos 'não precisou usar em 2006')", "unidades", S),
            ("estab_costuma_adubar", "Estabelecimentos que costumam adubar (2017: adubou + não adubou mas costuma)", "unidades", S),
            ("pct_adubou_no_ano", "Participação dos que adubaram no ano", "%", "cálculo próprio"),
            ("pct_costuma_adubar", "Participação dos que costumam adubar", "%", "cálculo próprio"),
            ("estab_so_quimica", "Fez só adubação química (só 2017)", "unidades", S + ", SIDRA 6847"),
            ("estab_so_organica", "Fez só adubação orgânica (só 2017)", "unidades", S + ", SIDRA 6847"),
            ("estab_quimica_e_organica", "Fez adubação química e orgânica (só 2017)", "unidades", S + ", SIDRA 6847"),
            ("estab_adubacao_quimica", "Fez adubação química, com ou sem orgânica (só 2017)", "unidades", "cálculo próprio"),
            ("pct_adubacao_quimica", "Participação dos que fizeram adubação química (só 2017)", "%", "cálculo próprio"),
            ("estab_aplicou_calcario", "Aplicou calcário ou outro corretivo de pH (só 2017)", "unidades", S + ", SIDRA 6849"),
            ("pct_aplicou_calcario", "Participação dos que aplicaram calcário (só 2017)", "%", "cálculo próprio"),
            ("estab_com_despesa_adubos", "Estabelecimentos com despesa em adubos (só 2006)", "unidades", S + ", SIDRA 833"),
            ("estab_com_despesa_corretivos", "Estabelecimentos com despesa em corretivos do solo (só 2006)", "unidades", S + ", SIDRA 833"),
            ("estab_com_despesa_adubos_corretivos", "Estabelecimentos com despesa em adubos e corretivos (só 2017)", "unidades", S + ", SIDRA 6899"),
            ("despesa_adubos_mil_reais", "Despesa com adubos, em reais do ano do censo (só 2006)", "mil R$", S + ", SIDRA 833"),
            ("despesa_corretivos_mil_reais", "Despesa com corretivos do solo, em reais do ano do censo (só 2006)", "mil R$", S + ", SIDRA 833"),
            ("despesa_adubos_corretivos_mil_reais", "Despesa com adubos e corretivos, em reais do ano do censo (2006: soma das duas rubricas)", "mil R$", S),
            ("despesa_agrotoxicos_mil_reais", "Despesa com agrotóxicos, em reais do ano do censo", "mil R$", S),
            ("despesa_total_mil_reais", "Despesa total dos estabelecimentos, em reais do ano do censo", "mil R$", S),
            ("pct_despesa_adubos_corretivos", "Adubos e corretivos na despesa total", "%", "cálculo próprio"),
        ]
        for col in ind:
            if col not in c.columns:
                c[col] = np.nan
        if nivel == "br_uf":
            c = c.merge(UF, left_on="local_cod", right_on="uf_cod", how="left")
            br = c["nivel_cod"] == "1"
            c["nivel"] = np.where(br, "BR", "UF")
            c["uf"] = c["uf"].where(~br, "BR")
            c["uf_nome"] = c["uf_nome"].where(~br, "Brasil")
            c["uf_cod"] = c["uf_cod"].where(~br, 0).astype(int)
            c["regiao"] = c["regiao"].where(~br, "")
            c = c.sort_values(["ano_censo", "uf_cod"]).reset_index(drop=True)
            c = c[["ano_censo", "nivel", "uf_cod", "uf", "uf_nome", "regiao"] + ind]
            saidas["uf"] = salvar(c, "uf_censo_adubacao.csv", [
                ("ano_censo", "Ano de referência do Censo Agropecuário", "2006 ou 2017", S), ("nivel", "BR (Brasil) ou UF", "", S),
                ("uf_cod", "Código IBGE da UF (0 para o Brasil)", "", "IBGE"), ("uf", "Sigla da UF (BR para o Brasil)", "", "IBGE"),
                ("uf_nome", "Nome da UF", "", "IBGE"), ("regiao", "Grande Região", "", "IBGE")] + dic_ind, "2006 e 2017")
        else:
            c["municipio"] = c["local_nome"].str.replace(r" - [A-Z]{2}$", "", regex=True)
            c["uf"] = c["local_nome"].str.extract(r" - ([A-Z]{2})$")[0]
            c = c.rename(columns={"local_cod": "municipio_cod"}).sort_values(["ano_censo", "municipio_cod"]).reset_index(drop=True)
            c = c[["ano_censo", "municipio_cod", "municipio", "uf"] + ind]
            saidas["mun"] = salvar(c, "mun_censo_adubacao.csv", [
                ("ano_censo", "Ano de referência do Censo Agropecuário", "2006 ou 2017", S),
                ("municipio_cod", "Código IBGE do município (7 dígitos)", "", "IBGE"),
                ("municipio", "Nome do município", "", "IBGE"), ("uf", "Sigla da UF", "", "IBGE")] + dic_ind, "2006 e 2017")
    return saidas


# ----------------------------------------------------------------- painéis integrados
def paineis(nut, m_anda, prc, cmx, cmx_uf, ids_uf, pam_uf, censo_uf, ano_parcial):
    # --- Brasil, anual
    f = nut[nut["nutriente"] != "NPK"]
    largo = {}
    for col, suf in [("uso_agricola_t", "uso_t"), ("producao_t", "producao_t"), ("importacao_t", "importacao_t"),
                     ("exportacao_t", "exportacao_t"), ("dependencia_importacao_pct", "dependencia_pct"), ("uso_kg_ha", "kg_ha")]:
        w = f.pivot(index="ano", columns="nutriente", values=col)
        for n in ["N", "P2O5", "K2O"]:
            largo[f"fao_{n.lower()}_{suf}"] = w[n]
    a = pd.DataFrame(largo)
    npk = nut[nut["nutriente"] == "NPK"].set_index("ano")
    a["fao_npk_uso_t"] = npk["uso_agricola_t"]
    a["fao_npk_importacao_t"] = npk["importacao_t"]
    a["fao_npk_producao_t"] = npk["producao_t"]
    a["fao_npk_dependencia_pct"] = npk["dependencia_importacao_pct"]
    a["fao_npk_kg_ha"] = npk["uso_kg_ha"]

    g = m_anda.groupby("ano")
    an = g[["entregas_t", "producao_t", "importacao_t", "exportacao_t"]].sum(min_count=1)
    an.columns = ["anda_" + c for c in an.columns]
    an["anda_meses"] = g["entregas_t"].count()
    c31 = cmx[cmx["grupo_sh4"] == "31"].groupby("ano")
    cx = c31[["importacao_t", "importacao_fob_usd", "exportacao_t"]].sum(min_count=1)
    cx.columns = ["comex_importacao_t", "comex_importacao_fob_usd", "comex_exportacao_t"]
    cx["comex_meses"] = c31["importacao_t"].count()
    br = pam_uf[(pam_uf["nivel"] == "BR") & (pam_uf["cultura"] == "Total")].set_index("ano")
    pa = br[["area_plantada_ha", "area_colhida_ha"]].add_prefix("pam_")
    pcols = ["ureia_usd_t", "dap_usd_t", "tsp_usd_t", "kcl_usd_t", "rocha_fosfatica_usd_t", "gas_natural_europa_usd_mmbtu",
             "soja_usd_t", "milho_usd_t", "cambio_brl_usd_media", "cambio_real_efetivo_indice"]
    pm = prc.groupby("ano")[pcols].mean().round(3)
    pm.loc[pm.index < 1995, "cambio_brl_usd_media"] = np.nan
    pm["precos_meses"] = prc.groupby("ano")["ureia_usd_t"].count()
    a = a.join([an, cx, pa, pm], how="outer").sort_index()
    a = a[a.index >= 1961].reset_index().rename(columns={"index": "ano"})
    a["ano_parcial"] = (a["ano"] == ano_parcial).astype(int)
    F, A, C, P, B = "FAOSTAT RFN", "ANDA", "Comex Stat", "Banco Mundial, Pink Sheet", "BCB-SGS"
    dic = [("ano", "Ano civil", "ano", "")]
    for suf, d, u in [("uso_t", "Uso agrícola", "t de nutriente"), ("producao_t", "Produção", "t de nutriente"),
                      ("importacao_t", "Importação", "t de nutriente"), ("exportacao_t", "Exportação", "t de nutriente"),
                      ("dependencia_pct", "Importação dividida pelo uso agrícola", "%"), ("kg_ha", "Uso por área de lavoura", "kg/ha")]:
        for n in ["N", "P2O5", "K2O"]:
            dic.append((f"fao_{n.lower()}_{suf}", f"{d} de {n}", u, F))
    dic += [("fao_npk_uso_t", "Uso agrícola de N + P2O5 + K2O", "t de nutriente", F),
            ("fao_npk_importacao_t", "Importação de N + P2O5 + K2O", "t de nutriente", F),
            ("fao_npk_producao_t", "Produção de N + P2O5 + K2O", "t de nutriente", F),
            ("fao_npk_dependencia_pct", "Importação dividida pelo uso agrícola, N + P2O5 + K2O", "%", F),
            ("fao_npk_kg_ha", "Uso de N + P2O5 + K2O por área de lavoura", "kg/ha", F),
            ("anda_entregas_t", "Entregas ao mercado, soma dos meses disponíveis", "t de produto", A),
            ("anda_producao_t", "Produção nacional, soma dos meses disponíveis", "t de produto", A),
            ("anda_importacao_t", "Importação, soma dos meses disponíveis", "t de produto", A),
            ("anda_exportacao_t", "Exportação, soma dos meses disponíveis (2013 em diante)", "t de produto", A),
            ("anda_meses", "Meses com dado de entregas no ano", "meses", A),
            ("comex_importacao_t", "Importação do capítulo 31 (NBM até 1996, NCM depois)", "t de produto", C),
            ("comex_importacao_fob_usd", "Importação do capítulo 31, valor FOB", "US$", C),
            ("comex_exportacao_t", "Exportação do capítulo 31 (1997 em diante)", "t de produto", C),
            ("comex_meses", "Meses com dado de importação no ano", "meses", C),
            ("pam_area_plantada_ha", "Área plantada, total das lavouras (1988 em diante)", "ha", "IBGE, PAM"),
            ("pam_area_colhida_ha", "Área colhida, total das lavouras", "ha", "IBGE, PAM"),
            ("ureia_usd_t", "Ureia, média anual", "US$/t", P), ("dap_usd_t", "DAP, média anual", "US$/t", P),
            ("tsp_usd_t", "TSP, média anual", "US$/t", P), ("kcl_usd_t", "Cloreto de potássio, média anual", "US$/t", P),
            ("rocha_fosfatica_usd_t", "Rocha fosfática, média anual", "US$/t", P),
            ("gas_natural_europa_usd_mmbtu", "Gás natural na Europa, média anual", "US$/mmbtu", P),
            ("soja_usd_t", "Soja, média anual", "US$/t", P), ("milho_usd_t", "Milho, média anual", "US$/t", P),
            ("cambio_brl_usd_media", "Câmbio, média das médias mensais (1995 em diante)", "R$/US$", B + " 3698"),
            ("cambio_real_efetivo_indice", "Câmbio real efetivo (IPCA), média anual", "jun/1994 = 100", B + " 11752"),
            ("precos_meses", "Meses com preço da ureia no ano", "meses", P),
            ("ano_parcial", "1 quando o ano não está completo nas fontes mensais", "0/1", "")]
    salvar(a, "painel_br_anual.csv", dic, f"{a.ano.min()}-{a.ano.max()}")

    # --- Brasil, mensal
    m = m_anda[["data", "entregas_t", "producao_t", "importacao_t", "exportacao_t"]].copy()
    m.columns = ["data", "anda_entregas_t", "anda_producao_t", "anda_importacao_t", "anda_exportacao_t"]
    t = cmx[cmx["grupo_sh4"] == "31"][["data", "importacao_t", "importacao_fob_usd", "importacao_cif_usd", "exportacao_t",
                                       "preco_medio_importacao_fob_usd_t"]]
    t.columns = ["data", "comex_importacao_t", "comex_importacao_fob_usd", "comex_importacao_cif_usd", "comex_exportacao_t", "comex_preco_medio_fob_usd_t"]
    gr = cmx[cmx["grupo_sh4"].isin(["3102", "3103", "3104", "3105"])].pivot(index="data", columns="grupo_sh4", values="importacao_t")
    gr.columns = ["comex_imp_" + {"3102": "nitrogenados", "3103": "fosfatados", "3104": "potassicos", "3105": "mistos"}[c] + "_t" for c in gr.columns]
    pcm = ["ureia_usd_t", "dap_usd_t", "tsp_usd_t", "kcl_usd_t", "rocha_fosfatica_usd_t", "gas_natural_europa_usd_mmbtu", "soja_usd_t",
           "milho_usd_t", "cambio_brl_usd_media", "cambio_real_efetivo_indice"]
    mm = m.merge(t, on="data", how="outer").merge(gr.reset_index(), on="data", how="outer").merge(prc[["data"] + pcm], on="data", how="left")
    mm = mm[mm["data"] >= "1997-01-01"].sort_values("data").reset_index(drop=True)
    mm.insert(1, "ano", mm["data"].str[:4].astype(int))
    mm.insert(2, "mes", mm["data"].str[5:7].astype(int))
    dicm = [("data", "Mês de referência (primeiro dia)", "AAAA-MM-DD", ""), ("ano", "Ano", "ano", ""), ("mes", "Mês", "1-12", ""),
            ("anda_entregas_t", "Entregas ao mercado", "t de produto", A), ("anda_producao_t", "Produção nacional", "t de produto", A),
            ("anda_importacao_t", "Importação segundo a ANDA", "t de produto", A),
            ("anda_exportacao_t", "Exportação segundo a ANDA (2013 em diante)", "t de produto", A),
            ("comex_importacao_t", "Importação do capítulo 31", "t de produto", C),
            ("comex_importacao_fob_usd", "Importação do capítulo 31, valor FOB", "US$", C),
            ("comex_importacao_cif_usd", "Importação do capítulo 31, valor CIF", "US$", C),
            ("comex_exportacao_t", "Exportação do capítulo 31", "t de produto", C),
            ("comex_preco_medio_fob_usd_t", "Valor FOB dividido pelo peso importado, capítulo 31", "US$/t", "cálculo próprio"),
            ("comex_imp_nitrogenados_t", "Importação da posição 3102", "t de produto", C),
            ("comex_imp_fosfatados_t", "Importação da posição 3103", "t de produto", C),
            ("comex_imp_potassicos_t", "Importação da posição 3104", "t de produto", C),
            ("comex_imp_mistos_t", "Importação da posição 3105 (NPK, MAP, DAP e outros)", "t de produto", C),
            ("ureia_usd_t", "Ureia", "US$/t", P), ("dap_usd_t", "DAP", "US$/t", P), ("tsp_usd_t", "TSP", "US$/t", P),
            ("kcl_usd_t", "Cloreto de potássio", "US$/t", P), ("rocha_fosfatica_usd_t", "Rocha fosfática", "US$/t", P),
            ("gas_natural_europa_usd_mmbtu", "Gás natural na Europa", "US$/mmbtu", P), ("soja_usd_t", "Soja", "US$/t", P),
            ("milho_usd_t", "Milho", "US$/t", P), ("cambio_brl_usd_media", "Câmbio, média do mês", "R$/US$", B + " 3698"),
            ("cambio_real_efetivo_indice", "Câmbio real efetivo (IPCA)", "jun/1994 = 100", B + " 11752")]
    salvar(mm, "painel_br_mensal.csv", dicm, f"{mm.data.min()[:7]} a {mm.data.max()[:7]}")

    # --- UF, anual
    i = ids_uf[ids_uf["nivel"] == "UF"]
    iw = i.pivot(index=["ano", "uf"], columns="nutriente", values="entregas_t")
    iw.columns = ["ids_entregas_" + c.lower() + "_t" for c in iw.columns]
    ik = i[i["nutriente"] == "Total"].set_index(["ano", "uf"])[["kg_ha"]].rename(columns={"kg_ha": "ids_kg_ha"})
    cu = cmx_uf[cmx_uf["grupo_sh4"] == "31"].set_index(["ano", "uf"])[["importacao_t", "importacao_fob_usd"]].add_prefix("comex_")
    pu = pam_uf[pam_uf["nivel"] == "UF"]
    pt = pu[pu["cultura"] == "Total"].set_index(["ano", "uf"])[["area_plantada_ha", "area_colhida_ha"]].add_prefix("pam_")
    pc = pu[pu["cultura"].isin(["Soja", "Milho", "Cana-de-açúcar"])].pivot(index=["ano", "uf"], columns="cultura", values="area_colhida_ha")
    pc = pc.rename(columns={"Soja": "pam_soja_colhida_ha", "Milho": "pam_milho_colhida_ha", "Cana-de-açúcar": "pam_cana_colhida_ha"})
    ce = censo_uf[censo_uf["nivel"] == "UF"].rename(columns={"ano_censo": "ano"}).set_index(["ano", "uf"])[
        ["pct_adubou_no_ano", "pct_costuma_adubar", "despesa_adubos_corretivos_mil_reais"]].add_prefix("censo_")
    u = pt.join([pc, cu, iw, ik, ce], how="outer")
    # painel balanceado: todas as UFs em todos os anos (vazio onde a fonte não cobre)
    anos = range(int(u.index.get_level_values("ano").min()), int(u.index.get_level_values("ano").max()) + 1)
    u = u.reindex(pd.MultiIndex.from_product([anos, UF["uf"]], names=["ano", "uf"])).reset_index()
    u = u.merge(UF, on="uf", how="left").sort_values(["ano", "uf_cod"]).reset_index(drop=True)
    u["ano_parcial"] = (u["ano"] == ano_parcial).astype(int)
    ordem = ["ano", "uf_cod", "uf", "uf_nome", "regiao", "pam_area_plantada_ha", "pam_area_colhida_ha", "pam_soja_colhida_ha",
             "pam_milho_colhida_ha", "pam_cana_colhida_ha", "comex_importacao_t", "comex_importacao_fob_usd", "ids_entregas_total_t",
             "ids_entregas_n_t", "ids_entregas_p2o5_t", "ids_entregas_k2o_t", "ids_kg_ha", "censo_pct_adubou_no_ano",
             "censo_pct_costuma_adubar", "censo_despesa_adubos_corretivos_mil_reais", "ano_parcial"]
    u = u[ordem]
    I = "IBGE, IDS, SIDRA 770"
    salvar(u, "painel_uf_anual.csv", [
        ("ano", "Ano civil", "ano", ""), ("uf_cod", "Código IBGE da UF", "", "IBGE"), ("uf", "Sigla da UF", "", "IBGE"),
        ("uf_nome", "Nome da UF", "", "IBGE"), ("regiao", "Grande Região", "", "IBGE"),
        ("pam_area_plantada_ha", "Área plantada, total das lavouras (1988 em diante)", "ha", "IBGE, PAM"),
        ("pam_area_colhida_ha", "Área colhida, total das lavouras", "ha", "IBGE, PAM"),
        ("pam_soja_colhida_ha", "Área colhida de soja", "ha", "IBGE, PAM"),
        ("pam_milho_colhida_ha", "Área colhida de milho", "ha", "IBGE, PAM"),
        ("pam_cana_colhida_ha", "Área colhida de cana-de-açúcar", "ha", "IBGE, PAM"),
        ("comex_importacao_t", "Importação do capítulo 31 por UF do produto (1997 em diante)", "t de produto", C),
        ("comex_importacao_fob_usd", "Importação do capítulo 31, valor FOB", "US$", C),
        ("ids_entregas_total_t", "Entregas ao consumidor final, N + P2O5 + K2O (2007-2014)", "t de nutriente", I),
        ("ids_entregas_n_t", "Entregas de N (2007-2014)", "t de nutriente", I),
        ("ids_entregas_p2o5_t", "Entregas de P2O5 (2007-2014)", "t de nutriente", I),
        ("ids_entregas_k2o_t", "Entregas de K2O (2007-2014)", "t de nutriente", I),
        ("ids_kg_ha", "Fertilizantes por área plantada (2007-2014)", "kg/ha", I),
        ("censo_pct_adubou_no_ano", "Estabelecimentos que adubaram no ano (só 2006 e 2017)", "%", "IBGE, Censo Agropecuário"),
        ("censo_pct_costuma_adubar", "Estabelecimentos que costumam adubar (só 2006 e 2017)", "%", "IBGE, Censo Agropecuário"),
        ("censo_despesa_adubos_corretivos_mil_reais", "Despesa com adubos e corretivos, reais do ano do censo (só 2006 e 2017)", "mil R$", "IBGE, Censo Agropecuário"),
        ("ano_parcial", "1 quando o ano não está completo no Comex Stat", "0/1", ""),
    ], f"{u.ano.min()}-{u.ano.max()}")
    return a, mm, u


# ----------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description="Consolida as bases em séries prontas para análise.")
    ap.add_argument("--sem-site", action="store_true", help="não copia os arquivos para docs/dados")
    args = ap.parse_args()

    log("FAOSTAT"); nut = faostat()
    log("ANDA"); m_anda = anda()
    log("Preços e câmbio"); prc = precos()
    log("Comex Stat"); cmx, cmx_uf, ano_parcial, ultimo_mes = comex()
    log("IBGE: IDS"); ids_uf = ids()
    log("IBGE: PAM"); pam_uf = pam()
    log("IBGE: Censos"); cen = censos()
    log("Painéis"); paineis(nut, m_anda, prc, cmx, cmx_uf, ids_uf, pam_uf, cen["uf"], ano_parcial)

    pd.DataFrame(DIC).to_csv(os.path.join(SAIDA, "DICIONARIO.csv"), index=False, encoding="utf-8", lineterminator="\n")
    if set(DESCRICOES) != set(RESUMO):
        raise ValueError(f"DESCRICOES e arquivos gerados não batem: {set(DESCRICOES) ^ set(RESUMO)}")
    arquivos = {}
    for nome, (nivel, freq, conteudo, fonte) in DESCRICOES.items():  # na ordem em que aparecem no site
        arquivos[nome] = {"nivel": nivel, "frequencia": freq, "conteudo": conteudo, "fonte": fonte,
                          "bytes": os.path.getsize(os.path.join(SAIDA, nome)), **RESUMO[nome]}
    meta = {"gerado_em": datetime.date.today().isoformat(), "versoes_das_fontes": VERSOES,
            "comex_ano_parcial": ano_parcial, "comex_ultimo_mes": ultimo_mes, "arquivos": arquivos}
    with open(os.path.join(SAIDA, "metadados.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    log(f"dicionário: {len(DIC)} colunas descritas; {len(RESUMO)} arquivos em {SAIDA}")

    if not args.sem_site:
        os.makedirs(SITE, exist_ok=True)
        for nome in sorted(os.listdir(SAIDA)):
            if nome.endswith((".csv", ".json")):
                shutil.copyfile(os.path.join(SAIDA, nome), os.path.join(SITE, nome))
        shutil.copyfile(os.path.join(BASE, "MANIFESTO.csv"), os.path.join(SITE, "MANIFESTO.csv"))
        log(f"cópia para o site em {SITE}")


if __name__ == "__main__":
    sys.exit(main())
