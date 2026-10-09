"""
Compras (POs) na API de add-ons — criar a partir da linha do PB, confirmar, ajustar preço e notas.

Regras aprendidas na prática:
- O PO tem que ter o MESMO formato da linha do PB (packs por caixa × unidades por pack), senão o Flexymax recusa
  ("RESTRICTION: Check your qty on PO").
- O preço do PO é por pack: custo da unidade × unidades por pack. Em linha "1 pack × 12" o preço é o da caixa.
- Só compra o que falta na linha (qty_order − qty_porder): nunca duplica.
"""
import time

import requests

API = "https://full-pot-flexy-add-ons.vercel.app"
BUYER_UQ, SALESMAN = "C9145113", "HOLEX"
CASE_UQ = {"BX": "0BFA95DF", "QB": "BB58F6B1", "HB": "646F1272", "EB": "58DAC0D8", "TY": "BBBFD08E", "HA": "2D738E3E",
           "BUN": "4512792C", "UNIT": "8E4F15E3"}
WH_BY_NAME = {"MIAMI": "BUEB4005", "FT LAUDERDALE": "CAM27168", "NAPLES": "YBRT6967", "WEST PALM BEACH": "82G89770"}

def _req(method, path, payload=None, tries=4):
    for t in range(tries):
        try:
            r = requests.request(method, API + path, json=payload, timeout=60)
            if r.status_code == 404: return None
            if r.status_code < 500: return r.json()
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = str(e)
        time.sleep(3 * (t + 1))
    raise RuntimeError(f"API add-ons falhou em {path}: {err}")

def pos_by_date(ship_date):
    return (_req("GET", f"/api/purchase-orders?ship_date={ship_date}&grower_uq=%25&product_uq=%25") or {}).get("data", [])

def po_detail(unico):
    return ((_req("GET", f"/api/purchase-orders/{unico}") or {}).get("data")) or None

def create_from_pb_line(line, pb_uq, grower_uq, wphysical_uq, ship_date, unit_cost, qty=None, details="."):
    """Cria e confirma o PO de uma linha do PB (formato do PB, preço por pack). Devolve o PO lido de volta."""
    qty = int(qty if qty is not None else line["qty_order"])
    packs, upx = int(line["packs_x_case"]), int(line["up_x_pack"])
    payload = {
        "pbook_d_uq": line["unico"], "pbook_uq": pb_uq, "grower_uq": grower_uq, "product_uq": line["product_uq"],
        "case_uq": line["case_uq"], "qty_porder": qty, "bunches_case": packs, "up_x_pack": upx,
        "po_price": round(float(unit_cost) * upx, 4), "charges": 0, "broker": 0, "handling": 0, "freight": 0, "duties": 0,
        "ship_date": ship_date, "food": False, "pccode": (line.get("description") or "")[:20].strip(),
        "details": (details or ".")[:250], "salesman": SALESMAN, "buyer_uq": BUYER_UQ, "wphysical_uq": wphysical_uq,
        "purchase_type": "S", "farm_item": ".", "pickup_order": False, "seasonprice": 0,
    }
    r = _req("POST", "/api/purchase-orders", payload)
    if not r or r.get("error") is not False: raise RuntimeError((r or {}).get("message") or "criação do PO falhou")
    unico = r["unico"]
    update(unico, confirm=True)
    po = po_detail(unico)
    if not po: raise RuntimeError(f"PO {unico} não aparece depois de criado")
    return po

def update(unico, unit_price=None, confirm=False, details=None, qty=None):
    """Altera um PO mantendo tudo o mais igual. unit_price = custo da UNIDADE (converte para pack)."""
    d = po_detail(unico)
    if not d: raise RuntimeError(f"PO {unico} não encontrado")
    case_sh = (d.get("case_sh") or "").strip(); wh = WH_BY_NAME.get((d.get("wp_name") or "").strip().upper())
    if case_sh not in CASE_UQ or not wh: raise RuntimeError(f"Caixa '{case_sh}' ou warehouse '{d.get('wp_name')}' desconhecido")
    upx = int(d.get("up_x_pack", 1)); q = int(qty if qty is not None else d.get("qty_porder", 0))
    payload = {
        "grower_uq": d["grower_uq"], "product_uq": d["product_uq"], "case_uq": CASE_UQ[case_sh],
        "qty_porder": q, "qty_confirm": q if confirm else min(int(d.get("qty_confirm", 0)), q),
        "bunches_case": int(d.get("bunches_case", 1)), "up_x_pack": upx,
        "po_price": round(float(unit_price) * upx, 4) if unit_price is not None else float(d.get("po_price") or 0),
        "charges": 0, "broker": 0, "handling": 0, "freight": 0, "duties": 0,
        "ship_date": (d.get("ship_date") or "")[:10], "food": False, "pccode": (d.get("description") or "")[:20].strip(),
        "details": (details if details is not None else (d.get("details") or "").strip() or ".")[:250],
        "salesman": SALESMAN, "wphysical_uq": wh, "buyer_uq": BUYER_UQ, "farm_item": ".", "purchase_type": "S",
    }
    r = _req("PUT", f"/api/purchase-orders/{unico}", payload)
    if not r or r.get("error") is not False: raise RuntimeError((r or {}).get("message") or "atualização do PO falhou")
    return po_detail(unico)
