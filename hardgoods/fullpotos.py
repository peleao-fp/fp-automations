"""
fullpotos (Inventory Entry web) — packings e caixas. Mesmas chamadas que a tela web faz.

Login: variável FULLPOTOS_COOKIE (GitHub) ou, no computador do Pedro, o fullpotos_config.json do fp-compras.
Enquanto o Carlos não expõe essas rotas na API de add-ons, depende desse cookie, que vence.
"""
import json, os, time

import requests

BASE = "https://fullpotos.flexymax.com"
LOCAL_CONF = os.path.expanduser("~/fp-compras/fullpotos_config.json")
PANTA_UQ = "52961702"   # id do app que a tela web manda no audit log

def _conf():
    c = {}
    if os.path.exists(LOCAL_CONF):
        with open(LOCAL_CONF) as f: c = json.load(f)
    if os.environ.get("FULLPOTOS_COOKIE"): c["cookie"] = os.environ["FULLPOTOS_COOKIE"]
    if os.environ.get("FULLPOTOS_USER_UQ"): c["user_uq"] = os.environ["FULLPOTOS_USER_UQ"]
    if not c.get("cookie"): raise RuntimeError("Sem login do fullpotos (FULLPOTOS_COOKIE)")
    return c

def req(method, path, body=None, tries=3):
    c = _conf()
    h = {"Cookie": c["cookie"], "Accept": "application/json", "Origin": BASE, "Referer": BASE + "/inventory-entry",
         "User-Agent": "Mozilla/5.0 fp-automations"}
    for t in range(tries):
        r = requests.request(method, BASE + path, json=body, headers=h, timeout=60)
        if r.status_code in (401, 403): raise RuntimeError(f"fullpotos recusou (HTTP {r.status_code}) — login expirado")
        if r.status_code < 500: return r.json() if r.text.strip() else None
        time.sleep(3 * (t + 1))
    raise RuntimeError(f"fullpotos HTTP {r.status_code} em {path}")

def user_uq(): return _conf().get("user_uq")

def box_of_po(po_unico):
    """Caixa com o mesmo unico do PO (só vale para packing feito no desktop; pelo "Add from PO" web a caixa ganha
    unico próprio — para saber se o PO já foi para packing, use qty_ship do PO)."""
    return req("GET", f"/api/inventory-entry/boxes/{po_unico}")

def boxes_by_awb(awbcode):
    """Só devolve caixas de packing FECHADO. Para packing aberto: packing_details()."""
    return req("GET", f"/api/inventory-entry/packing-box-by-awb?awbcode={awbcode}") or []

def packing(pack_uq):
    return req("GET", f"/api/inventory-entry/packings/{pack_uq}")

def audit(accion, tabla, registro, ext):
    try: req("POST", "/api/audit/log", {"panta_uq": PANTA_UQ, "accion": accion, "tabla": tabla, "registro": registro, "ext_accion": ext})
    except Exception: pass

def create_packing(grower_uq, wphysical_uq, awbcode, packing_no, invoice_no, invoice_date, available_date, details):
    body = {"grower_uq": grower_uq, "packing_no": packing_no, "invoice_no": invoice_no, "awbcode": awbcode,
            "invoice_date": invoice_date, "details": details, "porder_no": 0, "wphysical_uq": wphysical_uq,
            "available_date": available_date, "consolidated": False}
    r = req("POST", "/api/inventory-entry/packings", body)
    if not (r and r.get("success")): raise RuntimeError(f"criar packing falhou: {r}")
    audit("Insert", "flower_packing", r["unico"], "Insert Packing List FlexyMaxApp")
    return r["unico"]

def add_from_po(pack_uq, po_unico, qty):
    r = req("POST", "/api/inventory-entry/po-entries", {"porder_uq": po_unico, "packing_uq": pack_uq, "qty_ship": int(qty), "user_uq": user_uq()})
    if not (r and r.get("success")): raise RuntimeError(f"Add from PO falhou: {r}")
    audit("Insert", "flower_packing_box", po_unico, "Insert Inventory Box FlexyMaxApp")
    return r

def packing_details(pack_uq):
    rows = req("GET", f"/api/inventory-entry/packings/{pack_uq}/details")
    rows = rows if isinstance(rows, list) else (rows or {}).get("boxes") or (rows or {}).get("data") or []
    return [{k.lower(): v for k, v in r.items()} for r in rows]
