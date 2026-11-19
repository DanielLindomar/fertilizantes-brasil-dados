# -*- coding: utf-8 -*-
"""
Confere a coerência interna das séries em dados/consolidados.

Uso:
    python validar_consolidados.py

Cada teste compara as séries entre si ou com as tabelas de origem (chaves únicas,
somas que precisam fechar, valores não negativos). Termina com código 1 se algum falhar.
No fim, imprime os números de referência para conferência visual com as fontes.
"""
import os, sys

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(BASE, "consolidados")
FALHAS = []


def ler(nome, **kw):
    return pd.read_csv(os.path.join(C, nome), **kw)


def teste(nome, ok, detalhe=""):
    print(("  ok    " if ok else "  FALHA ") + nome + (f"  [{detalhe}]" if detalhe else ""))
    if not ok:
        FALHAS.append(nome)


def main():
    sh = {"grupo_sh4": str}
    nut = ler("br_anual_nutrientes_faostat.csv")
    anda = ler("br_mensal_anda.csv")
    prc = ler("br_mensal_precos_cambio.csv")
    cmx = ler("br_mensal_comercio_comex.csv", dtype=sh)
    ncm = ler("br_mensal_importacao_ncm.csv", dtype={"ncm": str, "grupo_sh4": str})
    ori = ler("br_anual_importacao_origem.csv", dtype=sh)
    ufc = ler("uf_anual_importacao_comex.csv", dtype=sh)
    ids = ler("uf_anual_entregas_nutriente_ids.csv")
    pam = ler("uf_anual_area_culturas_pam.csv")
    cuf = ler("uf_censo_adubacao.csv")
    mun = ler("mun_censo_adubacao.csv")
    pba, pbm, puf = ler("painel_br_anual.csv"), ler("painel_br_mensal.csv"), ler("painel_uf_anual.csv")
    dic = ler("DICIONARIO.csv")

    print("Chaves únicas")
    for nome, df, chave in [
        ("nutrientes FAOSTAT", nut, ["ano", "nutriente"]), ("ANDA mensal", anda, ["data"]), ("preços e câmbio", prc, ["data"]),
        ("Comex mensal por grupo", cmx, ["data", "grupo_sh4"]), ("Comex mensal por NCM", ncm, ["data", "ncm"]),
        ("origem das importações", ori, ["ano", "pais", "grupo_sh4"]), ("importação por UF", ufc, ["ano", "uf", "grupo_sh4"]),
        ("IDS", ids, ["ano", "nivel", "local_cod", "nutriente"]), ("PAM", pam, ["ano", "uf_cod", "cultura"]),
        ("Censo por UF", cuf, ["ano_censo", "uf"]), ("Censo por município", mun, ["ano_censo", "municipio_cod"]),
        ("painel Brasil anual", pba, ["ano"]), ("painel Brasil mensal", pbm, ["data"]), ("painel UF anual", puf, ["ano", "uf"]),
    ]:
        teste(nome, not df.duplicated(chave).any())

    print("Somas que precisam fechar")
    npk = nut[nut.nutriente != "NPK"].groupby("ano").uso_agricola_t.sum()
    teste("FAOSTAT: N + P2O5 + K2O = NPK", np.allclose(npk, nut[nut.nutriente == "NPK"].set_index("ano").uso_agricola_t))
    g = cmx[cmx.grupo_sh4 != "31"].groupby("data").importacao_t.sum()
    teste("Comex: soma das posições = capítulo 31", np.allclose(g, cmx[cmx.grupo_sh4 == "31"].set_index("data").importacao_t.reindex(g.index)))
    a = ncm.groupby("ano").importacao_t.sum()
    b = cmx[(cmx.grupo_sh4 == "31") & (cmx.nomenclatura == "NCM")].groupby("ano").importacao_t.sum()
    teste("Comex: soma das NCM = capítulo 31", np.allclose(a, b))
    for nome, df in [("origem", ori[ori.nomenclatura == "NCM"]), ("UF", ufc)]:
        s = df[df.grupo_sh4 == "31"].groupby("ano").importacao_t.sum()
        teste(f"Comex: soma por {nome} = total nacional", np.allclose(s, b.reindex(s.index)))
    p = ori[ori.grupo_sh4 == "31"].groupby("ano").participacao_pct.sum()
    teste("Comex: participações dos países somam 100%", np.allclose(p, 100, atol=0.05))
    t = ids[(ids.nutriente == "Total") & ids.entregas_t.notna()]
    teste("IDS: soma das UFs = Brasil", np.allclose(t[t.nivel == "UF"].groupby("ano").entregas_t.sum(), t[t.nivel == "BR"].set_index("ano").entregas_t))
    teste("IDS: soma das regiões = Brasil", np.allclose(t[t.nivel == "GR"].groupby("ano").entregas_t.sum(), t[t.nivel == "BR"].set_index("ano").entregas_t))
    n = ids[(ids.nivel == "UF") & (ids.nutriente != "Total")].groupby(["ano", "uf"]).entregas_t.sum()
    teste("IDS: N + P2O5 + K2O = total, por UF", np.allclose(n, t[t.nivel == "UF"].set_index(["ano", "uf"]).entregas_t.reindex(n.index), rtol=1e-4, atol=3))
    x = pam[pam.cultura == "Total"]
    dif = (x[x.nivel == "UF"].groupby("ano").area_colhida_ha.sum() / x[x.nivel == "BR"].set_index("ano").area_colhida_ha - 1).abs()
    # em 1974 a própria fonte tem 0,16% da área do Brasil sem UF
    teste("PAM: soma das UFs = Brasil (área colhida, tolerância de 0,5%)", (dif < 0.005).all(), f"maior diferença {dif.max() * 100:.2f}% em {dif.idxmax()}")
    for ano in (2006, 2017):
        u = cuf[cuf.ano_censo == ano]
        m = mun[mun.ano_censo == ano]
        br = u[u.nivel == "BR"].iloc[0]
        teste(f"Censo {ano}: soma das UFs = Brasil", u[u.nivel == "UF"].estab_total.sum() == br.estab_total)
        teste(f"Censo {ano}: soma dos municípios = Brasil", m.estab_total.sum() == br.estab_total and m.estab_adubou_no_ano.sum() == br.estab_adubou_no_ano)

    print("Coerência entre arquivos")
    s = anda.groupby("ano").entregas_t.sum()
    teste("painel anual = soma mensal da ANDA", np.allclose(pba.set_index("ano").anda_entregas_t.dropna(), s.reindex(pba.set_index("ano").anda_entregas_t.dropna().index)))
    j = pbm.merge(anda, on="data", how="inner")
    teste("painel mensal = série da ANDA", np.allclose(j.anda_entregas_t, j.entregas_t, equal_nan=True))
    q = puf.groupby("ano").size()
    teste("painel UF balanceado (27 UFs por ano)", (q == 27).all(), f"{q.index.min()}-{q.index.max()}")
    datas = pd.to_datetime(pbm.data)
    teste("painel mensal sem meses faltando", len(pd.date_range(datas.min(), datas.max(), freq="MS")) == len(pbm))

    print("Valores e documentação")
    for nome, df in [("ANDA", anda), ("preços", prc), ("Comex por grupo", cmx), ("Comex por UF", ufc), ("IDS", ids), ("PAM", pam), ("Censo municipal", mun)]:
        numericas = df.select_dtypes("number")
        teste(f"{nome}: sem valores negativos", not (numericas < 0).any().any())
    teste("dependência de importação entre 0 e 150%", nut.dependencia_importacao_pct.dropna().between(0, 150).all())
    for arq in sorted(f for f in os.listdir(C) if f.endswith(".csv") and f != "DICIONARIO.csv"):
        cols = list(pd.read_csv(os.path.join(C, arq), nrows=0).columns)
        teste(f"dicionário cobre {arq}", cols == dic[dic.arquivo == arq].coluna.tolist())

    print("\nNúmeros de referência (conferir com as fontes)")
    u = nut[nut.ano == nut.ano.max()].set_index("nutriente")
    for k in ["N", "P2O5", "K2O"]:
        print(f"  FAOSTAT {nut.ano.max()}, {k}: uso {u.uso_agricola_t[k] / 1e6:.2f} Mt; importação/uso {u.dependencia_importacao_pct[k]:.0f}%")
    cheios = anda.groupby("ano").entregas_t.agg(["sum", "count"])
    cheio = cheios[cheios["count"] == 12].index.max()
    print(f"  ANDA {cheio}: entregas {cheios.loc[cheio, 'sum'] / 1e6:.2f} Mt de produto")
    c = cmx[(cmx.grupo_sh4 == "31") & (cmx.ano == cheio)]
    print(f"  Comex Stat {cheio}: importação do capítulo 31 {c.importacao_t.sum() / 1e6:.2f} Mt; US$ {c.importacao_fob_usd.sum() / 1e9:.2f} bi FOB")
    top = ori[(ori.ano == cheio) & (ori.grupo_sh4 == "31")].head(3)
    print("  Origens em " + str(cheio) + ": " + "; ".join(f"{r.pais} {r.participacao_pct:.1f}%" for r in top.itertuples()))

    print(f"\n{'TUDO CERTO' if not FALHAS else str(len(FALHAS)) + ' FALHA(S): ' + '; '.join(FALHAS)}")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
