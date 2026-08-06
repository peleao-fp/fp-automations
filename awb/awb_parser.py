#!/usr/bin/env python3
"""
Parser de invoices de frete / customs / handling para lancamento por AWB no Flexymax.

Uso:
    python3 awb_parser.py arquivo.pdf [arquivo2.pdf ...]
    python3 awb_parser.py --json arquivo.pdf     # saida JSON pura

Fornecedores suportados:
    CAL_AIR        Cal Air Cargo / Cal Air Forwarding
    MAS_CUSTOMS    M.A.S. Customs Broker, Inc
    NEW_TRANSPORT  New Transport S.A. (debit notes: ARANCEL / FLETE AEREO)
    UPS_AIR_CARGO  UPS Air Cargo Billing Statement
    KM_HANDLING    K&M Handling, LLC
"""

import sys
import json
import re
import os
from datetime import datetime

import pdfplumber


# ----------------------------------------------------------------------------
# Utilitarios
# ----------------------------------------------------------------------------

MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10,
    'november': 11, 'december': 12,
}


def to_num(s):
    """'$1,234.56' -> 1234.56"""
    if s is None:
        return 0.0
    s = str(s).replace('$', '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def norm_date(s):
    """Normaliza varios formatos para YYYY-MM-DD. Retorna None se nao reconhecer."""
    if not s:
        return None
    s = s.strip()

    # 07/24/2026  ou  07/31/26
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{2,4})$', s)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        return f'{y:04d}-{mo:02d}-{d:02d}'

    # 2026-07-24
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', s)
    if m:
        return s

    # 2-Aug-2026
    m = re.match(r'^(\d{1,2})-([A-Za-z]{3,})-(\d{4})$', s)
    if m:
        d, mon, y = int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
        if mon in MONTHS:
            return f'{y:04d}-{MONTHS[mon]:02d}-{d:02d}'

    # July 27th, 2026
    m = re.match(r'^([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,\s*(\d{4})$', s)
    if m:
        mon, d, y = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        if mon in MONTHS:
            return f'{y:04d}-{MONTHS[mon]:02d}-{d:02d}'

    return None


def extract_text(path):
    """Extrai texto de todas as paginas. Retorna (texto, n_paginas)."""
    parts = []
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        for page in pdf.pages:
            parts.append(page.extract_text() or '')
    return '\n'.join(parts), n


# ----------------------------------------------------------------------------
# Deteccao de fornecedor
# ----------------------------------------------------------------------------

def detect_vendor(text):
    t = text.upper()
    if 'CAL AIR' in t:
        return 'CAL_AIR'
    if 'M.A.S. CUSTOMS BROKER' in t or 'MAS CUSTOMS BROKER' in t:
        return 'MAS_CUSTOMS'
    if 'NEW TRANSPORT' in t and 'DEBIT NOTE' in t:
        return 'NEW_TRANSPORT'
    if 'AIR CARGO BILLING STATEMENT' in t and 'UPS' in t:
        return 'UPS_AIR_CARGO'
    if 'K&M HANDLING' in t and 'AWB NO.' in t:
        return 'KM_HANDLING'
    if "K'S REFRIGERATED TRANSPORT" in t:
        return 'KS_REFRIGERATED'
    if 'MIA FLORAL LOGISTIC' in t:
        return 'MIA_FLORAL'
    if 'SAFTEC LOGISTICS' in t:
        return 'SAFTEC'
    if 'UPS SCS' in t and 'AIR WAYBILL' in t:
        return 'UPS_SCS_ECUADOR'
    return None


# ----------------------------------------------------------------------------
# Parsers por fornecedor
# ----------------------------------------------------------------------------

