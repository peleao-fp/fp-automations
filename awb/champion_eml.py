#!/usr/bin/env python3
"""
Handler do email da Champion Air Cargo (.eml com zip de documentos do embarque).

REGRA DE NEGOCIO: a Champion NUNCA gera lancamento. O documento oficial de
lancamento e a statement da UPS Air Cargo. Este handler apenas:
  1. Extrai o zip do .eml
  2. Localiza o MAWB_406*.pdf (escaneado)
  3. Roda OCR para extrair AWB e valores (frete + due agent + due carrier)
  4. Retorna um registro action=NOTIFY_ONLY para conferencia cruzada

Uso:
    python3 champion_eml.py arquivo.eml
    python3 champion_eml.py --json arquivo.eml
"""

import sys
import os
import re
import io
import json
import email
import zipfile
import subprocess
import tempfile
from email import policy

import pypdfium2 as pdfium


def ocr_pdf_first_page(pdf_bytes, dpi=300):
    """Renderiza a primeira pagina e roda tesseract. Retorna texto."""
    pdf = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    img = pdf[0].render(scale=dpi / 72).to_pil()
    with tempfile.TemporaryDirectory() as td:
        png = os.path.join(td, 'page.png')
        out = os.path.join(td, 'ocr')
        img.save(png)
        subprocess.run(['tesseract', png, out], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(out + '.txt', encoding='utf-8') as f:
            return f.read()


def money(s):
    """'685,26' ou '685.26' -> float. OCR as vezes troca separadores."""
    s = s.replace(' ', '')
    # padrao latino: 1.234,56 -> 1234.56 ; padrao us: 1,234.56 -> 1234.56
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def parse_champion_eml(path):
    out = {
        'source_file': os.path.basename(path),
        'vendor': 'CHAMPION',
        'vendor_display': 'Champion Air Cargo (informativo)',
        'launch_vendor': 'UPS AIR CARGO',
        'action': 'NOTIFY_ONLY',
        'note': ('Champion nao gera lancamento. O lancamento oficial deste AWB '
                 'sera feito pela statement da UPS Air Cargo.'),
    }

    with open(path, 'rb') as f:
        msg = email.message_from_binary_file(f, policy=policy.default)

    out['email_from'] = str(msg.get('From', ''))
    out['email_subject'] = str(msg.get('Subject', ''))
    out['email_date'] = str(msg.get('Date', ''))

    # AWB do assunto: "... MAWB 406 08763565"
    m = re.search(r'MAWB[\s_]*(\d{3})[\s_]*(\d{8})', out['email_subject'])
    if m:
        out['awb'] = m.group(1) + m.group(2)

    # Localiza zip e MAWB
    mawb_bytes = None
    mawb_name = None
    for part in msg.walk():
        fn = part.get_filename()
        if not fn:
            continue
        payload = part.get_payload(decode=True)
        if fn.lower().endswith('.zip'):
            z = zipfile.ZipFile(io.BytesIO(payload))
            for n in z.namelist():
                base = os.path.basename(n)
                if base.upper().startswith('MAWB') and base.lower().endswith('.pdf'):
                    mawb_bytes = z.read(n)
                    mawb_name = base
                    break
        elif fn.upper().startswith('MAWB') and fn.lower().endswith('.pdf'):
            mawb_bytes = payload
            mawb_name = fn
        if mawb_bytes:
            break

    if not mawb_bytes:
        out['status'] = 'ERROR'
        out['error'] = 'MAWB_*.pdf nao encontrado no email/zip'
        return out

    out['mawb_file'] = mawb_name

    # AWB tambem do nome do arquivo, como redundancia
    m = re.search(r'MAWB[\s_]*(\d{3})[\s_]*(\d{8})', mawb_name)
    if m and not out.get('awb'):
        out['awb'] = m.group(1) + m.group(2)

    # OCR
    try:
        text = ocr_pdf_first_page(mawb_bytes)
    except Exception as e:
        out['status'] = 'ERROR'
        out['error'] = f'OCR falhou: {e}'
        return out

    # Valores: frete (weight charge), due agent, due carrier
    # OCR gera "USS 685,26" / "US$ 685,26" — aceita ambos
    vals = [money(v) for v in re.findall(r'US[S\$]\s*([\d\.,]+)', text)]
    vals = [v for v in vals if v is not None]

    freight = agent = carrier = None
    m = re.search(r'Weight Charge[\s\S]{0,120}?US[S\$]\s*([\d\.,]+)', text)
    if m:
        freight = money(m.group(1))
    m = re.search(r'Due Agent[\s\S]{0,60}?US[S\$]\s*([\d\.,]+)', text)
    if m:
        agent = money(m.group(1))
    m = re.search(r'Due Carrier[\s\S]{0,60}?US[S\$]\s*([\d\.,]+)', text)
    if m:
        carrier = money(m.group(1))

    # Fallback: se nao achou pelas ancoras, usa os valores distintos do OCR
    if freight is None and vals:
        freight = max(set(vals), key=vals.count)  # valor que mais repete = frete

    parts = [v for v in (freight, agent, carrier) if v is not None]
    out['charges_reference'] = {
        'weight_charge': freight,
        'due_agent': agent,
        'due_carrier': carrier,
    }
    out['expected_total'] = round(sum(parts), 2) if parts else None

    warnings = []
    if not out.get('awb'):
        warnings.append('AWB nao identificado')
    if out['expected_total'] is None:
        warnings.append('Valores nao extraidos do OCR — conferencia manual')
    if agent is None or carrier is None:
        warnings.append('OCR nao capturou todos os componentes; total pode estar incompleto')
    out['warnings'] = warnings
    out['status'] = 'OK' if not warnings else 'WARN'
    return out


def main():
    args = [a for a in sys.argv[1:] if a != '--json']
    as_json = '--json' in sys.argv
    if not args:
        print(__doc__)
        sys.exit(1)

    results = [parse_champion_eml(p) for p in args]
    if as_json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    for r in results:
        print('=' * 72)
        print(f'[{r["status"]}] {r["source_file"]}')
        print('=' * 72)
        if r['status'] == 'ERROR':
            print(' ', r['error'])
            continue
        print(f'  Acao       : {r["action"]}  (nao lanca — aguarda statement UPS)')
        print(f'  AWB        : {r.get("awb")}')
        print(f'  MAWB file  : {r.get("mawb_file")}')
        cr = r.get('charges_reference', {})
        print(f'  Referencia : frete={cr.get("weight_charge")}  '
              f'agent={cr.get("due_agent")}  carrier={cr.get("due_carrier")}')
        print(f'  Total esperado na statement UPS: $ {r.get("expected_total")}')
        for w in r.get('warnings', []):
            print(f'  ! {w}')
        print()


if __name__ == '__main__':
    main()
