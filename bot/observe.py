#!/usr/bin/env python3
"""
Bot de hardgoods — MODO OBSERVANDO: lê o e-mail do fornecedor (IA), cruza com PBs/POs e manda ao Pedro
o que FARIA. Não grava nada no sistema.

  python -m bot.observe --gist <id>               # e-mail guardado num Gist (Power Automate / disparo manual)
  python -m bot.observe --files a.pdf b.pdf --subject "..." --sender x@y.com [--no-email]

Gist esperado: meta.json {subject, from, date}, body.txt (ou body.html) e anexos att_<nome>.b64 (base64).
Variáveis: ANTHROPIC_API_KEY, RESEND_API_KEY, GH_TOKEN.
"""
import argparse, base64, html, json, math, os, re, sys
from datetime import date, datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot import reader
from hardgoods import purchase as P

PREFIX = {"SYNDICATE": "SSA", "WD IMPORT": "WDI", "SMITHERS": "SFP", "OASIS": "SFP", "GIFTWARES": "GWS", "POTS COMPANY": "GWS"}
STORE_WH = {"PMP": "FT LAUDERDALE", "WPB": "WEST PALM BEACH", "NPL": "NAPLES", "MIA": "MIAMI"}
CODE = re.compile(r"\b(?:\d{2,5}-\d{2,3}-\d{2,4}|C\d{3,4}(?:-\d{2})?|[A-Z]{1,5}\d{2,5}[A-Z]{0,3}|\d{2}-\d{5})\b")
TO = ["pedro@fullpot.com"]
FROM = "Bot Hardgoods - Full Pot <pedro@fullpot.com>"

def prefix_of(supplier):
    s = (supplier or "").upper()
    return next((v for k, v in PREFIX.items() if k in s), None)

def codes(desc): return CODE.findall((desc or "").upper())

def so_units(c):
    raw = c / 0.62; b = math.floor(raw); return round(b + 0.99 if raw <= b + 0.99 else b + 1.99, 2)

def find_pos(prefix, store, around, so=None, days=12):
    """POs do fornecedor/loja nas datas próximas; se houver SO, prefere os que têm a SO nas notas."""
    wh = STORE_WH.get(store); out = []
    for i in range(-days, days + 1):
        d = (around + timedelta(days=i)).isoformat()
        try: rows = P.pos_by_date(d)
        except Exception: continue
        for p in rows:
            if (p.get("grower_po") or "").split("-")[0] != prefix: continue
            if wh and (p.get("warehouse") or "").strip().upper() != wh: continue
            dd = P.po_detail(p["unico"]) or {}
            out.append({**p, **{k: dd.get(k) for k in ("details", "bunches_case", "up_x_pack", "po_price", "qty_porder", "total_units", "ext_price")}, "_ship": d})
    if so:
        with_so = [p for p in out if so in (p.get("details") or "")]
        if with_so: return with_so
    return out

def plan_invoice(doc, pos):
    """Compara invoice × POs. Custo por unidade com frete rateado pelo valor."""
    lines = [l for l in doc["lines"] if (l["qty_shipped"] or l["extension"])]
    sub = sum(float(l["extension"] or 0) for l in lines) or 1; F = float(doc["freight"] or 0) + float(doc["other_charges"] or 0)
    used, rows = set(), []
    for l in lines:
        cand = [p for p in pos if p["unico"] not in used and l["code"].upper() in codes(p["description"])]
        p = next((x for x in cand if int(x["qty_porder"] or 0) == int(l["qty_shipped"] or 0)), cand[0] if cand else None)
        if not p: rows.append({"kind": "extra", "line": l}); continue
        used.add(p["unico"])
        upc = int(p["bunches_case"] or 1) * int(p["up_x_pack"] or 1)
        per_unit_invoice = l["unit"].upper() in ("EA", "EACH", "PC", "UN", "UNIT")
        qty_units = float(l["qty_shipped"]) * (1 if per_unit_invoice else upc)
        unit_cost = (float(l["extension"]) + float(l["extension"]) / sub * F) / qty_units if qty_units else 0
        old = float(p["po_price"] or 0) / max(1, int(p["up_x_pack"] or 1))
        po_units = int(p["qty_porder"] or 0) * upc
        rows.append({"kind": "match", "line": l, "po": p, "upc": upc, "unit_cost": round(unit_cost, 4), "old_cost": round(old, 4),
                     "qty_diff": qty_units - po_units, "po_units": po_units, "inv_units": qty_units})
    for p in pos:
        if p["unico"] not in used: rows.append({"kind": "missing", "po": p})
    return rows