def parse_cal_air(text):
    """Cal Air Cargo — invoice de frete."""
    out = {'vendor': 'CAL_AIR', 'vendor_display': 'Cal Air Cargo'}

    m = re.search(r'Invoice No:\s*([\w\-]+)', text)
    out['invoice_no'] = m.group(1) if m else None

    m = re.search(r'Invoice Date:\s*([\d/]+)', text)
    out['invoice_date'] = norm_date(m.group(1)) if m else None

    m = re.search(r'AWB:\s*(\S+)', text)
    if not m:
        m = re.search(r'Customer AWB:\s*(\S+)', text)
    out['awb'] = m.group(1) if m else None

    # Linhas de cobranca: ** CODIGO  DESCRICAO ... $unit $ext
    charges = []
    for line in text.split('\n'):
        m = re.match(r'^\*\*\s*(\S+)\s+(.+?)\s+(?:LBS|FEE|EA)\s+[\d\s]+\$[\d,\.]+\s+\$([\d,\.]+)\s*$',
                     line.strip())
        if m:
            charges.append({
                'code': m.group(1),
                'description': m.group(2).strip(),
                'amount': to_num(m.group(3)),
            })
    out['charges'] = charges

    m = re.search(r'Total:\s*\$([\d,\.]+)', text)
    out['total'] = to_num(m.group(1)) if m else None
    return out


def parse_mas_customs(text):
    """M.A.S. Customs Broker — invoice de duties / entry fee."""
    out = {'vendor': 'MAS_CUSTOMS', 'vendor_display': 'M.A.S. Customs Broker, Inc'}

    m = re.search(r'INVOICE NO\.\s*INVOICE DATE', text)
    # numero e data aparecem juntos numa linha proxima: "0972606 08/04/26"
    m = re.search(r'^\s*(\d{6,8})\s+(\d{2}/\d{2}/\d{2,4})\s*$', text, re.M)
    if m:
        out['invoice_no'] = m.group(1)
        out['invoice_date'] = norm_date(m.group(2))
    else:
        out['invoice_no'] = None
        out['invoice_date'] = None

    # AWB master (o que vai pro sistema) e house
    m = re.search(r'Master:\s*([\w\-]+),\s*House:\s*([\w\-]+)', text)
    if m:
        out['awb'] = m.group(1)
        out['awb_house'] = m.group(2)
    else:
        m = re.search(r'CLIENT REF\. NO\.\s*\n\s*(\S+)', text)
        out['awb'] = m.group(1) if m else None

    m = re.search(r'Forwarder:\s*(.+)', text)
    out['forwarder'] = m.group(1).strip() if m else None

    m = re.search(r'ENTRY NO\.\s*DATE OF ENTRY\s*\n[\d/]+\s+\d+\s+(\S+)', text)
    out['entry_no'] = m.group(1) if m else None

    charges = []
    m = re.search(r'^Entry Service Fee\s+([\d,\.]+)\s*$', text, re.M)
    if m:
        charges.append({'code': 'ENTRY_FEE', 'description': 'Entry Service Fee',
                        'amount': to_num(m.group(1))})
    m = re.search(r'^Duties, Taxes and Fees\s+([\d,\.]+)\s*$', text, re.M)
    if m:
        charges.append({'code': 'DUTIES', 'description': 'Duties, Taxes and Fees',
                        'amount': to_num(m.group(1))})
    out['charges'] = charges

    m = re.search(r'Balance \(USD\):\s*([\d,\.]+)', text)
    out['total'] = to_num(m.group(1)) if m else None
    return out


