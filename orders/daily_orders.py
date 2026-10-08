#!/usr/bin/env python3
"""
Pedidos diários — Holex / EZ Flower / Anton Spaargaren.

Todo dia útil às 4:20 PM (Miami) lê os POs da data de embarque (hoje +2; sexta → terça),
gera um PDF por fornecedor no formato do relatório "PURCHASE ORDERS" e envia pelo Resend,
com cópia para o comprador.

Uso:
  python orders/daily_orders.py                   # data automática, envia
  python orders/daily_orders.py --date 2026-10-09 # força a data de embarque
  python orders/daily_orders.py --dry-run         # só gera os PDFs em ./out, não envia
  python orders/daily_orders.py --test            # envia só para o comprador, assunto "TESTE"
  python orders/daily_orders.py --respect-clock   # só roda entre 16:15 e 17:59 em Miami (cron)

Variáveis de ambiente: RESEND_API_KEY, GH_TOKEN + RESULTS_GIST_ID (registro de envios).
"""
import argparse, base64, json, os, re, sys, time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import holidays
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas

API_BASE = "https://full-pot-flexy-add-ons.vercel.app"
MIAMI    = ZoneInfo("America/New_York")

FROM_EMAIL = "Pedro Leão - Full Pot <pedro@fullpot.com>"
BUYER_CC   = ["pedro@fullpot.com"]
# Prefixo do grower_po → fornecedor (emails confirmados pelo Pedro em 2026-10-07)
VENDORS = {
    "HFW": {"name": "HOLEX - HOLLAND",  "short": "HFW", "to": ["ricky.van.tol@holex.com"]},
    "EZF": {"name": "EZ FLOWER",        "short": "EZF", "to": ["danielp@ezflower.nl"]},
    "ANS": {"name": "ANTON SPAARGAREN", "short": "ANS", "to": ["g.de.beer@antonspaargaren.nl"]},
}
CASE_NAMES = {"BX": "BOX", "QB": "QUARTER", "HB": "HALF", "EB": "EIGHTH"}   # como o relatório do desktop mostra
SENT_FILE = "daily_orders_sent.json"   # no Gist de resultados: {"YYYY-MM-DD": {"HFW": "timestamp", ...}}

# ── datas ────────────────────────────────────────────────────────────────────
def _hol(y): return set(holidays.US(years=[y, y + 1]).keys()) | set(holidays.NL(years=[y, y + 1]).keys())
def is_valid_ship_day(d): return d.weekday() != 6 and d not in _hol(d.year)

def target_ship_date(today):
    """Seg–Qui: +2 dias; Sex: terça (+4). Sáb/Dom: None. Feriado ou domingo → próximo dia válido."""
    if today.weekday() >= 5: return None
    t = today + timedelta(days=4 if today.weekday() == 4 else 2)
    while not is_valid_ship_day(t): t += timedelta(days=1)
    return t

# ── API ──────────────────────────────────────────────────────────────────────
def api_get(path, tries=4):
    for i in range(tries):
        try:
            r = requests.get(API_BASE + path, timeout=60)
            if r.status_code == 200: return r.json()
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = str(e)
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"API falhou em {path}: {err}")

def ordinal(n): return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

def customer_no(customer):
    m = re.search(r"-\s*(\d+)\s*/", customer or "")
    return m.group(1) if m else ""

def load_orders(ship):
    """{prefixo: [linhas]} só dos fornecedores configurados, com os detalhes de cada PO."""
    rows = api_get(f"/api/purchase-orders?ship_date={ship.isoformat()}&grower_uq=%25&product_uq=%25").get("data", [])
    out = {}
    for p in rows:
        pref = (p.get("grower_po") or "").split("-")[0]
        if pref not in VENDORS or not p.get("active", True): continue
        d = api_get(f"/api/purchase-orders/{p['unico']}").get("data") or {}
        st = lambda k, src=d: str(src.get(k) or "").strip()
        out.setdefault(pref, []).append({
            "po": st("grower_po", p), "pb": st("pbook_no", p), "warehouse": st("wp_name") or st("warehouse", p),
            "product": re.sub(r"\s+", " ", st("description")), "case": CASE_NAMES.get(st("case_sh"), st("case_sh")),
            "qty": int(d.get("qty_porder") or 0), "bunches": int(d.get("bunches_case") or 0),
            "ux_bunch": int(d.get("up_x_pack") or 0), "ux_box": int(d.get("tunits_x_box") or 0),
            "t_units": int(d.get("total_units") or 0), "price": float(d.get("po_price") or 0),
            "ext": float(d.get("ext_price") or 0), "customer": customer_no(p.get("customer")),
            "box_mark": st("cporder_no", p), "notes": st("details") if st("details") not in ("", ".") else "",
            "cargo": st("cargo"),
        })
    for lines in out.values(): lines.sort(key=lambda l: (l["po"], l["product"]))
    return out

# ── PDF ──────────────────────────────────────────────────────────────────────
W, H = landscape(letter)
M = 40

