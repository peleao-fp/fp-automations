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

def box(unico):
    return req("GET", f"/api/inventory-entry/boxes/{unico}")

def update_box(unico, cost=None, price=None, fill_box_id=None, allow_customer_reset=False, packs_box=None):
    """Altera custo (f_cost_x_u) e/ou venda (price_x_u) da caixa; tudo o mais vai igual ao que está gravado.
    Nunca apaga o BOXID: manda o atual, ou fill_box_id se estiver vazio. Confere customer/BOXID na leitura de volta."""
    b = box(unico)
    if not b: raise RuntimeError(f"caixa {unico} não encontrada")
    st = lambda v: (v or "").strip() if isinstance(v, str) else v
    box_id = st(b.get("box_id")) or (fill_box_id or "")
    body = {
        "product_uq": b.get("box_pack_uq"), "product_desc": st(b.get("description")), "case_uq": b.get("case_uq"),
        "cporder_no": st(b.get("cporder_no")) or "", "box_qty": b.get("box_qty"), "packs_box": b.get("packs_box"),
        "packs_units": b.get("up_x_pack"), "stem_pack": b.get("stem_pack"), "lote": b.get("lote"), "cut_point": b.get("cut_point"),
        "box_id": box_id, "price_x_u": round(float(price if price is not None else b.get("price_x_u") or 0), 2),
        "f_cost_x_u": round(float(cost if cost is not None else b.get("f_cost_x_u") or 0), 4),
        "freight_cost": b.get("freight_cost"), "duties_cost": b.get("duties_cost"), "broker_cost": b.get("broker_cost"),
        "handling_cost": b.get("handling_cost"), "charge_cost": b.get("charge_cost"), "inventory_notes": st(b.get("inventory_notes")) or "",
        "units_x_box": b.get("tunits_x_box"), "total_units": b.get("total_units"), "t_charges": b.get("total_charge"),
        "c_cost_x_u": b.get("c_cost_x_u"), "t_cost_x_u": b.get("t_cost_x_u"), "user_uq": user_uq(),
    }
    if packs_box is not None:   # quantidade por caixa (a rota lot info /wh-control está quebrada no servidor)
        upx = int(b.get("up_x_pack") or 1); body["packs_box"] = int(packs_box)
        body["units_x_box"] = int(packs_box) * upx; body["total_units"] = int(packs_box) * upx * int(b.get("box_qty") or 1)
    r = req("PUT", f"/api/inventory-entry/boxes/{unico}", body)
    if not (r and r.get("success")): raise RuntimeError(f"PUT da caixa falhou: {r}")
    audit("Edit", "flower_packing_box", unico, "Update Inventory Box FlexyMaxApp")
    a = box(unico)
    if packs_box is not None and int(a.get("packs_box") or 0) != int(packs_box): raise RuntimeError(f"CONFERÊNCIA: quantidade não gravou na caixa {unico}")
    for k in (("box_qty", "box_pack_uq") if allow_customer_reset else ("customer", "customer_uq", "box_qty", "box_pack_uq")):
        if a.get(k) != b.get(k): raise RuntimeError(f"CONFERÊNCIA: campo {k} mudou ({b.get(k)} → {a.get(k)}) na caixa {unico}")
    if abs(float(a.get("f_cost_x_u") or 0) - body["f_cost_x_u"]) > 0.001 or abs(float(a.get("price_x_u") or 0) - body["price_x_u"]) > 0.005:
        raise RuntimeError(f"CONFERÊNCIA: custo/venda não gravaram na caixa {unico}")
    if st(a.get("box_id")) != box_id: raise RuntimeError(f"CONFERÊNCIA: BOXID ficou '{st(a.get('box_id'))}', esperado '{box_id}'")
    return b, a

def update_packing_header(pack_uq, **changes):
    h = packing(pack_uq)
    if not h: raise RuntimeError(f"packing {pack_uq} não encontrado")
    st = lambda v: (v or "").strip() if isinstance(v, str) else v
    body = {"grower_uq": st(h.get("grower_uq")), "packing_no": st(h.get("packing_no")), "invoice_no": st(h.get("invoice_no")),
            "awbcode": st(h.get("awbcode")), "invoice_date": str(h.get("date_invo"))[:10], "details": st(h.get("details")),
            "wphysical_uq": st(h.get("wphysical_uq")), "porder_no": int(h.get("porder_no") or 0),
            "available_date": str(h.get("available_date"))[:10], "consolidated": bool(h.get("consolidated"))}
    body.update(changes)
    r = req("PUT", f"/api/inventory-entry/packings/{pack_uq}", body)
    if not (r and r.get("success")): raise RuntimeError(f"PUT do packing falhou: {r}")
    audit("Edit", "flower_packing", pack_uq, "Update Packing List FlexyMaxApp")
    return packing(pack_uq)