def parse_new_transport(text):
    """New Transport S.A. — debit note (ARANCEL USA ou FLETE AEREO)."""
    out = {'vendor': 'NEW_TRANSPORT', 'vendor_display': 'New Transport S.A.'}

    # "DEBIT NOTE Nro RP 0001-00009294"
    m = re.search(r'DEBIT NOTE Nro\s+(.+?)\s*$', text, re.M)
    out['invoice_no'] = re.sub(r'\s+', ' ', m.group(1).strip()) if m else None

    m = re.search(r'ISSUE DATE:\s*(.+)', text)
    out['invoice_date'] = norm_date(m.group(1).strip()) if m else None

    # "AWB/HAWB: 36999758304 - 00000079816"  ou com "/"
    m = re.search(r'AWB/HAWB:\s*(\S+)\s*[-/]\s*(\S+)', text)
    if m:
        out['awb'] = m.group(1)
        out['awb_house'] = m.group(2)
    else:
        out['awb'] = None

    m = re.search(r'FECHA (?:DE )?VUELO:\s*([\d/]+)', text)
    if m:
        d = m.group(1)  # DD/MM/YYYY
        p = d.split('/')
        out['flight_date'] = f'{p[2]}-{p[1]}-{p[0]}' if len(p) == 3 else None

    # Item 1 e sempre a cobranca real
    charges = []
    m = re.search(r'^1\s+1\s+(.+?)\s+([\d,\.]+)\s+[\d,\.]+\s+([\d,\.]+)\s*$', text, re.M)
    if m:
        desc = m.group(1).strip()
        code = 'DUTY' if 'ARANCEL' in desc.upper() else (
            'FREIGHT' if 'FLETE' in desc.upper() else 'OTHER')
        charges.append({'code': code, 'description': desc, 'amount': to_num(m.group(3))})
    out['charges'] = charges

    m = re.search(r'^\$([\d,\.]+)\s*$', text, re.M)
    out['total'] = to_num(m.group(1)) if m else None
    return out


def parse_ups(text):
    """UPS Air Cargo — usa a linha estruturada I:SINVDetail quando disponivel."""
    out = {'vendor': 'UPS_AIR_CARGO', 'vendor_display': 'UPS Air Cargo'}

    # Linha oculta estruturada:
    # I:SINVDetail,<docid>,<statement>,<date>,<acct>,<acct>,<awb>,,,,ORIG,...
    m = re.search(r'I:SINVDetail,([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),([^,]*),', text)
    if m:
        out['invoice_no'] = m.group(2)
        out['invoice_date'] = norm_date(m.group(3))
        out['awb'] = m.group(6)
        out['account_no'] = m.group(4)
        out['_source'] = 'structured_line'
    else:
        m = re.search(r'STATEMENT NBR\s*:\s*(\d+)', text)
        out['invoice_no'] = m.group(1) if m else None
        out['awb'] = None
        out['invoice_date'] = None
        out['_source'] = 'fallback_regex'

    # Linha de detalhe: AWB DATA ROTA PESO U CHARGES FUEL OTHER TOTAL
    charges = []
    m = re.search(
        r'^(\d{8,})\s+([\d]{1,2}-[A-Za-z]{3}-\d{4})\s+(\S+)\s+([\d,\.]+)\s+(\w+)\s+'
        r'([\d,\.]+)\s+([\d,\.]+)\s+([\d,\.]+)\s+([\d,\.]+)\s*$', text, re.M)
    if m:
        if not out.get('awb'):
            out['awb'] = m.group(1)
        if not out.get('invoice_date'):
            out['invoice_date'] = norm_date(m.group(2))
        out['route'] = m.group(3)
        out['chargeable_weight'] = to_num(m.group(4))
        out['weight_unit'] = m.group(5)
        charges.append({'code': 'FREIGHT', 'description': 'Charges', 'amount': to_num(m.group(6))})
        charges.append({'code': 'FUEL', 'description': 'Fuel', 'amount': to_num(m.group(7))})
        charges.append({'code': 'OTHER', 'description': 'Other', 'amount': to_num(m.group(8))})
    out['charges'] = charges

    m = re.search(r'TOTAL DUE\s*:\s*([\d,\.]+)', text)
    out['total'] = to_num(m.group(1)) if m else None
    return out