def _header(c, now, page):
    c.setFont("Helvetica-Bold", 16); c.drawCentredString(W / 2, H - 40, "FULL POT")
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(W / 2, H - 52, "Phone: (954)568 4467 / . Fax:(954)568 4463 /")
    c.drawCentredString(W / 2, H - 62, "1516 SW 13 CT - POMPANO BEACH, FL - USA - e-mail: sales@fullpot.com")
    c.setFont("Helvetica-Bold", 7.5); c.drawString(M + 20, H - 78, "Date")
    c.setFont("Helvetica", 7.5); c.drawString(M + 42, H - 78, now.strftime("%m/%d/%Y %I:%M:%S %p"))
    c.setFont("Helvetica-Bold", 7.5); c.drawString(W - M - 90, H - 78, "Page"); c.setFont("Helvetica", 7.5)
    c.drawString(W - M - 68, H - 78, str(page))
    c.setLineWidth(1.2); c.line(M, H - 84, W - M, H - 84); c.line(M, H - 87, W - M, H - 87)
    return H - 100

COLS = [("Product", M + 6, "l"), ("Case/Box", 330, "c"), ("Qty", 390, "c"), ("Bunches", 432, "c"), ("UxBunch", 480, "c"),
        ("UxBox", 528, "c"), ("T.Units", 570, "c"), ("Price x U", 625, "c"), ("Ext Price", W - M - 30, "c")]

def _txt(c, x, y, s, align):
    {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[align](x, y, s)

def _po_header(c, y, line, ship):
    c.setFont("Helvetica-Bold", 16); c.drawCentredString(W / 2, y - 6, "PURCHASE ORDERS"); y -= 26
    c.setFont("Helvetica-Bold", 9); c.drawString(M + 6, y, "PO"); c.setFont("Helvetica", 9); c.drawString(M + 24, y, line["po"])
    c.setFont("Helvetica-Bold", 9); c.drawString(250, y, "Vendor"); c.setFont("Helvetica", 9); c.drawString(285, y, line["vendor"])
    c.setFont("Helvetica-Bold", 9); c.drawString(560, y, "Vendor Ship.Date"); c.setFont("Helvetica", 9)
    c.drawString(645, y, ship.strftime("%b %-d %Y")); y -= 16
    c.setFont("Helvetica-Bold", 9); c.drawString(M + 18, y, "Warehouse"); c.setFont("Helvetica", 9); c.drawString(M + 70, y, line["warehouse"])
    c.setFont("Helvetica-Bold", 9); c.drawString(560, y, "Cargo"); c.setFont("Helvetica", 9); c.drawString(590, y, line["cargo"]); y -= 8
    c.setFillColor(colors.HexColor("#EEEEEE")); c.rect(M, y - 14, W - 2 * M, 14, fill=1, stroke=1); c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7.5)
    for name, x, a in COLS: _txt(c, x, y - 10, name, a if a != "l" else "l")
    return y - 16

def _line(c, y, l):
    notes = [s for s in re.split(r"\s{2,}|\n", l["notes"]) if s.strip()]
    h = 62 + 10 * max(len(notes), 1)
    c.setFillColor(colors.HexColor("#EEEEEE")); c.rect(M, y - h, W - 2 * M, h - 30, fill=1, stroke=0); c.setFillColor(colors.black)
    c.rect(M, y - h, W - 2 * M, h, fill=0, stroke=1); c.line(M, y - 30, W - M, y - 30)
    c.setFont("Helvetica", 7.5)
    vals = [l["product"][:48], l["case"], str(l["qty"]), str(l["bunches"]), str(l["ux_bunch"]), str(l["ux_box"]),
            str(l["t_units"]), f"$   {l['price']:.4f}", f"$   {l['ext']:,.2f}"]
    for (name, x, a), v in zip(COLS, vals): _txt(c, x, y - 10, v, a)
    c.setFont("Helvetica-Bold", 7.5); c.drawString(M + 30, y - 24, "Vendor Item")
    c.drawCentredString(530, y - 24, "- - - - - Box Marks / Marcas de las cajas - - - - - -Instructions")
    c.drawString(M + 22, y - 41, "Customer"); c.drawString(250, y - 41, "PB."); c.drawString(460, y - 41, "Box Mark")
    c.setFont("Helvetica", 7.5)
    c.drawString(M + 62, y - 41, l["customer"]); c.drawString(272, y - 41, l["pb"]); c.drawString(500, y - 41, l["box_mark"])
    c.setFont("Helvetica", 7.5); c.drawString(M + 4, y - 54, "NOTES:")
    for i, n in enumerate(notes): c.drawString(M + 8, y - 64 - 10 * i, n[:140])
    return y - h - 6

