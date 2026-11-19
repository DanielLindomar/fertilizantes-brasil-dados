# Séries consolidadas

Arquivos prontos para análise, gerados por `scripts/consolidar.py` a partir das pastas `brutos/` e `tratados/`. Nada aqui é digitado à mão: para refazer, rode o script.

```bash
python scripts/consolidar.py
python scripts/validar_consolidados.py
```

O primeiro comando recria os 17 arquivos desta pasta e copia tudo para `docs/dados/` (usado pelo site). O segundo confere chaves únicas e somas que precisam fechar.

## Arquivos

O prefixo indica o nível territorial: `br_` (Brasil), `uf_` (unidade da federação), `mun_` (município). `painel_` junta várias fontes na mesma tabela.

| Arquivo | Conteúdo | Período | Fonte |
|---|---|---|---|
| `br_anual_nutrientes_faostat.csv` | Produção, importação, exportação e uso agrícola de N, P2O5 e K2O; kg/ha; dependência de importação | 1961–2024 | FAOSTAT RFN |
| `br_anual_produtos_faostat.csv` | Os mesmos fluxos por produto (ureia, MAP, KCl e outros 20) | 2002–2024 | FAOSTAT RFB |
| `br_anual_balanco_nutrientes_faostat.csv` | Balanço de N, P e K em lavouras: entradas, saídas e eficiência de uso | 1961–2023 | FAOSTAT ESB |
| `br_mensal_anda.csv` | Entregas, produção, importação e exportação de fertilizantes | 1998-01 a 2026-08 | ANDA (PDFs e Ipeadata) |
| `br_mensal_precos_cambio.csv` | Preços internacionais de ureia, DAP, TSP, KCl, rocha fosfática, gás natural, soja e milho; câmbio nominal e real; relações de troca | 1960-01 a 2026-10 | Banco Mundial e BCB |
| `br_mensal_comercio_comex.csv` | Importação e exportação do capítulo 31 por posição (3101 a 3105) | 1989-01 a 2026-10 | Comex Stat |
| `br_mensal_importacao_ncm.csv` | Importação por NCM de 8 dígitos | 1997-01 a 2026-10 | Comex Stat |
| `br_mensal_importacao_materias_primas.csv` | Importação de enxofre, rocha fosfática, ácidos sulfúrico e fosfórico e amônia | 1997-01 a 2026-10 | Comex Stat |
| `br_anual_importacao_origem.csv` | Importação por país de origem e posição, com participação | 1989–2026 | Comex Stat |
| `uf_anual_importacao_comex.csv` | Importação por UF do produto e posição | 1997–2026 | Comex Stat |
| `uf_anual_entregas_nutriente_ids.csv` | Entregas por nutriente e kg/ha, por UF, região e Brasil | 2007–2014 (kg/ha do Brasil desde 1992) | IBGE, IDS |
| `uf_anual_area_culturas_pam.csv` | Área plantada e colhida, quantidade e valor: total e nove culturas | 1974–2025 | IBGE, PAM |
| `uf_censo_adubacao.csv` | Adoção de adubação e calagem e despesa com adubos e corretivos, por UF | 2006 e 2017 | IBGE, Censo Agropecuário |
| `mun_censo_adubacao.csv` | Os mesmos indicadores por município | 2006 e 2017 | IBGE, Censo Agropecuário |
| `painel_br_anual.csv` | Uma linha por ano: FAOSTAT, ANDA, Comex Stat, PAM, preços e câmbio | 1961–2026 | várias |
| `painel_br_mensal.csv` | Uma linha por mês: ANDA, Comex Stat, preços e câmbio | 1997-01 a 2026-10 | várias |
| `painel_uf_anual.csv` | Uma linha por UF e ano (painel balanceado): PAM, Comex Stat, IDS e Censos | 1974–2026 | várias |

`DICIONARIO.csv` descreve cada coluna (descrição, unidade e fonte). `metadados.json` registra a versão de cada fonte usada e a cobertura de cada arquivo.

