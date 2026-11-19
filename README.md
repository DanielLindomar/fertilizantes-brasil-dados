# Repositório de dados – Fertilizantes (Universal CNPq 06/2026)

Bases abertas mapeadas no catálogo do projeto (`Mapeamento_dados_uso_fertilizantes.xlsx`, mantido fora deste repositório), baixadas com o script `scripts/baixar_bases.py`.

Site com gráficos e downloads: <https://daniellindomar.github.io/fertilizantes-brasil-dados/>

Primeira versão: **19/11/2026**.

## Estrutura

```
dados/
├── README.md            este arquivo
├── MANIFESTO.csv        uma linha por arquivo: catálogo, fonte, origem, data, tamanho, SHA-256, nº de linhas
├── scripts/
│   ├── baixar_bases.py            baixa tudo de novo numa pasta datada
│   ├── consolidar.py              gera as séries consolidadas e os dados do site
│   └── validar_consolidados.py    confere chaves únicas e somas que precisam fechar
├── brutos/<fonte>/<AAAA-MM-DD>/     como veio da fonte (APIs convertidas de JSON para CSV, sem alterar valores)
├── tratados/<fonte>/<AAAA-MM-DD>/   recortes derivados para uso direto (ex.: só Brasil)
├── consolidados/                    séries prontas para análise (ver consolidados/README.md)
└── docs/                            site do repositório (GitHub Pages)
```

Cada execução cria uma pasta nova com a data do dia; versões anteriores não são apagadas. Assim dá para citar e reproduzir a versão (vintage) usada em cada estimação, o que importa porque ANDA, FAOSTAT e Banco Mundial revisam séries.

## Séries consolidadas

A pasta `consolidados/` traz 17 arquivos prontos para análise, com dicionário de colunas (`DICIONARIO.csv`): séries anuais e mensais do Brasil, tabelas por UF e por município e três painéis integrados (Brasil anual, Brasil mensal e UF anual). As decisões de consolidação estão em `consolidados/README.md`.

Para refazer depois de baixar uma versão nova:

```bash
python scripts/consolidar.py
python scripts/validar_consolidados.py
```

O site em `docs/` mostra os principais gráficos e permite baixar cada arquivo.

## Conteúdo (versão 2026-11-19)

São 67 arquivos e cerca de 220 MB. Os IDs remetem ao Catálogo.

| Pasta | O que tem | Cobertura conferida | IDs |
|---|---|---|---|
| `brutos/faostat/` | Arquivos globais da FAOSTAT: RFN, RFB, RA, ESB, EMN e RFM (matriz de comércio) | RFN Brasil 1961–2024; ESB 1961–2023 | A01–A03, E01, E02, G03 |
| `tratados/faostat/` | Recortes do Brasil de cada arquivo (RFM: Brasil como declarante ou parceiro) | RFN 1.262 linhas; RFM 106.068 linhas | idem |
| `brutos/anda/` | Principais Indicadores 2016–2026 (PDF); Macro indicadores de ago/2026 (xlsx); Comentários (release do mês) | dados até ago/2026 | A04, A05, B05 |
| `tratados/anda/` | Tabelas mensais (entregas, produção, importação, exportação) extraídas de cada edição | 11 edições; totais anuais conferem com os PDFs | A04 |
| `brutos/ipeadata/` | Séries ANDA mensais e anuais e câmbio efetivo real GAC12 (inativo) | ANDA mensal 1998-01 a 2026-08; GAC12 até 2024-12 | A06, G05 |
| `brutos/ibge_sidra/` | IDS 768, 769, 770; Censo 2017 (6847, 6849, 6899, 6900); Censo 2006 (833, 1249, 864, 825); PAM 5457; PPM 3939 e 74; LSPA 6588; dicionário de códigos | IDS 2007–2014 por UF; PAM 1974–2025 (Brasil e UFs); Censos com cerca de 5.550 municípios | B01–B03, C01–C07, F01–F03 |
| `brutos/comex_stat/` | Importação do capítulo 31 e de matérias-primas, exportação do capítulo 31 (NCM × país × UF × mês); histórico NBM 1989–1996; tabelas NCM, NBM, países e UF | 1997-01 a 2026-10; NBM 1989–1996 | B06, G02 |
| `brutos/bcb_sgs/` | Câmbio real efetivo (11752), câmbio real bilateral (11753), dólar comercial (1, 3696, 3698) | 11752: 1988-01 a 2026-08; dólar diário até 18/11/2026 | G04 |
| `brutos/banco_mundial/` | Pink Sheet mensal e anual (xlsx) | 1960-01 a 2026-10 | G01 |
| `tratados/banco_mundial/` | Ureia, DAP, TSP, KCl, rocha fosfática, gás natural, soja e milho, mensal | 1960-01 a 2026-10 | G01 |
| `brutos/ibge_anuario/`, `infra_sa/`, `pnf_2050/`, `seeg/` | PDFs: AEB 4.1.2.10 e 4.1.2.11; Boletim ONTL (fev/2026); PNF 2050; nota metodológica do SEEG 13 | — | A08, B04, A09, E03 |

