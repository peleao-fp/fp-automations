"""
Flexymax (Appsmith) — leitura e edição de prebooks. Mesmas ações que index.js / flexymax.js usam.

Linha "anulada" (void=True) continua aparecendo na leitura: é como o Flexymax apaga algumas linhas.
"""
import json
import time

import requests

BASE = "https://app.flexymax.com/api/v1/actions/execute"
ANON = "ba68aa44-49dc-4dbf-8145-864bb24cd52d"
SALESMAN_UQ = "C9145113"
A = {
    "read_header": "659f60bcb185274a675b81e1",
    "read_lines":  "659f60bcb185274a675b81d8",
    "insert_line": "659f60bcb185274a675b81f0",
    "delete_line": "659f60bcb185274a675b81f7",
    "delete_pb":   "659f60bcb185274a675b8205",
}

def call(action_id, param_map, values, tries=3):
    """Executa uma ação do Appsmith. param_map: {campo: 'k0'}, values: {'k0': valor}."""
    files = {
        "executeActionDTO": (None, json.dumps({"actionId": action_id, "viewMode": True,
            "paramProperties": {k: {"datatype": "string", "blobIdentifiers": []} for k in values},
            "analyticsProperties": {"isUserInitiated": False}})),
        "parameterMap": (None, json.dumps(param_map)),
    }
    for k, v in values.items(): files[k] = ("blob", "" if v is None else str(v), "text/plain")
    headers = {"accept": "application/json", "x-anonymous-user-id": ANON, "x-appsmith-environmentid": "unused_env",
               "x-appsmith-version": "v1.78", "origin": "https://app.flexymax.com"}
    for t in range(tries):
        try:
            r = requests.post(BASE, files=files, headers=headers, timeout=60)
            if r.status_code < 500:
                d = r.json()
                if not (d.get("responseMeta") or {}).get("success"): raise RuntimeError(f"Flexymax: {json.dumps(d)[:300]}")
                return (d.get("data") or {}).get("body") or []
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = str(e)
        time.sleep(3 * (t + 1))
    raise RuntimeError(f"Flexymax falhou ({err})")

def read_header(pb_uq):
    rows = call(A["read_header"], {"appsmith.store.lcPrebook_Uq": "k0"}, {"k0": pb_uq})
    return rows[0] if rows else None

def read_lines(pb_uq, include_void=False):
    rows = call(A["read_lines"], {"appsmith.store.lcPrebook_Uq": "k0"}, {"k0": pb_uq})
    return rows if include_void else [l for l in rows if not l.get("void")]

def delete_line(line_uq):
    return call(A["delete_line"], {"tblPrebookDetails.selectedRow.unico": "k0",
                                   "appsmith.store.loSalesRepInfo[0].unico": "k1"}, {"k0": line_uq, "k1": SALESMAN_UQ})

def delete_prebook(pb_uq):
    return call(A["delete_pb"], {"appsmith.store.lcPrebook_Uq": "k0"}, {"k0": pb_uq})