def parse_km_handling(text):
    """K&M Handling — invoice de duties (AWB com sufixo D) / processing fee."""
    out = {'vendor': 'KM_HANDLING', 'vendor_display': 'K&M Handling, LLC'}

    m = re.search(r'^\s*(\d{1,2}/\d{1,2}/\d{4})\s+(\d{5,7})\s*$', text, re.M)
    if m:
        out['invoice_date'] = norm_date(m.group(1))
        out['invoice_no'] = m.group(2)
    else:
        out['invoice_date'] = None
        out['invoice_no'] = None

    # AWB vem sozinho numa linha logo apos o cabecalho, pode ter sufixo "D"
    m = re.search(r'AWB No\.\s+Terms.*\n\s*(\S+)\s+Net', text)
    if m:
        out['awb'] = m.group(1)
    else:
        m = re.search(r'^\s*(\d{8,}[A-Z]?)\s+Net\s', text, re.M)
        out['awb'] = m.group(1) if m else None

    if out.get('awb'):
        out['awb_has_d_suffix'] = out['awb'].upper().endswith('D')

    charges = []
    for line, code in [
        (r'^DUTIES, TAXES AND FEES\s+([\d,\.]+)', 'DUTIES'),
        (r'^PROCESSING FEE\s+([\d,\.]+)', 'PROCESSING_FEE'),
    ]:
        m = re.search(line, text, re.M)
        if m:
            desc = 'Duties, Taxes and Fees' if code == 'DUTIES' else 'Processing Fee'
            charges.append({'code': code, 'description': desc, 'amount': to_num(m.group(1))})
    out['charges'] = charges

    m = re.search(r'\$([\d,\.]+)\s*$', text.strip(), re.M)
    m2 = re.search(r'Total\s*\n?\s*\$([\d,\.]+)', text)
    out['total'] = to_num(m2.group(1)) if m2 else (to_num(m.group(1)) if m else None)
    return out


def parse_ks_refrigerated(text):
    """K's Refrigerated Transport — invoice de frete terrestre refrigerado."""
    out = {'vendor': 'KS_REFRIGERATED', 'vendor_display': "K's Refrigerated Transport, LLC"}

    m = re.search(r'^Date\s+(\d{1,2}/\d{1,2}/\d{4})\s*$', text, re.M)
    out['invoice_date'] = norm_date(m.group(1)) if m else None

    m = re.search(r'^Invoice #\s*(\d+)\s*$', text, re.M)
    out['invoice_no'] = m.group(1) if m else None

    # O AWB fica sozinho na coluna "Airbill #" da primeira linha (ex: DL24467310).
    # As linhas seguintes trazem NOMES DE SHIPPER nessa mesma coluna, nao AWBs.
    m = re.search(r'^\d{1,2}/\d{1,2}/\d{4}\s+([A-Z]{0,3}\d{7,})\s*$', text, re.M)
    out['awb'] = m.group(1) if m else None

    charges = []
    m = re.search(r'^SUBTOTAL\s+\d+\s+([\d,\.]+)\s*$', text, re.M)
    if m:
        charges.append({'code': 'FREIGHT', 'description': 'Subtotal frete',
                        'amount': to_num(m.group(1))})
    for pat, code, desc in [
        (r'^FSC\s+Fuel Surcharge\s+[\d\.]+%\s+([\d,\.]+)', 'FUEL', 'Fuel Surcharge'),
        (r'^CF\s+Consol Fee\s+\d+\s+[\d,\.]+\s+([\d,\.]+)', 'CONSOL_FEE', 'Consol Fee'),
        (r'^AWB\s+K\'s Airway Bill\s+\d+\s+[\d,\.]+\s+([\d,\.]+)', 'AWB_FEE', "K's Airway Bill"),
    ]:
        m = re.search(pat, text, re.M)
        if m:
            charges.append({'code': code, 'description': desc, 'amount': to_num(m.group(1))})
    out['charges'] = charges

    m = re.search(r'Balance Due\s*\$([\d,\.]+)', text)
    if not m:
        m = re.search(r'^Total\s*\n\s*\$([\d,\.]+)', text, re.M)
    out['total'] = to_num(m.group(1)) if m else None
    return out