### Cuidados ao usar

- **Originais da ANDA fora do GitHub.** Os 13 arquivos de `brutos/anda/` (PDFs, planilha e release) constam do manifesto com SHA-256, mas não são publicados no repositório do GitHub por não trazerem licença aberta explícita. O script os baixa de novo, exceto os "Comentários" de meses passados, que o site da ANDA não mantém. As tabelas extraídas estão em `tratados/anda/`.

- **SIDRA, chave territorial.** Use `nivel_cod` + `local_cod`. Nas tabelas 769 e 770, o código 1 é o Brasil no nível 1 e a região Norte no nível 2.
- **Comex Stat, histórico NBM.** A API devolve a descrição da mercadoria sem o código NBM; para casar, use `comex_tabela_nbm_fertilizantes.csv`. Há 135 linhas com peso vazio na própria API.
- **ANDA, Comentários.** O release mensal traz as entregas acumuladas no ano pelas principais UFs. Exemplo de jan–ago/2026: MT 6,77 Mt (24,8%), PR 3,07, GO 2,90, SP 2,79, RS 2,24, MG 2,07 e BA 1,96 Mt. O site só mantém o mês corrente, então **rodar o script todo mês** vai acumulando essa série. O mesmo release avisa que parte da produção nacional de 2026 (ureia e KCl) não foi captada.
- **Versões que não batem.**
  - As entregas de 2021 somam 45.855.071 t nos PDFs da ANDA e 45.931.405 t no Ipeadata.
  - A exportação de 2025 é de 635.304 t na ANDA e 608.219 t no Ipeadata.
  - Para os meses recentes, prefira as tabelas extraídas dos PDFs (`tratados/anda/`).
- **Pink Sheet, mudanças de cotação.** O KCl passa a ser CFR Brasil em jan/2020. A ureia passa a ser FOB Oriente Médio em mar/2022.

## Convenções dos CSV

- UTF-8, separador vírgula, ponto decimal. No Excel em português, abra pelo menu Dados > De Texto/CSV e escolha vírgula como separador.
- **SIDRA:** colunas de código (`*_cod`) e `valor`. Os nomes de variáveis e categorias estão em `sidra_dicionario.csv`. Os símbolos especiais do IBGE ficam como texto: `-` (zero absoluto), `..` (não se aplica), `...` (dado não disponível), `X` (dado omitido por sigilo).
- **Comex Stat:** valores em US$ e kg, como a API devolve. `state` é a "UF do produto": na importação, a UF de destino declarada da mercadoria, não a UF onde o adubo é aplicado.
- **FAOSTAT:** arquivos `.zip` globais em `brutos/` (layout normalizado da FAO, codificação latin-1 dentro do zip). Os recortes do Brasil em `tratados/` estão em UTF-8.
- **ANDA:** valores em toneladas de produto, não de nutriente.

## Como atualizar

Requer Python 3.9 ou mais recente, com `pdfplumber` e `openpyxl` instalados. A consolidação usa também `pandas`.

```bash
python dados/scripts/baixar_bases.py
```

Para baixar só algumas fontes:

```bash
python dados/scripts/baixar_bases.py --fontes sidra,comex,bcb
```

As fontes disponíveis são `faostat`, `anda`, `ipeadata`, `sidra`, `comex`, `bcb`, `bancomundial` e `documentos`. O manifesto é atualizado a cada fonte concluída.

## O que não foi baixado

| Fonte | Motivo |
|---|---|
| Anuário Estatístico da ANDA (A07) | Pago ou restrito. É a fonte do painel estadual por nutriente: pedir à ANDA. |
| Microdados dos Censos Agropecuários (C08) | Acesso restrito, pela Sala de Acesso a Dados Restritos do IBGE |
| FUBC/IFA (D01) | O Dryad exige login; baixar manualmente o `Country_tables.xlsx` |
| Bases em grade de Coello et al. (2025) e Adalibieke et al. (2023) (D03, D04) | Arquivos globais grandes; baixar só se a equipe decidir usar |
| Custos de produção e preços de insumos da Conab (D05, G06) | Portal dinâmico, sem link direto para os arquivos |
| IMEA, CNA/Campo Futuro, IEA-SP, CEPEA (D06, D07, G07, G09) | Boletins e bancos de dados sem acesso automatizável conferido |
| Levantamento de safra da Conab (F04), MapBiomas (F05) | Não conferidos nesta etapa; o MapBiomas é muito grande |
| Relatório de referência do MCTI (E04) | O servidor `repositorio.mctic.gov.br` não respondeu em 19/11/2026 (erro de DNS); o script tenta de novo na próxima execução |
| PAM por município | Não incluída para não pesar a pasta. Para baixar, acrescente ao script uma entrada com `MUN` para a tabela 5457. |