def pb_lines(store, around, days=10):
    """Linhas de PB (fechados) de hardgoods da loja, nas datas próximas."""
    wh = {"PMP": "CAM27168", "WPB": "82G89770", "NPL": "YBRT6967", "MIA": "BUEB4005"}.get(store); out = {}
    for i in range(-3, days + 1):
        d = (around + timedelta(days=i)).isoformat()
        try: rows = P._req("GET", f"/api/prebooks-without-po?date={d}&product_type=HARDGOODS") or {}
        except Exception: continue
        for x in rows.get("data", []):
            if not wh or (x.get("wphysical_uq") or "").strip() == wh: out[x["pbook_d_uq"]] = x
    return list(out.values())

def similar(code, cands):
    """Código parecido: mesmo começo (ex.: 7121-06-2218 × 7121-06-2216)."""
    parts = code.split("-")
    head = "-".join(parts[:-1]) if len(parts) > 2 else (code[:-2] if len(code) > 4 else code)
    return [c for c in cands if c != code and c.startswith(head)]

def plan_reply(doc, prefix, store):
    """Resposta: o que não vem → linhas de PO/PB a tirar; código que não existe no PB mas parece outro → pergunta."""
    out = []
    bad = [l for l in doc["lines"] if l["status"] in ("out_of_stock", "discontinued", "cannot_order", "backorder")]
    if not bad: return out
    pos = find_pos(prefix, store, date.today(), doc.get("sales_order") or None, days=10)
    pbs = pb_lines(store, date.today())
    for l in bad:
        code = l["code"].upper()
        hit = [p for p in pos if code in codes(p["description"])]
        pb_hit = [x for x in pbs if code in codes(x["description"])]
        near = [] if (hit or pb_hit) else ([x for x in pbs if similar(code, codes(x["description"]))] +
                                            [dict(p, pbook_no=p.get("pbook_no")) for p in pos if similar(code, codes(p["description"]))])
        out.append({"line": l, "pos": hit, "pb": pb_hit, "near": near})
    return out

def money(x): return f"${x:,.2f}"

def questions(doc, rows):
    """Perguntas ao Pedro: (pergunta, o que o bot faria, regra que já cobre ou None)."""
    q = []
    if doc["doc_type"] == "invoice":
        for r in rows:
            if r["kind"] == "match":
                l, po = r["line"], r["po"]
                if r["old_cost"] and abs(r["unit_cost"] - r["old_cost"]) / r["old_cost"] > 0.05:
                    q.append((f"{l['code']}: custo/un muda {r['old_cost']:.4f} → {r['unit_cost']:.4f} ({(r['unit_cost']/r['old_cost']-1)*100:+.0f}%). Atualizo PO e caixa?",
                              "sim, uso o custo da fatura", None))
                if r["qty_diff"]:
                    q.append((f"{l['code']}: PO tem {r['po_units']:g} un, fatura {r['inv_units']:g} un ({l['status']}). Ajusto PO e caixa ao que veio?",
                              "sim, deixo como veio", "R6"))
            elif r["kind"] == "missing":
                q.append((f"{r['po']['description'].strip()[:40]} ({r['po']['grower_po']}) não está na fatura. Tiro o PO e a caixa?",
                          "sim, mas antes confiro se a leitura fechou com o subtotal", "R6"))
            elif r["kind"] == "extra":
                l = r["line"]
                q.append((f"{l['code']} {l['description'][:30]} veio na fatura sem PO ({l['qty_shipped']:g} × ${l['price']}). O que faço?",
                          "não entra, só aviso" if not l["price"] else "pergunto: criar PO ou ignorar", "R10" if not l["price"] else None))
    else:
        for r in rows:
            l = r["line"]
            if r["near"]:
                n = r["near"][0]
                q.append((f"{l['code']} ({l['status']}) não está no PB, mas o PB {n['pbook_no']} tem {n['description'].strip()[:40]}. É o mesmo item? Se sim, tiro.",
                          "não faço nada até você confirmar", None))
            elif r["pos"] or r["pb"]:
                where = ", ".join([p["grower_po"] for p in r["pos"]] + [f"PB {x['pbook_no']}" for x in r["pb"]])
                q.append((f"{l['code']} {l['description'][:30]} — {l['status']}. Tiro de {where}?", "sim", "R1"))
            else:
                q.append((f"{l['code']} {l['description'][:30]} — {l['status']}: não achei em nenhum PB/PO desta loja.", "nada a fazer", None))
    for u in doc.get("uncertainties") or []:
        q.append((f"A leitura ficou em dúvida: {u}", "não faço nada até você responder", None))
    return q