def parse_mia_floral(text):
    """MIA Floral Logistic Corp — invoice de frete."""
    out = {'vendor': 'MIA_FLORAL', 'vendor_display': 'MIA Floral Logistic Corp'}

    m = re.search(r'Invoice no\.:\s*(\S+)', text)
    out['invoice_no'] = m.group(1) if m else None

    m = re.search(r'Invoice date:\s*([\d/]+)', text)
    out['invoice_date'] = norm_date(m.group(1)) if m else None

    # "AWB: 992 01108656" — remove espacos internos
    m = re.search(r'AWB:\s*([\d\s\-]+?)(?:\s{2,}|$)', text, re.M)
    out['awb'] = re.sub(r'[\s\-]', '', m.group(1)) if m else None

    charges = []
    for line in text.split('\n'):
        m = re.match(r'^(\d+)\.\s+(.+?)\s+(?:\S+\s+)?(\d+)\s+\$([\d,\.]+)\s+\$([\d,\.]+)\s*$',
                     line.strip())
        if m:
            charges.append({'code': 'FREIGHT', 'description': m.group(2).strip(),
                            'amount': to_num(m.group(5))})
    out['charges'] = charges

    m = re.search(r'Total\s*\$([\d,\.]+)', text)
    out['total'] = to_num(m.group(1)) if m else None
    return out


def parse_ups_scs(text):
    """UPS SCS Ecuador — o documento e o proprio Air Waybill; lanca o Total Collect."""
    out = {'vendor': 'UPS_SCS_ECUADOR', 'vendor_display': 'UPS SCS ECUADOR SAS'}

    # AWB: numeros do routing "QUITO/406UIO03633954" -> 40603633954
    m = re.search(r'\b(\d{3})UIO(\d{8})\b', text)
    if m:
        out['awb'] = m.group(1) + m.group(2)
    else:
        m = re.search(r'/(\d{3})[A-Z]{3}(\d{8})\b', text)
        out['awb'] = (m.group(1) + m.group(2)) if m else None

    m = re.search(r'HAWB NO\.\s*\n?.*?(\d{8,})', text)
    out['awb_house'] = m.group(1) if m else None

    # invoice_no: nao ha numero de invoice; usa o HAWB como referencia
    out['invoice_no'] = out.get('awb_house')

    # Data de execucao: "05-AUG-2026"
    m = re.search(r'(\d{1,2}-[A-Z]{3}-\d{4})', text)
    out['invoice_date'] = norm_date(m.group(1).title()) if m else None

    # Total Collect e o maior "Total Collect" — pega o valor apos "Total Collect"
    charges = []
    m = re.search(r'Total Collect[\s\S]{0,80}?([\d,]+\.\d{2})', text)
    if m:
        total = to_num(m.group(1))
        charges.append({'code': 'FREIGHT', 'description': 'Total Collect (AWB)',
                        'amount': total})
        out['total'] = total
    else:
        out['total'] = None
    out['charges'] = charges
    return out


def parse_saftec(text):
    """SAFTEC Logistics LLC — invoice de frete aereo Equador."""
    out = {'vendor': 'SAFTEC', 'vendor_display': 'SAFTEC LOGISTICS LLC'}

    m = re.search(r'Invoice Number:\s*\n?\s*(\S+)', text)
    out['invoice_no'] = m.group(1) if m else None

    # "AWB Date" seguido da data na linha de baixo (ou proxima)
    m = re.search(r'AWB Date\s*\n(?:.*\n)?(\d{4}-\d{2}-\d{2})', text)
    out['invoice_date'] = norm_date(m.group(1)) if m else None

    # AWB no formato 145-9999-5895 — normaliza removendo hifens
    m = re.search(r'\b(\d{3}-\d{4}-\d{4})\b', text)
    if m:
        out['awb_printed'] = m.group(1)
        out['awb'] = m.group(1).replace('-', '')
    else:
        out['awb'] = None

    charges = []
    for line in text.split('\n'):
        m = re.match(r'^([\d,\.]+)\s+\$\s*([\d,\.]+)\s+(.+?)\s+\$\s*([\d,\.]+)\s*$',
                     line.strip())
        if m:
            desc = m.group(3).strip()
            code = 'FREIGHT' if 'FREIGHT' in desc.upper() else desc.upper().replace(' ', '_')[:16]
            charges.append({'code': code, 'description': desc, 'amount': to_num(m.group(4))})
    out['charges'] = charges

    m = re.search(r'TOTAL\s+\$\s*([\d,\.]+)', text)
    out['total'] = to_num(m.group(1)) if m else None
    return out


