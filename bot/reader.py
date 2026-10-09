"""
Leitor de e-mails de fornecedor de hardgoods com o Claude: resposta ao pedido ou invoice → dados estruturados.

A IA só LÊ e devolve JSON validado (saída estruturada). Quem decide e grava é o código, com as travas de sempre.
Variável de ambiente: ANTHROPIC_API_KEY.
"""
import base64, json, os

import anthropic

MODEL = "claude-opus-5-5"

LINE = {
    "type": "object", "additionalProperties": False,
    "required": ["code", "description", "qty_ordered", "qty_shipped", "unit", "price", "extension", "status"],
    "properties": {
        "code": {"type": "string", "description": "Item number exactly as printed (e.g. 4049-12-09, MG66, 31-01610)"},
        "description": {"type": "string"},
        "qty_ordered": {"type": "number", "description": "0 when not printed"},
        "qty_shipped": {"type": "number", "description": "Quantity actually shipped/invoiced; for a reply, the quantity confirmed (0 if not available)"},
        "unit": {"type": "string", "description": "Unit of measure as printed: CS, EA, PK, BX…"},
        "price": {"type": "number", "description": "Price per unit of measure; 0 when not printed"},
        "extension": {"type": "number", "description": "Line total as printed; 0 when not printed"},
        "status": {"type": "string", "enum": ["shipped", "partial", "backorder", "out_of_stock", "discontinued", "cannot_order", "substituted", "other"]},
    },
}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["supplier", "doc_type", "store", "sales_order", "invoice_number", "invoice_date", "lines",
                 "subtotal", "freight", "other_charges", "total", "total_quantity", "notes"],
    "properties": {
        "supplier": {"type": "string"},
        "doc_type": {"type": "string", "enum": ["reply", "invoice", "order_confirmation", "other"],
                     "description": "reply = text answer about availability; invoice = billing document"},
        "store": {"type": "string", "enum": ["PMP", "WPB", "NPL", "MCO", "MIA", "unknown"],
                  "description": "Full Pot store the document refers to (Customer PO / ship-to / text). PMP = Pompano/Ft Lauderdale"},
        "sales_order": {"type": "string", "description": "Supplier sales order number, e.g. SO-454843; empty if none"},
        "invoice_number": {"type": "string", "description": "Empty if not an invoice"},
        "invoice_date": {"type": "string", "description": "YYYY-MM-DD or empty"},
        "lines": {"type": "array", "items": LINE},
        "subtotal": {"type": "number", "description": "Merchandise subtotal as printed (0 if none)"},
        "freight": {"type": "number", "description": "Freight/delivery/shipping charges (0 if none)"},
        "other_charges": {"type": "number"},
        "total": {"type": "number", "description": "Invoice total / net amount as printed (0 if none)"},
        "total_quantity": {"type": "number", "description": "'Total Quantities' or carton count as printed; 0 if none"},
        "notes": {"type": "string", "description": "Anything relevant that does not fit above (substitutions, comments)"},
    },
}
WRAPPER = {"type": "object", "additionalProperties": False, "required": ["documents"],
           "properties": {"documents": {"type": "array", "items": SCHEMA,
                                        "description": "One entry per invoice / per store document found (a PDF may hold several invoices)"}}}
SYSTEM = (
    "You read emails and attachments sent by Full Pot's hardgoods suppliers (Syndicate Sales, WD Imports, Smithers-Oasis, "
    "Giftwares and others). Extract exactly what is printed: never invent items, quantities or prices, and keep item codes "
    "exactly as written. One email may cover several stores; when it does, return the data of the document you are given. "
    "A line whose description sits on the line above its numbers is still one line. Include every line, even with zero price."
)

def read_document(subject, sender, body_text, attachments):
    """attachments: [(filename, bytes)]. Returns a LIST of documents (one per invoice/store found)."""
    client = anthropic.Anthropic()
    content = []
    for name, data in attachments:
        if name.lower().endswith(".pdf"):
            content.append({"type": "document", "title": name,
                            "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": f"From: {sender}\nSubject: {subject}\n\n{body_text or ''}\n\n"
                                             "Extract every document: one entry per invoice (a PDF may contain several invoices, "
                                             "one per store). For a text reply, one entry per store mentioned."})
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=16000, system=SYSTEM, messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": WRAPPER}},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"O modelo recusou a leitura: {getattr(resp, 'stop_details', None)}")
    text = next(b.text for b in resp.content if b.type == "text")
    docs = json.loads(text)["documents"]
    for d in docs: d["_usage"] = {"input": resp.usage.input_tokens, "output": resp.usage.output_tokens, "model": resp.model, "docs": len(docs)}
    return docs

def check_totals(d):
    """Trava: soma das linhas tem que bater com o subtotal impresso (e caixas com o total de quantidades)."""
    s = round(sum(float(l["extension"] or 0) for l in d["lines"]), 2)
    q = round(sum(float(l["qty_shipped"] or 0) for l in d["lines"]), 2)
    problems = []
    if d["subtotal"] and abs(s - float(d["subtotal"])) > 0.02: problems.append(f"linhas ${s:,.2f} ≠ subtotal ${float(d['subtotal']):,.2f}")
    if d["total_quantity"] and abs(q - float(d["total_quantity"])) > 0.01: problems.append(f"quantidade {q:g} ≠ total impresso {float(d['total_quantity']):g}")
    return problems
