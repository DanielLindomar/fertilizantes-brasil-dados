/* Fertilizantes no Brasil - site do repositório de dados.
   Sem dependências: lê os CSV de docs/dados e desenha os gráficos em SVG. */
(function () {
  "use strict";

  const CFG = Object.assign({ repo: "", ramo: "main", semCopia: [] }, window.SITE_CONFIG || {});
  const NS = "http://www.w3.org/2000/svg";
  const $ = (sel, raiz) => (raiz || document).querySelector(sel);

  // ------------------------------------------------------------ utilidades
  function h(tag, attrs, ...filhos) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of filhos.flat(Infinity)) if (c != null) e.append(c); // texto entra como nó de texto
    return e;
  }
  function s(tag, attrs, ...filhos) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs || {}) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    for (const c of filhos.flat(Infinity)) if (c != null) e.append(c);
    return e;
  }
  const NF = [0, 1, 2].map((d) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const f = (v, d) => (Number.isFinite(v) ? NF[d || 0].format(v) : "–");
  const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const rotMes = (data) => MES[+data.slice(5, 7) - 1] + "/" + data.slice(0, 4);
  const dataBR = (iso) => iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4);
  const NUTR = { N: "N", P2O5: "P₂O₅", K2O: "K₂O", NPK: "NPK" };
  const num = (v) => (v === "" || v == null ? NaN : +v);
  const sinal = (v, d) => (v > 0 ? "+" : v < 0 ? "−" : "") + f(Math.abs(v), d);

  function parseCSV(texto) {
    const linhas = [];
    let linha = [], cur = "", aspas = false;
    for (let i = 0; i < texto.length; i++) {
      const c = texto[i];
      if (aspas) {
        if (c === '"') { if (texto[i + 1] === '"') { cur += '"'; i++; } else aspas = false; }
        else cur += c;
      } else if (c === '"') aspas = true;
      else if (c === ",") { linha.push(cur); cur = ""; }
      else if (c === "\n") { linha.push(cur); linhas.push(linha); linha = []; cur = ""; }
      else if (c !== "\r") cur += c;
    }
    if (cur !== "" || linha.length) { linha.push(cur); linhas.push(linha); }
    const cab = linhas.shift();
    return linhas.filter((r) => r.length === cab.length).map((r) => Object.fromEntries(cab.map((k, i) => [k, r[i]])));
  }
  const cache = {};
  function csv(nome) {
    if (!cache[nome]) {
      cache[nome] = fetch("dados/" + nome).then((r) => {
        if (!r.ok) throw new Error(nome + ": HTTP " + r.status);
        return r.text();
      }).then(parseCSV);
    }
    return cache[nome];
  }

  function tiques(max, n) {
    if (!(max > 0)) return [0, 1];
    const bruto = max / (n || 5);
    const p = Math.pow(10, Math.floor(Math.log10(bruto)));
    const m = bruto / p;
    const passo = (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
    const topo = Math.ceil(max / passo - 1e-9) * passo;
    const out = [];
    for (let v = 0; v <= topo + passo / 2; v += passo) out.push(+v.toFixed(10));
    return out;
  }

  // ------------------------------------------------------------ dica (tooltip)
  const dica = h("div", { class: "dica", role: "status", hidden: true });
  document.body.append(dica);
  function mostrarDica(conteudo, x, y) {
    dica.replaceChildren(conteudo);
    dica.hidden = false;
    const r = dica.getBoundingClientRect();
    let esq = x + 14, topo = y + 14;
    if (esq + r.width > innerWidth - 8) esq = x - r.width - 14;
    if (esq < 8) esq = 8;
    if (topo + r.height > innerHeight - 8) topo = y - r.height - 14;
    if (topo < 8) topo = 8;
    dica.style.left = esq + "px";
    dica.style.top = topo + "px";
  }
  function esconderDica() { dica.hidden = true; }
  function caixaDica(titulo, linhas, rodape) {
    const d = document.createDocumentFragment();
    if (titulo) d.append(h("div", { class: "dica-t" }, titulo));
    for (const l of linhas) {
      d.append(h("div", { class: "dica-l" },
        l.cor ? h("span", { class: "chave " + (l.forma || ""), style: "background:" + l.cor }) : null,
        h("strong", null, l.valor), h("span", null, l.nome)));
    }
    if (rodape) d.append(h("div", { class: "dica-r" }, rodape));
    return d;
  }
  addEventListener("scroll", esconderDica, { passive: true });

  // ------------------------------------------------------------ peças comuns
  function legenda(fig, itens) {
    const leg = $(".legenda", fig);
    if (!leg) return;
    leg.replaceChildren(...itens.map((it) => h("span", null, h("span", { class: "chave " + (it.forma || ""), style: "background:" + it.cor }), it.nome)));
  }
  function tabelaAlternavel(fig, colunas, linhas) {
    const plot = $(".plot", fig), leg = $(".legenda", fig), btn = $(".alternar", fig);
    const cont = h("div", { class: "rolagem", hidden: true, tabindex: "0", role: "region", "aria-label": "Tabela de dados do gráfico" },
      h("table", null,
        h("thead", null, h("tr", null, colunas.map((c) => h("th", { class: c.n ? "n" : null, scope: "col" }, c.t)))),
        h("tbody", null, linhas.map((r) => h("tr", null, r.map((v, i) => h("td", { class: colunas[i].n ? "n" : "fixo" }, v)))))));
    plot.after(cont);
    btn.setAttribute("aria-pressed", "false");
    btn.addEventListener("click", () => {
      const ver = cont.hidden;
      cont.hidden = !ver;
      plot.hidden = ver;
      if (leg) leg.hidden = ver;
      btn.textContent = ver ? "Ver gráfico" : "Ver tabela";
      btn.setAttribute("aria-pressed", String(ver));
    });
  }
  function responsivo(caixa, desenhar) {
    let larg = 0, raf = 0;
    new ResizeObserver(() => {
      const w = caixa.clientWidth;
      if (!w || w === larg) return;
      larg = w;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(desenhar);
    }).observe(caixa);
  }
  function falha(seletores, erro) {
    console.error(erro);
    const local = location.protocol === "file:";
    for (const sel of seletores.split(",")) {
      const fig = $(sel.trim());
      if (!fig) continue;
      ($(".plot", fig) || fig).replaceChildren(h("p", { class: "erro" }, local
        ? "Os dados não carregam quando a página é aberta direto do disco. Sirva a pasta com \"python -m http.server\" e abra pelo endereço local."
        : "Não foi possível carregar estes dados."));
    }
  }
  // navegação por setas num gráfico com n posições; devolve a função que zera o estado
  function teclado(alvo, n, eixo, mostrar, esconder) {
    let i = null;
    const menos = eixo === "x" ? "ArrowLeft" : "ArrowUp", mais = eixo === "x" ? "ArrowRight" : "ArrowDown";
    alvo.addEventListener("keydown", (ev) => {
      let j = i == null ? (eixo === "x" ? n - 1 : 0) : i;
      if (ev.key === menos) j = i == null ? j : Math.max(0, i - 1);
      else if (ev.key === mais) j = i == null ? j : Math.min(n - 1, i + 1);
      else if (ev.key === "Home") j = 0;
      else if (ev.key === "End") j = n - 1;
      else if (ev.key === "Escape") { i = null; esconder(); return; }
      else return;
      ev.preventDefault();
      i = j;
      mostrar(i);
    });
    alvo.addEventListener("focus", () => { if (alvo.matches(":focus-visible")) { i = eixo === "x" ? n - 1 : 0; mostrar(i); } });
    alvo.addEventListener("blur", () => { i = null; esconder(); });
    return (v) => { i = v; };
  }

  // ------------------------------------------------------------ gráfico de linhas
  // cfg: { x: [rótulo de cada posição], series: [{nome, curto, cor, v: []}], fmt, fmtFim, unidade, tiqueX(i, estreito), yMax, margemRotulo, aria }
  function graficoLinhas(fig, cfg) {
    const plot = $(".plot", fig);
    const n = cfg.x.length;
    legenda(fig, cfg.series.map((se) => ({ nome: se.nome, cor: se.cor })));

    function desenhar() {
      const W = plot.clientWidth;
      if (!W) return;
      const estreito = W < 480;
      const H = estreito ? 250 : 310;
      const rot = !estreito;
      const m = { t: 12, r: rot ? cfg.margemRotulo || 84 : 12, b: 26, l: 38 };
      const pw = W - m.l - m.r, ph = H - m.t - m.b;
      let max = cfg.yMax || 0;
      if (!cfg.yMax) for (const se of cfg.series) for (const v of se.v) if (v > max) max = v;
      const tq = tiques(max, 5), topo = tq[tq.length - 1];
      const X = (i) => m.l + (n === 1 ? pw / 2 : (i / (n - 1)) * pw);
      const Y = (v) => m.t + (1 - v / topo) * ph;
      const svg = s("svg", { viewBox: "0 0 " + W + " " + H, height: H, role: "img", tabindex: "0", "aria-label": cfg.aria + " Use as setas para percorrer os valores." });

      for (const t of tq) {
        svg.append(s("line", { class: t === 0 ? "eixo-l" : "grade-l", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
        svg.append(s("text", { x: m.l - 6, y: Y(t) + 4, "text-anchor": "end" }, f(t, topo < 5 ? 1 : 0)));
      }
      for (let i = 0; i < n; i++) {
        const r = cfg.tiqueX(i, estreito);
        if (r == null) continue;
        svg.append(s("line", { class: "eixo-l", x1: X(i), x2: X(i), y1: Y(0), y2: Y(0) + 4 }));
        svg.append(s("text", { x: X(i), y: H - 6, "text-anchor": "middle" }, r));
      }
      const mira = s("line", { class: "mira", y1: m.t, y2: Y(0), visibility: "hidden" });
      svg.append(mira);

      const fins = [];
      for (const se of cfg.series) {
        let d = "", pena = false, ult = -1;
        se.v.forEach((v, i) => {
          if (!Number.isFinite(v)) { pena = false; return; }
          d += (pena ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1);
          pena = true;
          ult = i;
        });
        svg.append(s("path", { class: "linha", d: d, style: "stroke:" + se.cor }));
        if (ult >= 0) fins.push({ se: se, i: ult, x: X(ult), y: Y(se.v[ult]) });
      }
      if (rot) { // rótulos diretos no fim de cada linha, afastados com guia quando colidem
        const o = fins.slice().sort((a, b) => a.y - b.y);
        let ant = -Infinity;
        for (const e of o) { e.ly = Math.max(e.y, ant + 16); ant = e.ly; }
        let lim = H - m.b;
        for (let k = o.length - 1; k >= 0; k--) { if (o[k].ly > lim) o[k].ly = lim; lim = o[k].ly - 16; }
        for (const e of o) {
          const desviado = Math.abs(e.ly - e.y) > 3;
          if (desviado) svg.append(s("line", { class: "guia", x1: e.x + 6, y1: e.y, x2: e.x + 13, y2: e.ly }));
          svg.append(s("text", { class: "rotulo", x: e.x + (desviado ? 16 : 10), y: e.ly + 4 },
            (e.se.curto || e.se.nome) + " ", s("tspan", { class: "forte" }, (cfg.fmtFim || cfg.fmt)(e.se.v[e.i]))));
        }
      }
      for (const e of fins) svg.append(s("circle", { class: "ponto", cx: e.x, cy: e.y, r: 4, style: "fill:" + e.se.cor }));
      const marc = cfg.series.map((se) => s("circle", { class: "ponto", r: 4.5, style: "fill:" + se.cor, visibility: "hidden" }));
      svg.append(...marc);

      function mostrar(i, cx, cy) {
        mira.setAttribute("x1", X(i));
        mira.setAttribute("x2", X(i));
        mira.setAttribute("visibility", "visible");
        cfg.series.forEach((se, k) => {
          const v = se.v[i];
          marc[k].setAttribute("visibility", Number.isFinite(v) ? "visible" : "hidden");
          if (Number.isFinite(v)) { marc[k].setAttribute("cx", X(i)); marc[k].setAttribute("cy", Y(v)); }
        });
        if (cx == null) { const r = svg.getBoundingClientRect(); cx = r.left + X(i); cy = r.top + m.t + 8; }
        mostrarDica(caixaDica(cfg.x[i], cfg.series.map((se) => ({
          cor: se.cor, nome: se.nome,
          valor: Number.isFinite(se.v[i]) ? cfg.fmt(se.v[i]) + (cfg.unidade ? " " + cfg.unidade : "") : "sem dado",
        }))), cx, cy);
      }
      function esconder() {
        mira.setAttribute("visibility", "hidden");
        marc.forEach((c) => c.setAttribute("visibility", "hidden"));
        esconderDica();
      }
      const fixar = teclado(svg, n, "x", (i) => mostrar(i), esconder);
      const mover = (ev) => {
        const r = svg.getBoundingClientRect();
        const i = Math.max(0, Math.min(n - 1, Math.round(((ev.clientX - r.left - m.l) / pw) * (n - 1))));
        fixar(i);
        mostrar(i, ev.clientX, ev.clientY);
      };
      svg.addEventListener("pointermove", mover);
      svg.addEventListener("pointerdown", mover);
      svg.addEventListener("pointerleave", esconder);
      plot.replaceChildren(svg);
    }
    responsivo(plot, desenhar);
    desenhar();
  }

  // ------------------------------------------------------------ colunas empilhadas
  // cfg: { x: [rótulos], series: [{nome, cor, v: []}], fmt, unidade, tiqueX(i, estreito), aria }
  function graficoPilhas(fig, cfg) {
    const plot = $(".plot", fig);
    const n = cfg.x.length;
    const totais = cfg.x.map((_, i) => cfg.series.reduce((a, se) => a + (se.v[i] || 0), 0));
    legenda(fig, cfg.series.map((se) => ({ nome: se.nome, cor: se.cor, forma: "caixa" })));

    function desenhar() {
      const W = plot.clientWidth;
      if (!W) return;
      const estreito = W < 480;
      const H = estreito ? 260 : 340;
      const m = { t: 22, r: 14, b: 26, l: 38 };
      const pw = W - m.l - m.r, ph = H - m.t - m.b;
      const tq = tiques(Math.max(...totais), 5), topo = tq[tq.length - 1];
      const faixa = pw / n, lw = Math.max(2, Math.min(24, faixa * 0.7));
      const Y = (v) => m.t + (1 - v / topo) * ph;
      const svg = s("svg", { viewBox: "0 0 " + W + " " + H, height: H, role: "img", tabindex: "0", "aria-label": cfg.aria + " Use as setas para percorrer os anos." });
      for (const t of tq) {
        svg.append(s("line", { class: t === 0 ? "eixo-l" : "grade-l", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
        svg.append(s("text", { x: m.l - 6, y: Y(t) + 4, "text-anchor": "end" }, f(t)));
      }
      const colunas = [];
      for (let i = 0; i < n; i++) {
        const x0 = m.l + i * faixa + (faixa - lw) / 2;
        const g = s("g", { class: "coluna" });
        let acc = 0, ultimo = -1;
        cfg.series.forEach((se, k) => { if (se.v[i] > 0) ultimo = k; });
        cfg.series.forEach((se, k) => {
          const v = se.v[i] || 0;
          if (v <= 0) return;
          const yb = Y(acc), yt = Y(acc + v);
          acc += v;
          const alt = yb - yt;
          if (k === ultimo) { // ponta de dados arredondada; base reta
            const r = Math.min(4, lw / 2, alt);
            g.append(s("path", { style: "fill:" + se.cor, d: "M" + x0 + " " + yb + "V" + (yt + r) + "Q" + x0 + " " + yt + " " + (x0 + r) + " " + yt + "H" + (x0 + lw - r) + "Q" + (x0 + lw) + " " + yt + " " + (x0 + lw) + " " + (yt + r) + "V" + yb + "Z" }));
          } else { // 2 px da cor da superfície separam os segmentos
            const folga = alt > 3 ? 2 : alt / 2;
            g.append(s("rect", { style: "fill:" + se.cor, x: x0, y: yt + folga, width: lw, height: Math.max(0.5, alt - folga) }));
          }
        });
        svg.append(g);
        colunas.push(g);
        const r = cfg.tiqueX(i, estreito);
        if (r != null) svg.append(s("text", { x: x0 + lw / 2, y: H - 6, "text-anchor": "middle" }, r));
      }
      // rótulo direto só no total da última coluna
      const xu = m.l + (n - 1) * faixa + faixa / 2;
      svg.append(s("text", { class: "forte", x: Math.min(xu, W - 16), y: Y(totais[n - 1]) - 6, "text-anchor": "middle" }, cfg.fmt(totais[n - 1])));

      function mostrar(i, cx, cy) {
        colunas.forEach((g, k) => g.classList.toggle("apagada", k !== i));
        if (cx == null) { const r = svg.getBoundingClientRect(); cx = r.left + m.l + (i + 0.5) * faixa; cy = r.top + Y(totais[i]); }
        const linhas = cfg.series.map((se) => ({
          cor: se.cor, forma: "caixa", nome: se.nome + " (" + f((se.v[i] / totais[i]) * 100) + "%)",
          valor: cfg.fmt(se.v[i] || 0),
        })).reverse();
        mostrarDica(caixaDica(cfg.x[i], linhas, "Total: " + cfg.fmt(totais[i]) + " " + cfg.unidade), cx, cy);
      }
      function esconder() {
        colunas.forEach((g) => g.classList.remove("apagada"));
        esconderDica();
      }
      const fixar = teclado(svg, n, "x", (i) => mostrar(i), esconder);
      const mover = (ev) => {
        const r = svg.getBoundingClientRect();
        const i = Math.max(0, Math.min(n - 1, Math.floor((ev.clientX - r.left - m.l) / faixa)));
        fixar(i);
        mostrar(i, ev.clientX, ev.clientY);
      };
      svg.addEventListener("pointermove", mover);
      svg.addEventListener("pointerdown", mover);
      svg.addEventListener("pointerleave", esconder);
      plot.replaceChildren(svg);
    }
    responsivo(plot, desenhar);
    desenhar();
  }

  // ------------------------------------------------------------ barras ordenadas (HTML)
  // cfg: { linhas: [{nome, curto, v, dica: [{valor, nome}]}], fmt, aria }
  function barrasOrdenadas(fig, cfg) {
    const plot = $(".plot", fig);
    const max = Math.max(...cfg.linhas.map((r) => r.v));
    const lista = h("div", { class: "barras", role: "list", tabindex: "0", "aria-label": cfg.aria + " Use as setas para percorrer as linhas." });
    const linhas = cfg.linhas.map((r) => h("div", { class: "barra-linha", role: "listitem" },
      h("span", { class: "barra-nome" }, h("span", { class: "so-largo" }, r.nome), h("span", { class: "so-estreito" }, r.curto)),
      h("span", { class: "barra-area" },
        h("span", { class: "barra", style: "width:calc((100% - 4.2em) * " + (r.v / max).toFixed(4) + ")" }),
        h("span", { class: "barra-valor" }, cfg.fmt(r.v)))));
    function mostrar(i, cx, cy) {
      linhas.forEach((el, k) => el.classList.toggle("ativa", k === i));
      if (cx == null) { const r = linhas[i].getBoundingClientRect(); cx = r.left + r.width / 2; cy = r.bottom - 8; }
      mostrarDica(caixaDica(cfg.linhas[i].nome, cfg.linhas[i].dica), cx, cy);
    }
    function esconder() {
      linhas.forEach((el) => el.classList.remove("ativa"));
      esconderDica();
    }
    const fixar = teclado(lista, linhas.length, "y", (i) => mostrar(i), esconder);
    linhas.forEach((el, i) => {
      el.addEventListener("pointermove", (ev) => { fixar(i); mostrar(i, ev.clientX, ev.clientY); });
      el.addEventListener("pointerleave", esconder);
    });
    lista.append(...linhas);
    plot.replaceChildren(lista);
  }

  // ------------------------------------------------------------ halteres (antes e depois por linha)
  // cfg: { linhas: [{nome, curto, a, b, forte}], rotA, rotB, aria }
  function graficoHalteres(fig, cfg) {
    const plot = $(".plot", fig);
    const n = cfg.linhas.length;
    const corA = "var(--ord-antes)", corB = "var(--ord-depois)";
    legenda(fig, [{ nome: cfg.rotA, cor: corA, forma: "ponto" }, { nome: cfg.rotB, cor: corB, forma: "ponto" }]);

    function desenhar() {
      const W = plot.clientWidth;
      if (!W) return;
      const estreito = W < 480;
      const lh = 22, m = { t: 24, r: 18, b: 4, l: estreito ? 36 : 138 };
      const H = m.t + lh * n + m.b, pw = W - m.l - m.r;
      const tq = tiques(Math.max(...cfg.linhas.map((r) => Math.max(r.a, r.b))), 5), topo = tq[tq.length - 1];
      const X = (v) => m.l + (v / topo) * pw;
      const svg = s("svg", { viewBox: "0 0 " + W + " " + H, height: H, role: "img", tabindex: "0", "aria-label": cfg.aria + " Use as setas para percorrer as linhas." });
      const faixa = s("rect", { class: "faixa-ativa", x: 0, width: W, height: lh, rx: 4, visibility: "hidden" });
      svg.append(faixa);
      for (const t of tq) {
        svg.append(s("line", { class: t === 0 ? "eixo-l" : "grade-l", x1: X(t), x2: X(t), y1: m.t, y2: H - m.b }));
        svg.append(s("text", { x: X(t), y: 13, "text-anchor": "middle" }, f(t) + "%"));
      }
      cfg.linhas.forEach((r, i) => {
        const y = m.t + i * lh + lh / 2;
        svg.append(s("text", { class: r.forte ? "forte" : "rotulo", x: m.l - 10, y: y + 4, "text-anchor": "end" }, estreito ? r.curto : r.nome));
        svg.append(s("line", { x1: X(r.a), x2: X(r.b), y1: y, y2: y, style: "stroke:" + corA + ";stroke-width:2" }));
        svg.append(s("circle", { class: "ponto", cx: X(r.a), cy: y, r: 5, style: "fill:" + corA }));
        svg.append(s("circle", { class: "ponto", cx: X(r.b), cy: y, r: 5, style: "fill:" + corB }));
      });
      function mostrar(i, cx, cy) {
        const r = cfg.linhas[i];
        faixa.setAttribute("y", m.t + i * lh);
        faixa.setAttribute("visibility", "visible");
        if (cx == null) { const b = svg.getBoundingClientRect(); cx = b.left + X(Math.max(r.a, r.b)); cy = b.top + m.t + i * lh + lh; }
        mostrarDica(caixaDica(r.nome, [
          { cor: corA, forma: "ponto", valor: f(r.a, 1) + "%", nome: cfg.rotA },
          { cor: corB, forma: "ponto", valor: f(r.b, 1) + "%", nome: cfg.rotB },
        ], "Variação: " + sinal(r.b - r.a, 1) + " p.p."), cx, cy);
      }
      function esconder() {
        faixa.setAttribute("visibility", "hidden");
        esconderDica();
      }
      const fixar = teclado(svg, n, "y", (i) => mostrar(i), esconder);
      const mover = (ev) => {
        const b = svg.getBoundingClientRect();
        const i = Math.floor((ev.clientY - b.top - m.t) / lh);
        if (i < 0 || i >= n) { esconder(); return; }
        fixar(i);
        mostrar(i, ev.clientX, ev.clientY);
      };
      svg.addEventListener("pointermove", mover);
      svg.addEventListener("pointerdown", mover);
      svg.addEventListener("pointerleave", esconder);
      plot.replaceChildren(svg);
    }
    responsivo(plot, desenhar);
    desenhar();
  }

  // ------------------------------------------------------------ indicador com minigráfico
  function indicador(cont, cfg) { // cfg: { rotulo, valor, unidade, delta, serie: [] }
    const mini = h("div", { class: "mini", "aria-hidden": "true" });
    const tile = h("div", { class: "cartao tile" },
      h("span", { class: "tile-rotulo" }, cfg.rotulo),
      h("span", { class: "tile-valor" }, cfg.valor, cfg.unidade ? h("small", null, cfg.unidade) : null),
      cfg.delta ? h("span", { class: "tile-delta" }, h("b", null, cfg.delta.valor), " " + cfg.delta.texto) : null,
      mini);
    cont.append(tile);
    const v = cfg.serie.filter(Number.isFinite);
    if (v.length < 2) return;
    function desenhar() {
      const W = mini.clientWidth, H = 34;
      if (!W) return;
      const lo = Math.min(...v), hi = Math.max(...v), amp = hi - lo || 1;
      const X = (i) => 5 + (i / (v.length - 1)) * (W - 10), Y = (x) => 5 + (1 - (x - lo) / amp) * (H - 10);
      const svg = s("svg", { viewBox: "0 0 " + W + " " + H, height: H });
      svg.append(s("path", { d: v.map((x, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(x).toFixed(1)).join(""), style: "fill:none;stroke:var(--eixo);stroke-width:2;stroke-linejoin:round;stroke-linecap:round" }));
      svg.append(s("circle", { cx: X(v.length - 1), cy: Y(v[v.length - 1]), r: 4, style: "fill:var(--serie-1);stroke:var(--superficie);stroke-width:2" }));
      mini.replaceChildren(svg);
    }
    responsivo(mini, desenhar);
    desenhar();
  }

  // ============================================================ conteúdo
  const tiqueAno = (anos) => (i, estreito) => (anos[i] % (estreito ? 20 : 10) === 0 ? String(anos[i]) : null);
  const tiqueJaneiro = (datas, largo, curto) => (i, estreito) => {
    const d = datas[i];
    return d.slice(5, 7) === "01" && +d.slice(0, 4) % (estreito ? curto : largo) === 0 ? d.slice(0, 4) : null;
  };

  async function destaque() {
    const nut = await csv("br_anual_nutrientes_faostat.csv");
    const ano = Math.max(...nut.map((r) => +r.ano));
    const de = (k) => nut.find((r) => +r.ano === ano && r.nutriente === k);
    const npk = de("NPK");
    $("#heroi-rotulo").textContent = "Importação de NPK como proporção do uso agrícola em " + ano;
    $("#heroi-valor").textContent = f(num(npk.dependencia_importacao_pct)) + "%";
    $("#heroi-nota").textContent = f(num(npk.importacao_t) / 1e6, 1) + " milhões de t importadas para " + f(num(npk.uso_agricola_t) / 1e6, 1)
      + " milhões de t usadas na agricultura, em nutriente (N + P₂O₅ + K₂O). Fonte: FAOSTAT.";
    $("#medidores").replaceChildren(...["N", "P2O5", "K2O"].map((k) => {
      const p = num(de(k).dependencia_importacao_pct);
      return h("div", { class: "medidor", role: "listitem" },
        h("span", null, NUTR[k]),
        h("span", { class: "medidor-trilha" }, h("span", { class: "medidor-barra", style: "width:" + Math.min(100, p).toFixed(1) + "%" })),
        h("span", { class: "medidor-valor" }, f(p) + "%"));
    }));
  }

  async function indicadores() {
    const cont = $("#tiles");
    const [anual, precos] = await Promise.all([csv("painel_br_anual.csv"), csv("br_mensal_precos_cambio.csv")]);
    const variacao = (a, b) => ({ valor: (a >= b ? "▲ " : "▼ ") + f(Math.abs(a / b - 1) * 100, 1) + "%", texto: "" });
    const cheios = (colMeses) => anual.filter((r) => num(r[colMeses]) === 12);
    const a = cheios("anda_meses"), c = cheios("comex_meses");
    const ua = a[a.length - 1], pa = a[a.length - 2], uc = c[c.length - 1], pc = c[c.length - 2];
    let d = variacao(num(ua.anda_entregas_t), num(pa.anda_entregas_t));
    d.texto = "sobre " + pa.ano;
    indicador(cont, { rotulo: "Entregas ao mercado em " + ua.ano + " (ANDA)", valor: f(num(ua.anda_entregas_t) / 1e6, 1), unidade: "milhões de t", delta: d,
      serie: a.slice(-12).map((r) => num(r.anda_entregas_t)) });
    d = variacao(num(uc.comex_importacao_t), num(pc.comex_importacao_t));
    d.texto = "sobre " + pc.ano;
    indicador(cont, { rotulo: "Importação em " + uc.ano + " (Comex Stat)", valor: f(num(uc.comex_importacao_t) / 1e6, 1), unidade: "milhões de t", delta: d,
      serie: c.slice(-12).map((r) => num(r.comex_importacao_t)) });
    d = variacao(num(uc.comex_importacao_fob_usd), num(pc.comex_importacao_fob_usd));
    d.texto = "sobre " + pc.ano;
    indicador(cont, { rotulo: "Gasto com importação em " + uc.ano + " (FOB)", valor: "US$ " + f(num(uc.comex_importacao_fob_usd) / 1e9, 1), unidade: "bilhões", delta: d,
      serie: c.slice(-12).map((r) => num(r.comex_importacao_fob_usd)) });
    const p = precos.filter((r) => r.ureia_usd_t !== "");
    const up = p[p.length - 1], ap = p[p.length - 13];
    d = variacao(num(up.ureia_usd_t), num(ap.ureia_usd_t));
    d.texto = "em 12 meses";
    indicador(cont, { rotulo: "Preço internacional da ureia em " + rotMes(up.data), valor: "US$ " + f(num(up.ureia_usd_t)), unidade: "por t", delta: d,
      serie: p.slice(-13).map((r) => num(r.ureia_usd_t)) });
  }

  async function usoEDependencia() {
    const nut = await csv("br_anual_nutrientes_faostat.csv");
    const anos = [...new Set(nut.map((r) => +r.ano))].sort((a, b) => a - b);
    const cores = { N: "var(--serie-1)", P2O5: "var(--serie-2)", K2O: "var(--serie-3)" };
    const serie = (k, col, div) => anos.map((a) => { const r = nut.find((x) => +x.ano === a && x.nutriente === k); return r ? num(r[col]) / div : NaN; });
    const ks = ["N", "P2O5", "K2O"];
    const uso = ks.map((k) => ({ nome: NUTR[k], cor: cores[k], v: serie(k, "uso_agricola_t", 1e6) }));
    const dep = ks.map((k) => ({ nome: NUTR[k], cor: cores[k], v: serie(k, "dependencia_importacao_pct", 1) }));
    graficoLinhas($("#g-uso"), { x: anos.map(String), series: uso, fmt: (v) => f(v, 2), fmtFim: (v) => f(v, 1), unidade: "milhões de t",
      tiqueX: tiqueAno(anos), margemRotulo: 70, aria: "Gráfico de linhas: uso agrícola de N, P2O5 e K2O no Brasil, " + anos[0] + " a " + anos[anos.length - 1] + "." });
    tabelaAlternavel($("#g-uso"), [{ t: "Ano" }, { t: "N (mil t)", n: 1 }, { t: "P₂O₅ (mil t)", n: 1 }, { t: "K₂O (mil t)", n: 1 }],
      anos.map((a, i) => [String(a)].concat(uso.map((se) => f(se.v[i] * 1000)))).reverse());
    graficoLinhas($("#g-dep"), { x: anos.map(String), series: dep, fmt: (v) => f(v, 1) + "%", fmtFim: (v) => f(v) + "%",
      tiqueX: tiqueAno(anos), margemRotulo: 76, aria: "Gráfico de linhas: importação dividida pelo uso agrícola de N, P2O5 e K2O, " + anos[0] + " a " + anos[anos.length - 1] + "." });
    tabelaAlternavel($("#g-dep"), [{ t: "Ano" }, { t: "N (%)", n: 1 }, { t: "P₂O₅ (%)", n: 1 }, { t: "K₂O (%)", n: 1 }],
      anos.map((a, i) => [String(a)].concat(dep.map((se) => f(se.v[i], 1)))).reverse());
  }

  async function mercado() {
    const anda = await csv("br_mensal_anda.csv");
    const movel = (col) => anda.map((_, i) => {
      if (i < 11) return NaN;
      let soma = 0;
      for (let k = i - 11; k <= i; k++) { const v = num(anda[k][col]); if (!Number.isFinite(v)) return NaN; soma += v; }
      return soma / 1e6;
    }).slice(11);
    const datas = anda.slice(11).map((r) => r.data);
    const series = [
      { nome: "Entregas ao mercado", curto: "Entregas", cor: "var(--serie-1)", v: movel("entregas_t") },
      { nome: "Importação", cor: "var(--serie-2)", v: movel("importacao_t") },
      { nome: "Produção nacional", curto: "Produção", cor: "var(--serie-3)", v: movel("producao_t") },
    ];
    graficoLinhas($("#g-anda"), { x: datas.map((d) => "12 meses até " + rotMes(d)), series: series, fmt: (v) => f(v, 1), unidade: "milhões de t",
      tiqueX: tiqueJaneiro(datas, 5, 10), margemRotulo: 104,
      aria: "Gráfico de linhas: entregas, importação e produção nacional de fertilizantes em 12 meses, " + rotMes(datas[0]) + " a " + rotMes(datas[datas.length - 1]) + "." });
    tabelaAlternavel($("#g-anda"), [{ t: "12 meses até" }, { t: "Entregas (mil t)", n: 1 }, { t: "Importação (mil t)", n: 1 }, { t: "Produção (mil t)", n: 1 }],
      datas.map((d, i) => [rotMes(d)].concat(series.map((se) => f(se.v[i] * 1000)))).reverse());
  }

  async function precos() {
    const p = (await csv("br_mensal_precos_cambio.csv")).filter((r) => r.data >= "2000-01-01" && r.ureia_usd_t !== "");
    const datas = p.map((r) => r.data);
    const series = [
      { nome: "Ureia", cor: "var(--serie-1)", v: p.map((r) => num(r.ureia_usd_t)) },
      { nome: "Fosfato diamônico (DAP)", curto: "DAP", cor: "var(--serie-2)", v: p.map((r) => num(r.dap_usd_t)) },
      { nome: "Cloreto de potássio (KCl)", curto: "KCl", cor: "var(--serie-3)", v: p.map((r) => num(r.kcl_usd_t)) },
    ];
    graficoLinhas($("#g-precos"), { x: datas.map(rotMes), series: series, fmt: (v) => "US$ " + f(v), unidade: "por t", fmtFim: (v) => f(v),
      tiqueX: tiqueJaneiro(datas, 5, 10), margemRotulo: 74,
      aria: "Gráfico de linhas: preços internacionais de ureia, DAP e cloreto de potássio, " + rotMes(datas[0]) + " a " + rotMes(datas[datas.length - 1]) + "." });
    tabelaAlternavel($("#g-precos"), [{ t: "Mês" }, { t: "Ureia (US$/t)", n: 1 }, { t: "DAP (US$/t)", n: 1 }, { t: "KCl (US$/t)", n: 1 }],
      datas.map((d, i) => [rotMes(d)].concat(series.map((se) => f(se.v[i], 1)))).reverse());
  }

  async function origem() {
    const o = (await csv("br_anual_importacao_origem.csv")).filter((r) => r.grupo_sh4 === "31" && r.nomenclatura === "NCM" && r.ano_parcial === "0");
    const anos = [...new Set(o.map((r) => +r.ano))].sort((a, b) => a - b);
    const paises = ["Rússia", "China", "Canadá", "Marrocos", "Estados Unidos"];
    const cores = ["var(--serie-1)", "var(--serie-2)", "var(--serie-3)", "var(--serie-4)", "var(--serie-5)"];
    const idx = Object.fromEntries(anos.map((a, i) => [a, i]));
    const series = paises.map((nome, k) => ({ nome: nome, cor: cores[k], v: anos.map(() => 0) }));
    const outros = { nome: "Outros países", cor: "var(--outros)", v: anos.map(() => 0) };
    for (const r of o) {
      const k = paises.indexOf(r.pais);
      (k >= 0 ? series[k] : outros).v[idx[+r.ano]] += num(r.importacao_t) / 1e6;
    }
    series.push(outros);
    graficoPilhas($("#g-origem"), { x: anos.map(String), series: series, fmt: (v) => f(v, 1), unidade: "milhões de t",
      tiqueX: (i, estreito) => (anos[i] % (estreito ? 10 : 5) === 0 ? String(anos[i]) : null),
      aria: "Gráfico de colunas empilhadas: importação de fertilizantes por país de origem, " + anos[0] + " a " + anos[anos.length - 1] + "." });
    tabelaAlternavel($("#g-origem"), [{ t: "Ano" }].concat(series.map((se) => ({ t: se.nome + " (mil t)", n: 1 })), [{ t: "Total (mil t)", n: 1 }]),
      anos.map((a, i) => [String(a)].concat(series.map((se) => f(se.v[i] * 1000)), [f(series.reduce((t, se) => t + se.v[i], 0) * 1000)])).reverse());
  }

  async function porUF() {
    const u = (await csv("uf_anual_importacao_comex.csv")).filter((r) => r.grupo_sh4 === "31" && r.ano_parcial === "0");
    const ano = Math.max(...u.map((r) => +r.ano));
    const linhas = u.filter((r) => +r.ano === ano).map((r) => ({ nome: r.uf_nome, curto: r.uf, v: num(r.importacao_t) / 1e6, fob: num(r.importacao_fob_usd) }))
      .sort((a, b) => b.v - a.v);
    const total = linhas.reduce((t, r) => t + r.v, 0);
    for (const r of linhas) {
      r.dica = [{ valor: f(r.v, 2) + " milhões de t", nome: f((r.v / total) * 100, 1) + "% do país" }, { valor: "US$ " + f(r.fob / 1e6) + " milhões", nome: "valor FOB" }];
    }
    $("#g-uf-sub").textContent = "Capítulo 31 em " + ano + ", em milhões de toneladas de produto · Comex Stat";
    barrasOrdenadas($("#g-uf"), { linhas: linhas, fmt: (v) => f(v, 2), aria: "Barras ordenadas: importação de fertilizantes por UF em " + ano + "." });
    tabelaAlternavel($("#g-uf"), [{ t: "UF" }, { t: "Importação (mil t)", n: 1 }, { t: "Participação (%)", n: 1 }, { t: "FOB (US$ milhões)", n: 1 }],
      linhas.map((r) => [r.nome, f(r.v * 1000), f((r.v / total) * 100, 1), f(r.fob / 1e6)]));
  }

  async function censo() {
    const c = await csv("uf_censo_adubacao.csv");
    const por = {};
    for (const r of c) (por[r.uf] = por[r.uf] || { nome: r.uf_nome, curto: r.uf, forte: r.nivel === "BR" })[r.ano_censo] = num(r.pct_adubou_no_ano);
    const linhas = Object.values(por).map((r) => ({ nome: r.nome, curto: r.curto, forte: r.forte, a: r["2006"], b: r["2017"] }))
      .sort((x, y) => (y.forte - x.forte) || (y.b - x.b));
    graficoHalteres($("#g-censo"), { linhas: linhas, rotA: "2006", rotB: "2017", aria: "Gráfico de halteres: estabelecimentos que adubaram em 2006 e em 2017, Brasil e UFs." });
    tabelaAlternavel($("#g-censo"), [{ t: "UF" }, { t: "2006 (%)", n: 1 }, { t: "2017 (%)", n: 1 }, { t: "Variação (p.p.)", n: 1 }],
      linhas.map((r) => [r.nome, f(r.a, 1), f(r.b, 1), sinal(r.b - r.a, 1)]));
  }

  // ------------------------------------------------------------ séries consolidadas
  const tamanho = (b) => (b >= 1048576 ? f(b / 1048576, 1) + " MB" : f(Math.max(1, b / 1024)) + " kB");
  async function listaSeries() {
    const alvo = $("#lista-series");
    const [meta, dic] = await Promise.all([fetch("dados/metadados.json").then((r) => { if (!r.ok) throw new Error("metadados"); return r.json(); }), csv("DICIONARIO.csv")]);
    alvo.replaceChildren(...Object.entries(meta.arquivos).map(([nome, a]) => {
      const cols = dic.filter((r) => r.arquivo === nome);
      const det = h("details", { class: "colunas" }, h("summary", null, "Colunas (" + cols.length + ")"));
      det.addEventListener("toggle", () => {
        if (!det.open || det.childElementCount > 1) return;
        det.append(h("div", { class: "rolagem", tabindex: "0", role: "region", "aria-label": "Colunas de " + nome },
          h("table", null,
            h("thead", null, h("tr", null, ["Coluna", "Descrição", "Unidade", "Fonte"].map((t) => h("th", { scope: "col" }, t)))),
            h("tbody", null, cols.map((r) => h("tr", null, h("td", { class: "fixo" }, h("code", null, r.coluna)), h("td", null, r.descricao), h("td", { class: "fixo" }, r.unidade), h("td", null, r.fonte)))))));
      });
      return h("article", { class: "cartao arquivo" },
        h("div", { class: "arquivo-topo" }, h("span", { class: "arquivo-nome" }, nome),
          h("a", { class: "botao", href: "dados/" + nome, download: true }, "Baixar CSV (" + tamanho(a.bytes) + ")")),
        h("p", { class: "arquivo-desc" }, a.conteudo + "."),
        h("div", { class: "etiquetas" }, [a.nivel, a.frequencia, a.periodo.replace(/^(\d{4})-(\d{4})$/, "$1–$2"), f(a.linhas) + " linhas × " + a.colunas + " colunas", "Fonte: " + a.fonte].map((t) => h("span", null, t))),
        det);
    }));
    const versao = Object.values(meta.versoes_das_fontes).sort().pop();
    $("#versao").textContent = "Versão atual: download das fontes em " + dataBR(versao) + "; consolidação em " + dataBR(meta.gerado_em) + ".";
    $("#cit-versao").textContent = versao;
    $("#cit-ano").textContent = versao.slice(0, 4);
  }

  // ------------------------------------------------------------ arquivos originais
  const FONTES = { anda: "ANDA", banco_mundial: "Banco Mundial", bcb_sgs: "Banco Central", comex_stat: "Comex Stat", faostat: "FAOSTAT", ibge_anuario: "IBGE (Anuário)",
    ibge_sidra: "IBGE (SIDRA)", infra_sa: "Infra S.A.", ipeadata: "Ipeadata", pnf_2050: "Plano Nacional de Fertilizantes", seeg: "SEEG" };
  function repositorio() {
    if (CFG.repo) return CFG.repo.replace(/\/$/, "");
    if (/\.github\.io$/.test(location.hostname)) {
      const nome = location.pathname.split("/").filter(Boolean)[0];
      if (nome) return "https://github.com/" + location.hostname.split(".")[0] + "/" + nome;
    }
    return "";
  }
  const semAcento = (t) => t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  async function listaOriginais() {
    const man = await csv("MANIFESTO.csv");
    const repo = repositorio();
    const corpo = $("#lista-originais"), sel = $("#f-fonte"), busca = $("#f-busca"), cont = $("#f-contagem");
    for (const k of [...new Set(man.map((r) => r.fonte))].sort((a, b) => (FONTES[a] || a).localeCompare(FONTES[b] || b, "pt-BR"))) {
      sel.append(h("option", { value: k }, FONTES[k] || k));
    }
    const linhas = man.map((r) => {
      const base = r.arquivo.split("/").pop();
      const temCopia = !CFG.semCopia.some((p) => r.arquivo.startsWith(p));
      const copia = repo ? repo + "/raw/" + CFG.ramo + "/" + encodeURI(r.arquivo) : "../" + encodeURI(r.arquivo);
      const links = [];
      if (temCopia) links.push(h("a", { href: copia }, "cópia"));
      const url = (r.origem.match(/^https?:\/\/\S+/) || [])[0]; // o manifesto às vezes anota texto depois do endereço
      if (url) links.push(h("a", { href: url, rel: "noopener" }, "fonte original"));
      const tr = h("tr", null,
        h("td", null, h("code", null, base), h("div", { class: "nota", style: "margin-top:2px" }, r.arquivo.split("/").slice(0, -1).join("/"))),
        h("td", { class: "fixo" }, FONTES[r.fonte] || r.fonte),
        h("td", null, r.descricao, r.observacao ? h("div", { class: "nota", style: "margin-top:2px" }, r.observacao) : null),
        h("td", { class: "n" }, tamanho(+r.bytes)),
        h("td", { class: "fixo" }, links.flatMap((l, i) => (i ? [" · ", l] : [l]))));
      return { tr: tr, fonte: r.fonte, texto: semAcento(r.arquivo + " " + r.descricao + " " + (FONTES[r.fonte] || "")) };
    });
    corpo.replaceChildren(...linhas.map((l) => l.tr));
    function filtrar() {
      const q = semAcento(busca.value.trim());
      let visiveis = 0;
      for (const l of linhas) {
        const ok = (!sel.value || l.fonte === sel.value) && (!q || l.texto.includes(q));
        l.tr.hidden = !ok;
        if (ok) visiveis++;
      }
      cont.textContent = visiveis + " de " + linhas.length + " arquivos";
    }
    sel.addEventListener("change", filtrar);
    busca.addEventListener("input", filtrar);
    filtrar();
    if (repo) {
      const a = $("#link-repo");
      a.href = repo;
      a.hidden = false;
    }
  }

  // ------------------------------------------------------------ partida
  const tarefas = [
    [destaque, "#heroi-nota"], [indicadores, "#tiles"], [usoEDependencia, "#g-uso, #g-dep"], [mercado, "#g-anda"], [precos, "#g-precos"],
    [origem, "#g-origem"], [porUF, "#g-uf"], [censo, "#g-censo"], [listaSeries, "#lista-series"], [listaOriginais, "#f-contagem"],
  ];
  for (const [fn, sel] of tarefas) fn().catch((e) => falha(sel, e));
})();