def insert_line(pb_uq, product_uq, case_uq, qty, packs_x_case, up_x_pack, sales_price, grower_uq=""):
    """Insere uma linha no PB (mesmo mapeamento do flexymax.js insertPrebookLine)."""
    pm = {
        "JSONFormAddPrebook.formData.up_x_pack": "k0", "''": "k1",
        "(JSONFormAddPrebook.formData?.customGPM || 0)": "k2", "(JSONFormAddPrebook.formData?.retail_price || 0)": "k3",
        "dsPrebookHeader.data[0].unico": "k4", "JSONFormAddPrebook.formData.up_x_case": "k5",
        "(JSONFormAddPrebook.formData?.additional_notes || '')": "k6", "JSONFormAddPrebook.formData.sales_price": "k7",
        "JSONFormAddPrebook.formData.customBoxQty": "k8", "JSONFormAddPrebook.sourceData.unico": "k9",
        "JSONFormAddPrebook.formData.customGrower_uq": "k10", "(JSONFormAddPrebook.formData?.upc || '')": "k11",
        "(JSONFormAddPrebook.formData?.customFood || '' )": "k12", "(JSONFormAddPrebook.formData?.food || false)": "k13",
        "(JSONFormAddPrebook.formData?.upc_notes || '')": "k14", "appsmith.store.loSalesRepInfo[0].unico": "k15",
        "JSONFormAddPrebook.formData.customUxCase": "k16", "JSONFormAddPrebook.formData.instructions": "k17",
        "(JSONFormAddPrebook.formData?.boxcode || '')": "k18", "(JSONFormAddPrebook.formData?.upc_text || '')": "k19",
        "(JSONFormAddPrebook.formData?.color_breakdown || '')": "k20", "JSONFormAddPrebook.formData.case_uq": "k21",
        "(JSONFormAddPrebook.formData?.boxcode2 || '')": "k22", "(JSONFormAddPrebook.formData?.customCutPoint || 0 )": "k23",
    }
    v = {"k0": up_x_pack, "k1": "", "k2": 0, "k3": 0, "k4": pb_uq, "k5": packs_x_case, "k6": "", "k7": sales_price,
         "k8": qty, "k9": product_uq, "k10": grower_uq, "k11": "", "k12": "", "k13": "false", "k14": "", "k15": SALESMAN_UQ,
         "k16": packs_x_case * up_x_pack, "k17": "", "k18": "", "k19": "", "k20": "", "k21": case_uq, "k22": "", "k23": 0}
    rows = call(A["insert_line"], pm, v)
    if not rows or rows[0].get("error"): raise RuntimeError(f"insert falhou: {rows}")
    return rows[0]

# ── Packing (tela de packing do app Flexymax) — edita a caixa MANTENDO o customer ─────────────────────────
A["packing_box_update"] = "6789f2f079bb654e94f63864"

def packing_box_update(box_unico, product_uq, case_uq, box_qty, packs_case, units_pack, cost_unit, sale_price,
                       customer_uq, customer_no, box_id="", cporder="", notes="", freight=0, duties=0, handling=0, broker=0, other=0):
    """Mesmo "Update Box" da tela de packing do Flexymax: grava quantidade, custo, venda e o CUSTOMER (código + número)."""
    pm = {
        "(FormPackingBoxUpdate.data?.InpuInsertFreight || 0)": "k0", "(FormPackingBoxUpdate.data?.InputBoxIdUpdate || '')": "k1",
        "(FormPackingBoxUpdate.data?.InputBoxNotesUpdate || '')": "k2", "(FormPackingBoxUpdate.data?.InputCaseDutiesUpdate || 0)": "k3",
        "(FormPackingBoxUpdate.data?.InputCaseHandlingUpdate || 0)": "k4", "(FormPackingBoxUpdate.data?.InputCaseInsertBrokerUpdate || 0)": "k5",
        "(FormPackingBoxUpdate.data?.InputCaseOtherCostsUpdate || 0)": "k6", "2": "k7",
        "FormPackingBoxUpdate.data.InputBoxQtyUpdate": "k8", "FormPackingBoxUpdate.data.InputCPOUpdate": "k9",
        "FormPackingBoxUpdate.data.InputPacksCaseUpdate": "k10", "FormPackingBoxUpdate.data.InputPriceUnitUpdate": "k11",
        "FormPackingBoxUpdate.data.InputSalePriceUpdate": "k12", "FormPackingBoxUpdate.data.InputUnitsCaseUpdate": "k13",
        "FormPackingBoxUpdate.data.InputUnitsPackUpdate": "k14", "SelectCasesListUpdate.selectedOptionValue": "k15",
        "SelectCustomers.selectedOptionLabel.substring(SelectCustomers.selectedOptionLabel.indexOf('-') + 1).trim();": "k16",
        "SelectCustomers.selectedOptionValue": "k17", "dsPackingBoxInfo.data[0].box_pack_uq": "k18", "dsPackingBoxInfo.data[0].unico": "k19",
    }
    v = {"k0": freight, "k1": box_id, "k2": notes, "k3": duties, "k4": handling, "k5": broker, "k6": other, "k7": 2,
         "k8": int(box_qty), "k9": cporder, "k10": int(packs_case), "k11": round(float(cost_unit), 4), "k12": round(float(sale_price), 2),
         "k13": int(packs_case) * int(units_pack), "k14": int(units_pack), "k15": case_uq, "k16": str(customer_no),
         "k17": customer_uq, "k18": product_uq, "k19": box_unico}
    return call(A["packing_box_update"], pm, v)