def report_html(doc, kind_rows, problems):
    e = html.escape
    h = [f"<h3>🔍 Bot hardgoods — OBSERVANDO (nada foi gravado)</h3>",
         f"<p><b>{e(doc['supplier'])}</b> · {e(doc['doc_type'])} · loja <b>{e(doc['store'])}</b> · SO {e(doc['sales_order'] or '—')}"
         f" · invoice {e(doc['invoice_number'] or '—')} · {len(doc['lines'])} linhas · subtotal {money(doc['subtotal'])}"
         f" · frete {money(doc['freight'])} · total {money(doc['total'])}</p>"]
    if problems:
        h.append("<p style='color:#CF222E'><b>PARARIA AQUI:</b> " + e("; ".join(problems)) + " — a leitura não fechou com a fatura.</p>")
    if doc["doc_type"] == "invoice":
        m = [r for r in kind_rows if r["kind"] == "match"]
        h.append("<table border=1 cellpadding=3 style='border-collapse:collapse;font-size:12px'><tr><th>Item</th><th>PO</th><th>Qtd PO→fatura (un)</th>"
                 "<th>Custo/un atual</th><th>Custo/un fatura (c/ frete)</th><th>O que eu faria</th></tr>")
        for r in m:
            acts = []
            if abs(r["unit_cost"] - r["old_cost"]) > 0.005: acts.append(f"custo {r['old_cost']:.4f} → {r['unit_cost']:.4f}")
            if r["qty_diff"]: acts.append(f"quantidade {r['po_units']:g} → {r['inv_units']:g} un")
            h.append(f"<tr><td>{e(r['line']['code'])} {e(r['line']['description'][:30])}</td><td>{e(r['po']['grower_po'])}</td>"
                     f"<td>{r['po_units']:g} → {r['inv_units']:g}</td><td>{r['old_cost']:.4f}</td><td>{r['unit_cost']:.4f}</td>"
                     f"<td>{e('; '.join(acts) or 'nada (já bate)')}</td></tr>")
        h.append("</table>")
        for r in kind_rows:
            if r["kind"] == "missing": h.append(f"<p>❌ PO sem linha na fatura (não veio?): {e(r['po']['grower_po'])} {e(r['po']['description'].strip()[:40])} — eu tiraria o PO e a caixa</p>")
            if r["kind"] == "extra": h.append(f"<p>⚠️ Na fatura sem PO: {e(r['line']['code'])} {e(r['line']['description'][:40])} {r['line']['qty_shipped']:g} — PARARIA e te perguntaria</p>")
    else:
        for r in kind_rows:
            l = r["line"]
            where = ", ".join([p["grower_po"] for p in r["pos"]] + [f"PB {x['pbook_no']}" for x in r["pb"]]) or \
                    (f"parecido no PB {r['near'][0]['pbook_no']}: {r['near'][0]['description'].strip()[:30]}" if r["near"] else "não achei no PB/PO")
            h.append(f"<p>• {e(l['code'])} {e(l['description'][:40])} — <b>{e(l['status'])}</b> → tiraria de: {e(where)}</p>")
        if not kind_rows: h.append("<p>Nada a tirar: o fornecedor confirmou tudo.</p>")
    qs = questions(doc, kind_rows)
    if qs:
        h.append("<h4>Perguntas para você</h4><ol>")
        for qq, ans, rule in qs:
            tag = f"<span style='color:#2DA44E'>[regra {rule}: faria sem perguntar]</span>" if rule else "<span style='color:#BF8700'>[sem regra: preciso da sua resposta]</span>"
            h.append(f"<li>{e(qq)}<br><i>O que eu faria: {e(ans)}</i> {tag}</li>")
        h.append("</ol><p style='font-size:12px'>Responda pelo número (ex.: <b>1 sim, 3 não: deixa o PO</b>). Cada resposta nova vira uma regra em bot/regras.md.</p>")
    u = doc.get("_usage", {})
    h.append(f"<p style='color:#57606A;font-size:11px'>IA: {e(str(u.get('model')))} · {u.get('input')} tokens de entrada, {u.get('output')} de saída</p>")
    return "".join(h)