def set_price(unico, price):
    """Só a venda (rota "Change Prices" da tela web). Confere que customer/BOXID não mudaram."""
    b = box(unico)
    r = req("PUT", f"/api/inventory-entry/boxes/{unico}/price", {"price_x_unit": round(float(price), 2), "user_uq": user_uq()})
    if not (r and r.get("success")): raise RuntimeError(f"Change Prices falhou: {r}")
    audit("Edit", unico, unico, "Change Prices FlexyMaxApp")
    a = box(unico)
    for k in ("customer", "customer_uq", "box_id", "f_cost_x_u", "box_qty"):
        if a.get(k) != b.get(k): raise RuntimeError(f"CONFERÊNCIA: {k} mudou ({b.get(k)} → {a.get(k)}) na caixa {unico}")
    return a

def delete_box(unico):
    r = req("DELETE", f"/api/inventory-entry/boxes/{unico}", {"user_uq": user_uq()})
    if not (r and r.get("success")): raise RuntimeError(f"apagar caixa falhou: {r}")
    audit("Delete", "flower_packing_box", unico, "Delete Inventory Box FlexyMaxApp")
    return r

def set_box_units(unico, packs_box, box_qty=None):
    """Quantidade da caixa pela rota "lot info" (/wh-control). Confere customer e BOXID depois."""
    b = box(unico)
    body = {"case_uq": b.get("case_uq"), "box_qty": int(box_qty if box_qty is not None else b.get("box_qty")),
            "packs_box": int(packs_box), "packs_units": int(b.get("up_x_pack") or 1), "user_uq": user_uq()}
    r = req("PUT", f"/api/inventory-entry/boxes/{unico}/wh-control", body)
    if not (r and r.get("success")): raise RuntimeError(f"wh-control falhou: {r}")
    audit("Edit", "flower_packing_box", unico, "Update Inventory Box FlexyMaxApp")
    return b, box(unico)

def find_product(text):
    r = req("GET", f"/api/inventory-entry/products?page=1&pageSize=20&search={text}")
    rows = r if isinstance(r, list) else (r or {}).get("data") or (r or {}).get("products") or []
    return [{k.lower(): v for k, v in x.items()} for x in rows]

def add_box(pack_uq, product_uq, case_uq, box_qty, packs_box, packs_units, price):
    """"Add Box" da tela web: caixa de estoque (sem customer, custo 0) direto no packing."""
    body = {"pack_uq": pack_uq, "product_uq": product_uq, "case_uq": case_uq, "box_qty": int(box_qty), "packs_box": int(packs_box),
            "packs_units": int(packs_units), "units_x_box": int(packs_box) * int(packs_units), "cut_point": 2,
            "price_x_u": round(float(price), 2), "user_uq": user_uq()}
    r = req("POST", "/api/inventory-entry/boxes", body)
    if not (r and r.get("success")): raise RuntimeError(f"Add Box falhou: {r}")
    audit("Insert", "flower_packing_box", r.get("unico") or pack_uq, "Insert Inventory Box FlexyMaxApp")
    return r

def edit_box(unico, cost=None, price=None, packs_box=None, fill_box_id=None):
    """Edita custo/venda/quantidade da caixa pela tela de packing do Flexymax, que GRAVA o customer junto
    (o "Edit Box" do fullpotos web zera o customer). Confere tudo na leitura de volta."""
    from . import flexy
    b = box(unico)
    if not b: raise RuntimeError(f"caixa {unico} não encontrada")
    st = lambda v: (v or "").strip() if isinstance(v, str) else v
    box_id = st(b.get("box_id")) or (fill_box_id or "")
    new_cost = float(cost if cost is not None else b.get("f_cost_x_u") or 0)
    new_price = float(price if price is not None else b.get("price_x_u") or 0)
    new_packs = int(packs_box if packs_box is not None else b.get("packs_box") or 1)
    flexy.packing_box_update(unico, b["box_pack_uq"], b["case_uq"], b["box_qty"], new_packs, b["up_x_pack"], new_cost, new_price,
                             st(b.get("customer_uq")), b.get("customer"), box_id=box_id, cporder=st(b.get("cporder_no")),
                             notes=st(b.get("inventory_notes")), freight=b.get("freight_cost") or 0, duties=b.get("duties_cost") or 0,
                             handling=b.get("handling_cost") or 0, broker=b.get("broker_cost") or 0, other=b.get("charge_cost") or 0)
    a = box(unico)
    for k in ("customer", "customer_uq", "box_qty", "box_pack_uq"):
        if a.get(k) != b.get(k): raise RuntimeError(f"CONFERÊNCIA: {k} mudou ({b.get(k)} → {a.get(k)}) na caixa {unico}")
    if abs(float(a.get("f_cost_x_u") or 0) - round(new_cost, 4)) > 0.001 or abs(float(a.get("price_x_u") or 0) - round(new_price, 2)) > 0.005 \
            or int(a.get("packs_box") or 0) != new_packs:
        raise RuntimeError(f"CONFERÊNCIA: custo/venda/quantidade não gravaram na caixa {unico}")
    return b, a