## Convenções

- CSV em UTF-8, separador vírgula, ponto decimal. No Excel em português, abra por Dados > De Texto/CSV.
- Datas mensais no primeiro dia do mês (`AAAA-MM-01`).
- Quantidades em toneladas. A unidade muda entre fontes e isso importa:
  - FAOSTAT RFN e IDS medem **nutriente** (N, P2O5, K2O);
  - FAOSTAT ESB mede **nutriente elementar** (N, P, K);
  - ANDA, Comex Stat e FAOSTAT RFB medem **produto**.
- Valores monetários são correntes: US$ no comércio e nos preços, mil R$ do ano nos Censos e na PAM.
- Célula vazia significa que a fonte não tem o dado. Nada foi interpolado nem extrapolado.
- Nos dados do IBGE, `-` virou 0; `X` (sigilo), `..` e `...` viraram vazio.

## Decisões de consolidação

**ANDA mensal.** De 2013 em diante vale o PDF "Principais Indicadores" mais recente que publica o mês; de 1998 a 2012, a série do Ipeadata. Os totais anuais de entregas coincidem nas onze edições dos PDFs; de uma edição para outra, a ANDA reviu 22 dos 164 meses de entregas, 79 de produção e 31 de importação, e por isso vale sempre a edição mais recente. O Ipeadata diverge dos PDFs em 54 meses entre 2013 e 2021, e em junho de 2014 repete o valor de março (1.697.722 t, contra 2.682.830 t nos PDFs). A coluna `entregas_ipeadata_t` fica no arquivo para conferência.

**Dependência de importação.** Há duas medidas em `br_anual_nutrientes_faostat.csv`. `dependencia_importacao_pct` é importação dividida pelo uso agrícola, a mesma razão usada no catálogo; pode passar de 100% em anos de formação de estoque. `dependencia_liquida_pct` é importação líquida dividida pelo consumo aparente. O uso agrícola de 2002 em diante tem flag `I` (imputado pela FAO).

**NPK.** A linha `NPK` soma N, P2O5 e K2O e fica vazia quando falta um dos três. Por isso a produção de NPK só aparece a partir de 1985, quando a FAOSTAT começa a registrar produção de K2O no Brasil.

**Comex Stat antes de 1997.** As importações de 1989 a 1996 vêm da nomenclatura NBM e foram agrupadas pelas quatro primeiras posições do código. Na própria API, 66 linhas do capítulo 31 vêm sem peso nesse período; elas somam menos de 0,01% do valor FOB, então o efeito nas toneladas é desprezível. A coluna `nomenclatura` separa os dois períodos.

**UF no Comex Stat.** É a "UF do produto": o destino declarado na importação, não a UF onde o adubo é aplicado.

**Censos de 2006 e 2017.** As perguntas mudaram, então há duas medidas de adoção harmonizadas:

| Medida | 2006 (SIDRA 864) | 2017 (SIDRA 6847) |
|---|---|---|
| `estab_adubou_no_ano` | "Usa" menos "Usa, não precisou usar em 2006" | "Fez adubação" |
| `estab_costuma_adubar` | "Usa" | "Fez adubação" mais "Não fez, costuma fazer" |

A despesa de 2006 separa adubos de corretivos; a de 2017 traz as duas rubricas juntas. A coluna `despesa_adubos_corretivos_mil_reais` é comparável nos dois anos (em reais correntes de cada um).

**Câmbio.** Antes de julho de 1994 a série do BCB está na moeda da época. Os preços em reais (`*_brl_t`) começam em julho de 1994.

**PAM.** O valor da produção só entra de 1994 em diante (em reais). Em 1974 a soma das UFs fica 0,16% abaixo do total do Brasil na própria fonte.

**Ano parcial.** 2026 vai até agosto na ANDA e até outubro no Comex Stat. As colunas `ano_parcial`, `anda_meses` e `comex_meses` marcam isso.