def load_gist(gid):
    tok = os.environ.get("GH_TOKEN"); hd = {"Authorization": f"token {tok}"} if tok else {}
    g = requests.get(f"https://api.github.com/gists/{gid}", headers=hd, timeout=60).json()["files"]
    def content(f):
        return requests.get(f["raw_url"], headers=hd, timeout=60).text if f.get("truncated") else f["content"]
    meta = json.loads(content(g["meta.json"])) if "meta.json" in g else {}
    body = content(g["body.txt"]) if "body.txt" in g else re.sub("<[^>]+>", " ", content(g["body.html"])) if "body.html" in g else ""
    atts = [(n[4:-4], base64.b64decode(content(f))) for n, f in g.items() if n.startswith("att_") and n.endswith(".b64")]
    return meta.get("subject", ""), meta.get("from", ""), body, atts

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gist"); ap.add_argument("--files", nargs="*"); ap.add_argument("--subject", default=""); ap.add_argument("--sender", default="")
    ap.add_argument("--text", default="", help="corpo do e-mail (teste manual, sem Gist)")
    ap.add_argument("--no-email", action="store_true"); ap.add_argument("--out", default="out")
    a = ap.parse_args()
    if a.gist: subject, sender, body, atts = load_gist(a.gist)
    else: subject, sender, body, atts = a.subject, a.sender, a.text, [(os.path.basename(f), open(f, "rb").read()) for f in a.files or []]
    docs = []
    for att in (atts or [None]):        # uma leitura por anexo; cada anexo pode ter várias invoices (uma por loja)
        docs.extend(reader.read_document(subject, sender, body, [att] if att else []))
    os.makedirs(a.out, exist_ok=True)
    parts = []
    for d in docs:
        prefix = prefix_of(d["supplier"]); problems = reader.check_totals(d)
        if d["doc_type"] == "invoice" and prefix and not problems:
            around = date.fromisoformat(d["invoice_date"]) if d["invoice_date"] else date.today()
            rows = plan_invoice(d, find_pos(prefix, d["store"], around, d["sales_order"] or None))
        elif d["doc_type"] in ("reply", "order_confirmation") and prefix:
            rows = plan_reply(d, prefix, d["store"])
        else:
            rows = []
            if not prefix: problems.append(f"fornecedor '{d['supplier']}' fora da lista do bot")
        parts.append(report_html(d, rows, problems))
        print(json.dumps({k: d[k] for k in ("supplier", "doc_type", "store", "sales_order", "invoice_number", "subtotal", "freight", "total")}),
              "| linhas", len(d["lines"]), "| problemas", problems, "| ações", len(rows))
    body_html = "<hr>".join(parts)
    with open(os.path.join(a.out, "observe.html"), "w") as f: f.write(body_html)
    with open(os.path.join(a.out, "observe.json"), "w") as f: json.dump(docs, f, indent=1, default=str)
    if a.no_email: return
    r = requests.post("https://api.resend.com/emails", timeout=60, headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
                      json={"from": FROM, "to": TO, "subject": f"🔍 [observando] {subject or docs[0]['supplier']}", "html": body_html})
    print("e-mail:", r.status_code, r.text[:120])

if __name__ == "__main__":
    main()
