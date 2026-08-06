#!/usr/bin/env python3
"""
Orquestrador do lancamento de charges por AWB no Flexymax.

Fluxo:
  1. Recebe o caminho de um arquivo (.pdf ou .eml)
  2. Faz o parse (awb_parser / champion_eml)
  3. Aplica as regras de negocio (vendor UQ + charge type UQ)
  4. Verifica duplicidade no Gist (awb_charges_log.json)
  5. POST /api/awbs/charges no Flexymax + registros de auditoria
  6. Atualiza o Gist (log de lancados + awb_results.json para o Power Automate)

Uso:
  python3 src/main.py --file caminho/arquivo.pdf [--dry-run]

Env:
  GH_TOKEN   token do GitHub (secrets) — para ler/escrever o Gist
  GIST_ID    id do gist de resultados (default: 08dec31e87f93d907ad03c4f68bb547d)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from awb_parser import parse_pdf              # noqa: E402
from champion_eml import parse_champion_eml   # noqa: E402

FLEXY_BASE = 'https://fullpotos.flexymax.com'
GIST_ID = os.environ.get('GIST_ID', '08dec31e87f93d907ad03c4f68bb547d')
GH_TOKEN = os.environ.get('GH_TOKEN', '')
PANTA_UQ = '52961702'  # mesmo identificador de tela usado pelo App AWB no browser

# ---------------------------------------------------------------------------
# Mapeamentos (UQs do Flexymax)
# ---------------------------------------------------------------------------

CHARGE_TYPE_UQ = {
    'FREIGHT': '81C85F5D',   # AIR FREIGHT
    'BROKER': '1D410A67',
    'DUTIES': 'C68C9ABE',
    'HANDLING': '881B2882',
    'OTHER': '5C4F6591',     # Credit Card Fee / Other Charges
}

VENDOR_UQ = {
    'CAL_AIR': ('B9F3A13B', 'Cal Air Cargo'),
    'MAS_CUSTOMS': ('C72AB731', 'M.A.S. Customs Broker'),
    'NEW_TRANSPORT': ('493179EE', 'NEW TRANSPORT'),
    'UPS_AIR_CARGO': ('DF37EB50', 'UPS AIR CARGO'),
    'KM_HANDLING': ('F28077A2', 'KM HANDLING AND IMPORTS, INC'),
    'KS_REFRIGERATED': ('1DF6115C', 'KS REFRIGERATED TRANSPORT'),
    'SAFTEC': ('EF01D006', 'SAFTEC LOGISTICS LLC'),
    'MIA_FLORAL': ('B53E67D8', 'MIA FREIGHT FLORAL LOGISTIC'),
    'UPS_SCS_ECUADOR': ('50519ED4', 'UPS SCS ECUADOR SAS'),
    'CHAMPION': ('2344BEE3', 'CHAMPION AIR CARGO'),
}


def decide_charge_type(parsed):
    """Regras de negocio definidas pelo Pedro (ago/2026)."""
    v = parsed['vendor']
    codes = {c['code'] for c in parsed.get('charges', [])}

    if v == 'MAS_CUSTOMS':
        # Com entry fee -> Broker (total); so duties -> Duties
        return 'BROKER' if 'ENTRY_FEE' in codes else 'DUTIES'

    if v == 'KM_HANDLING':
        # AWB com sufixo D -> Duties; sem D -> Handling
        return 'DUTIES' if parsed.get('awb_has_d_suffix') else 'HANDLING'

    if v == 'NEW_TRANSPORT':
        # ARANCEL -> Duties; FLETE AEREO -> Freight
        return 'DUTIES' if 'DUTY' in codes else 'FREIGHT'

    # Todos os demais lancam como FREIGHT
    return 'FREIGHT'


# ---------------------------------------------------------------------------
# Gist: log de lancados (dedup) + resultados
# ---------------------------------------------------------------------------

def gist_headers():
    return {'Authorization': f'Bearer {GH_TOKEN}',
            'Accept': 'application/vnd.github+json'}


def gist_read(filename):
    r = requests.get(f'https://api.github.com/gists/{GIST_ID}',
                     headers=gist_headers(), timeout=30)
    r.raise_for_status()
    files = r.json().get('files', {})
    if filename in files:
        content = files[filename].get('content')
        if files[filename].get('truncated'):
            content = requests.get(files[filename]['raw_url'], timeout=30).text
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def gist_write(files_dict):
    payload = {'files': {name: {'content': json.dumps(data, indent=2, ensure_ascii=False)}
                         for name, data in files_dict.items()}}
    r = requests.patch(f'https://api.github.com/gists/{GIST_ID}',
                       headers=gist_headers(), json=payload, timeout=30)
    r.raise_for_status()


def dedup_key(awb, vendor_key, total):
    return f'{awb}|{vendor_key}|{total:.2f}'


# ---------------------------------------------------------------------------
# Flexymax
# ---------------------------------------------------------------------------

def flexy_post_charge(parsed, charge_type_key, dry_run=False):
    supplier_uq, _ = VENDOR_UQ[parsed['vendor']]
    body = {
        'supplier_uq': supplier_uq,
        'ap_type_uq': CHARGE_TYPE_UQ[charge_type_key],
        'invoice_date': parsed['invoice_date'],
        'invoice_no': str(parsed['invoice_no'])[:20],
        'description': f'{parsed["vendor_display"]} (auto)'[:50],
        # Convencao observada no App AWB: o VALOR sempre vai no campo freight;
        # o ap_type_uq e quem classifica o tipo da cobranca.
        'freight': round(float(parsed['total']), 2),
        'total_boxes': parsed.get('total_boxes', 0) or 0,
        'full_boxes': parsed.get('full_boxes', 0) or 0,
        'weight': parsed.get('weight', 0) or 0,
        'awbcode': parsed['awb'],
        'awc_date': parsed['invoice_date'],
        'duties': 0, 'o_charges': 0, 'handling': 0, 'broker': 0, 'oc_ammount': 0,
    }
    if dry_run:
        return {'dry_run': True, 'body': body}

    s = requests.Session()
    # replica o padrao de auditoria do App AWB
    s.post(f'{FLEXY_BASE}/api/audit/enter', timeout=30,
           json={'panta_uq': PANTA_UQ, 'tabla': 'flower_awbs', 'ext_accion': 'N/A'})

    r = s.post(f'{FLEXY_BASE}/api/awbs/charges', json=body, timeout=30)
    r.raise_for_status()
    resp = r.json()
    if not resp.get('success'):
        raise RuntimeError(f'Flexymax recusou o lancamento: {resp}')

    unico = resp.get('unico')
    s.post(f'{FLEXY_BASE}/api/audit/log', timeout=30,
           json={'panta_uq': PANTA_UQ, 'accion': 'Insert', 'tabla': 'flower_awbs',
                 'registro': unico, 'ext_accion': f'AWB {parsed["awb"]} charge (auto)'})
    return {'unico': unico, 'body': body}


def flexy_awb_exists(awb):
    """Confere se o AWB existe no sistema antes de lancar."""
    try:
        r = requests.get(f'{FLEXY_BASE}/api/awbs/search', params={'q': awb}, timeout=30)
        r.raise_for_status()
        return bool(r.json().get('records'))
    except requests.RequestException:
        return None  # indeterminado — nao bloqueia, mas registra warning


# ---------------------------------------------------------------------------
# Orquestracao
# ---------------------------------------------------------------------------

def process(path, dry_run=False):
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    result = {'processed_at': now, 'source_file': os.path.basename(path)}

    # 1. Parse
    if path.lower().endswith('.eml'):
        parsed = parse_champion_eml(path)
    else:
        parsed = parse_pdf(path)
    result.update({k: parsed.get(k) for k in
                   ('vendor', 'vendor_display', 'awb', 'invoice_no',
                    'invoice_date', 'total', 'warnings', 'status')})

    if parsed.get('status') == 'ERROR':
        result['outcome'] = 'ERROR'
        result['error'] = parsed.get('error')
        return result

    log = gist_read('awb_charges_log.json') or {}

    # 2. Champion: nunca lanca — so informa
    if parsed.get('action') == 'NOTIFY_ONLY':
        result['outcome'] = 'NOTIFY_ONLY'
        result['expected_total'] = parsed.get('expected_total')
        launched = [k for k in log
                    if k.startswith(f'{parsed.get("awb")}|UPS_AIR_CARGO|')]
        if launched:
            result['note'] = (f'Frete deste AWB JA LANCADO via statement UPS '
                              f'({log[launched[0]]["invoice_no"]} em '
                              f'{log[launched[0]]["processed_at"]}).')
            if parsed.get('expected_total') is not None:
                if abs(log[launched[0]]['total'] - parsed['expected_total']) > 0.01:
                    result['note'] += (' ATENCAO: valor do MAWB difere do lancado — '
                                      'conferir manualmente.')
        else:
            result['note'] = ('MAWB da Champion recebido. AGUARDANDO statement da '
                              'UPS Air Cargo para lancar '
                              f'(valor esperado: ${parsed.get("expected_total")}).')
        return result

    # 3. Regras de negocio
    charge_type = decide_charge_type(parsed)
    result['charge_type'] = charge_type
    result['vendor_flexymax'] = VENDOR_UQ[parsed['vendor']][1]

    # 4. Dedup
    key = dedup_key(parsed['awb'], parsed['vendor'], parsed['total'])
    if key in log:
        result['outcome'] = 'DUPLICATE'
        result['note'] = (f'Lancamento identico ja feito em '
                          f'{log[key]["processed_at"]} (invoice {log[key]["invoice_no"]}, '
                          f'unico {log[key].get("unico")}). NAO lancado novamente.')
        return result

    # 5. AWB existe?
    exists = flexy_awb_exists(parsed['awb'])
    if exists is False:
        result['outcome'] = 'AWB_NOT_FOUND'
        result['note'] = (f'AWB {parsed["awb"]} nao encontrado no Flexymax. '
                          'Lancamento NAO realizado — verificar se o AWB ja foi criado.')
        return result
    if exists is None:
        result.setdefault('warnings', []).append('Busca do AWB indisponivel; seguiu mesmo assim')

    # 6. POST
    post = flexy_post_charge(parsed, charge_type, dry_run=dry_run)
    if dry_run:
        result['outcome'] = 'DRY_RUN'
        result['would_post'] = post['body']
        return result

    result['outcome'] = 'LAUNCHED'
    result['unico'] = post['unico']

    # 7. Atualiza log de dedup
    log[key] = {'awb': parsed['awb'], 'vendor': parsed['vendor'],
                'vendor_flexymax': VENDOR_UQ[parsed['vendor']][1],
                'charge_type': charge_type, 'total': parsed['total'],
                'invoice_no': parsed['invoice_no'], 'unico': post['unico'],
                'processed_at': now, 'source_file': os.path.basename(path)}
    gist_write({'awb_charges_log.json': log})
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True, help='PDF ou EML a processar')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    result = process(args.file, dry_run=args.dry_run)

    print(json.dumps(result, indent=2, ensure_ascii=False))

    # publica resultado para o Power Automate ler
    if GH_TOKEN and not args.dry_run:
        try:
            gist_write({'awb_results.json': result})
        except requests.RequestException as e:
            print(f'AVISO: falha ao gravar awb_results.json no Gist: {e}',
                  file=sys.stderr)

    if result.get('outcome') in ('ERROR',):
        sys.exit(1)


if __name__ == '__main__':
    main()