PARSERS = {
    'CAL_AIR': parse_cal_air,
    'MAS_CUSTOMS': parse_mas_customs,
    'NEW_TRANSPORT': parse_new_transport,
    'UPS_AIR_CARGO': parse_ups,
    'KM_HANDLING': parse_km_handling,
    'KS_REFRIGERATED': parse_ks_refrigerated,
    'MIA_FLORAL': parse_mia_floral,
    'SAFTEC': parse_saftec,
    'UPS_SCS_ECUADOR': parse_ups_scs,
}


# ----------------------------------------------------------------------------
# Orquestracao
# ----------------------------------------------------------------------------

def parse_pdf(path):
    text, npages = extract_text(path)
    result = {
        'source_file': os.path.basename(path),
        'pages': npages,
        'text_chars': len(text.strip()),
    }

    if len(text.strip()) == 0:
        result['status'] = 'ERROR'
        result['error'] = 'PDF sem camada de texto (escaneado) — requer OCR'
        return result

    vendor = detect_vendor(text)
    if not vendor:
        result['status'] = 'ERROR'
        result['error'] = 'Fornecedor nao reconhecido'
        return result

    try:
        data = PARSERS[vendor](text)
    except Exception as e:
        result['status'] = 'ERROR'
        result['error'] = f'Falha no parser {vendor}: {e}'
        return result

    result.update(data)
    result['currency'] = 'USD'

    # Validacoes
    warnings = []
    for field in ('invoice_no', 'invoice_date', 'awb', 'total'):
        if not result.get(field):
            warnings.append(f'Campo obrigatorio ausente: {field}')

    if result.get('charges'):
        soma = round(sum(c['amount'] for c in result['charges']), 2)
        if result.get('total') is not None and abs(soma - result['total']) > 0.01:
            warnings.append(
                f'Soma das cobrancas ({soma:.2f}) diferente do total ({result["total"]:.2f})')
    else:
        warnings.append('Nenhuma linha de cobranca extraida')

    result['warnings'] = warnings
    result['status'] = 'OK' if not warnings else 'WARN'
    return result


def main():
    args = [a for a in sys.argv[1:] if a != '--json']
    as_json = '--json' in sys.argv

    if not args:
        print(__doc__)
        sys.exit(1)

    results = [parse_pdf(p) for p in args]

    if as_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    for r in results:
        icon = {'OK': '[OK]  ', 'WARN': '[WARN]', 'ERROR': '[ERRO]'}[r['status']]
        print('=' * 72)
        print(f'{icon} {r["source_file"]}')
        print('=' * 72)
        if r['status'] == 'ERROR':
            print(f'  {r["error"]}')
            print()
            continue
        print(f'  Fornecedor : {r.get("vendor_display")}  ({r.get("vendor")})')
        print(f'  Invoice    : {r.get("invoice_no")}   Data: {r.get("invoice_date")}')
        print(f'  AWB        : {r.get("awb")}'
              + (f'   (House: {r.get("awb_house")})' if r.get('awb_house') else ''))
        if r.get('awb_has_d_suffix'):
            print(f'               ^ sufixo "D" detectado')
        print(f'  Cobrancas  :')
        for c in r.get('charges', []):
            print(f'      {c["code"]:<16} {c["description"]:<32} $ {c["amount"]:>9,.2f}')
        print(f'  {"TOTAL":<10} : $ {r.get("total", 0):,.2f}')
        for w in r.get('warnings', []):
            print(f'  ! {w}')
        print()


if __name__ == '__main__':
    main()