def build_pdf(path, vendor_name, lines, ship, now):
    c = canvas.Canvas(path, pagesize=landscape(letter)); page = 1
    by_po = {}
    for l in lines: by_po.setdefault(l["po"], []).append({**l, "vendor": vendor_name})
    tot_boxes = tot_usd = 0
    for i, (po, pl) in enumerate(by_po.items()):
        if i: c.showPage(); page += 1
        y = _po_header(c, _header(c, now, page), pl[0], ship)
        for l in pl:
            need = 72 + 10 * max(len(l["notes"].split("  ")), 1)
            if y - need < 60:
                c.showPage(); page += 1; y = _header(c, now, page) - 8
            y = _line(c, y, l)
        boxes = sum(l["qty"] for l in pl); usd = sum(l["ext"] for l in pl)
        tot_boxes += boxes; tot_usd += usd
        c.setFont("Helvetica-Bold", 8)
        c.drawString(400, y - 12, "Total Ship Date"); c.drawString(490, y - 12, str(boxes))
        c.drawString(W - M - 110, y - 12, "Total $"); c.drawRightString(W - M - 10, y - 12, f"{usd:,.2f}")
        if i == len(by_po) - 1:
            c.drawString(400, y - 28, "Total Vendor"); c.drawString(490, y - 28, str(tot_boxes))
            c.drawString(W - M - 110, y - 28, "Total $"); c.drawRightString(W - M - 10, y - 28, f"{tot_usd:,.2f}")
        c.setFont("Helvetica-Oblique", 7.5); c.drawString(M, 30, "FULL POT"); c.drawRightString(W - M, 30, "View next pages")
    c.save()
    return tot_boxes, tot_usd

# ── registro de envios (Gist) ────────────────────────────────────────────────
def gist_load():
    tok, gid = os.environ.get("GH_TOKEN"), os.environ.get("RESULTS_GIST_ID")
    if not (tok and gid): return None
    r = requests.get(f"https://api.github.com/gists/{gid}", headers={"Authorization": f"token {tok}"}, timeout=30)
    r.raise_for_status()
    f = r.json()["files"].get(SENT_FILE)
    return json.loads(f["content"]) if f else {}

def gist_save(data):
    tok, gid = os.environ.get("GH_TOKEN"), os.environ.get("RESULTS_GIST_ID")
    if not (tok and gid): return
    requests.patch(f"https://api.github.com/gists/{gid}", headers={"Authorization": f"token {tok}"}, timeout=30,
                   json={"files": {SENT_FILE: {"content": json.dumps(data, indent=1)}}}).raise_for_status()

# ── envio ────────────────────────────────────────────────────────────────────
def send(to, cc, subject, pdf_path):
    key = os.environ["RESEND_API_KEY"]
    with open(pdf_path, "rb") as f: att = base64.b64encode(f.read()).decode()
    r = requests.post("https://api.resend.com/emails", timeout=60, headers={"Authorization": f"Bearer {key}"}, json={
        "from": FROM_EMAIL, "to": to, "cc": cc, "subject": subject, "text": " ",
        "attachments": [{"filename": os.path.basename(pdf_path), "content": att}]})
    if r.status_code >= 300: raise RuntimeError(f"Resend {r.status_code}: {r.text[:200]}")
    return r.json().get("id")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test", action="store_true"); ap.add_argument("--respect-clock", action="store_true")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()

    now = datetime.now(MIAMI)
    # O cron roda às 20:20 e 21:20 UTC (cobre EDT e EST); a 2ª execução vira reserva — o registro no Gist evita envio duplo
    if a.respect_clock and not ((now.hour == 16 and now.minute >= 15) or now.hour == 17):
        print(f"Fora do horário em Miami ({now:%H:%M}) — nada a fazer"); return
    ship = date.fromisoformat(a.date) if a.date else target_ship_date(now.date())
    if not ship: print("Fim de semana — não envia"); return
    print(f"Hoje (Miami): {now:%a %Y-%m-%d %H:%M} → embarque {ship:%a %Y-%m-%d}")

    sent = {} if (a.dry_run or a.test) else (gist_load() or {})
    orders = load_orders(ship)
    os.makedirs(a.out, exist_ok=True)
    errors = 0
    for pref, v in VENDORS.items():
        lines = orders.get(pref)
        if not lines: print(f"  {pref}: sem POs"); continue
        if sent.get(ship.isoformat(), {}).get(pref):
            print(f"  {pref}: já enviado em {sent[ship.isoformat()][pref]} — pulando"); continue
        fname = f"{pref}  for arrival on {ship:%b} {ordinal(ship.day)}.pdf"
        path = os.path.join(a.out, fname)
        boxes, usd = build_pdf(path, v["name"], lines, ship, now)
        npo = len({l['po'] for l in lines})
        print(f"  {pref}: {npo} POs, {boxes} caixas, ${usd:,.2f} → {path}")
        if a.dry_run: continue
        subject = f"{pref}  for arrival on {ship:%b} {ordinal(ship.day)}"
        to, cc = (BUYER_CC, []) if a.test else (v["to"], BUYER_CC)
        if a.test: subject = "TESTE — " + subject + f" (iria para: {', '.join(v['to'])})"
        try:
            mid = send(to, cc, subject, path); print(f"     enviado ({mid}) para {to} cc {cc}")
        except Exception as e:
            errors += 1; print(f"     ERRO no envio: {e}"); continue
        if not a.test:
            sent.setdefault(ship.isoformat(), {})[pref] = now.isoformat(timespec="minutes")
            try: gist_save(sent)
            except Exception as e:
                errors += 1; print(f"     ATENÇÃO: enviado, mas não consegui registrar no Gist ({e}) — a execução reserva pode reenviar")
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
