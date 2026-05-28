require('dotenv').config();
const fs    = require('fs');
const cfg   = require('./config');
const flexy = require('./flexymax');
const { parseEmail } = require('./parser');

function formatDate(d) {
  return d.toLocaleDateString('en-US', { month:'long', day:'numeric', year:'numeric' });
}
function addDays(d, n) { const r=new Date(d); r.setDate(r.getDate()+n); return r; }
function extractCode(s) {
  const parts = (s||'').trim().split(/\s+/);
  if (!parts.length) return '';
  const first = parts[0];
  // Short letter-only prefix + numeric code → combine (e.g. "UN 616-24-07" → "UN616-24-07")
  if (first.length <= 3 && /^[A-Za-z]+$/.test(first) && parts[1] && /\d/.test(parts[1])) {
    return first + parts[1];
  }
  // First token has numbers → it's a product code, use it directly
  if (/\d/.test(first)) return first;
  // No numbers in first token → descriptive name from Flexymax (e.g. "BUBBLE BALL 8 INCHES")
  // Use the full description for exact match
  return (s||'').trim();
}

async function createPrebook(data, dryRun=false) {
  const { location, grower_name, lines } = data;
  const customer = cfg.CUSTOMERS[location];
  if (!customer) throw new Error(`Unknown location: ${location}`);

  console.log(`\n${'='.repeat(55)}`);
  console.log(`📦 ${location} — ${customer.label}`);
  console.log(`   Grower: ${grower_name} | Products: ${lines.length}`);

  const pbDate   = formatDate(new Date());
  const shipDate = formatDate(addDays(new Date(), cfg.SHIPPING_DAYS_AHEAD));
  console.log(`   PB: ${pbDate} → Ship: ${shipDate}`);

  if (dryRun) {
    console.log('   [DRY RUN]');
    return { location, prebook_uq:'DRY_RUN', pbook_no:'DRY_RUN', ok:lines.length, fail:0 };
  }

  const julian  = await flexy.dateToJulian(shipDate);
  const carrier = await flexy.getDefaultCarrier(customer.shipto_uq);
  console.log(`   Carrier: ${carrier?.carrier?.trim()||'n/a'}`);
  const addr = await flexy.getShipAddress(customer.shipto_uq);

  const header = await flexy.createPrebookHeader({
    carrier_uq:     carrier?.unico||'',
    carrier_account:carrier?.account||'.',
    carrier_zone:   carrier?.zone||'',
    shipto_uq:      customer.shipto_uq,
    customer_uq:    customer.customer_uq,
    whouse_uq:      cfg.WAREHOUSE_UQ,
    ship_name:      addr?.Ship_Name?.trim()||'.',
    ship_address:   addr?.Ship_Address?.trim()||'.',
    ship_city:      addr?.Ship_city?.trim()||'.',
    ship_state:     addr?.Ship_state?.trim()||'.',
    ship_zip:       addr?.Ship_zip?.trim()||'.',
    ship_phone:     addr?.Ship_phone?.trim()||'.',
    ship_fax:       addr?.Ship_fax?.trim()||'.',
    terms_uq:       cfg.TERMS_UQ,
    salesman_uq:    cfg.SALESMAN_UQ,
    pb_date:        pbDate,
    shipping_date:  shipDate,
    juliantext:     julian,
  });

  const prebook_uq = header.unico;
  const pbRead     = await flexy.readPrebookHeader(prebook_uq);
  const pbook_no   = pbRead?.pbook_no || '?';
  console.log(`   ✅ Prebook #${pbook_no} (${prebook_uq})`);

  let ok=0, fail=0;
  for (const line of lines) {
    const code = extractCode(line.product_code);
    process.stdout.write(`   → [${code}] ${line.qty_boxes}bx @ $${line.box_price}... `);
    try {
      const p = await flexy.searchProduct(code);
      if (!p) { console.log('NOT FOUND ⚠️'); fail++; continue; }
      await flexy.insertPrebookLine({
        prebook_uq, product_uq:p.unico, case_uq:p.case_uq,
        up_x_pack:p.up_x_pack||1, up_x_case:p.up_x_case||1,
        sales_price:line.box_price, qty_boxes:line.qty_boxes,
        salesman_uq:cfg.SALESMAN_UQ,
      });
      console.log(`✅ ${p.description?.trim()}`);
      ok++;
    } catch(e) { console.log(`❌ ${e.message}`); fail++; }
  }

  console.log(`   Result: ${ok} OK, ${fail} failed`);
  return { location, prebook_uq, pbook_no, ok, fail };
}

async function main() {
  const args    = process.argv.slice(2);
  const dryRun  = args.includes('--dry-run');
  const jsonIdx = args.indexOf('--json');
  const htmlIdx = args.indexOf('--html');
  const subjIdx = args.indexOf('--subject');

  console.log(`🌸 Prebook Automation | ${dryRun?'DRY RUN':'LIVE'} | ${new Date().toLocaleString()}`);

  let list = [];

  if (jsonIdx >= 0) {
    // Mode 1: JSON file (manual/test)
    const file = args[jsonIdx+1];
    const data = JSON.parse(fs.readFileSync(file,'utf8'));
    list = Array.isArray(data) ? data : [data];
    console.log(`📂 Loaded from ${file}`);

  } else if (htmlIdx >= 0) {
    // Mode 2: raw HTML from email (Power Automate → GitHub Actions)
    const htmlFile = args[htmlIdx+1];
    const subject  = subjIdx >= 0 ? args[subjIdx+1] : '';
    const html     = fs.readFileSync(htmlFile,'utf8');
    console.log(`📧 Parsing: "${subject}"`);
    const parsed = parseEmail(subject, html);
    if (!parsed.location) {
      console.error(`❌ Could not detect location from subject: "${subject}"`);
      process.exit(1);
    }
    if (parsed.lines.length === 0) {
      console.log('📭 No products found. Exiting.');
      return;
    }
    list = [parsed];
    console.log(`   Location: ${parsed.location} | Products: ${parsed.lines.length}`);

  } else {
    console.error('Usage:');
    console.error('  node src/index.js --json prebooks.json [--dry-run]');
    console.error('  node src/index.js --subject "NPL SUGGESTED" --html body.html [--dry-run]');
    process.exit(1);
  }

  const results = [];
  for (const d of list) {
    try { results.push(await createPrebook(d, dryRun)); }
    catch(e) { console.error(`❌ ${d.location}: ${e.message}`); results.push({location:d.location,error:e.message}); }
  }

  console.log(`\n${'='.repeat(55)}`);
  console.log('📊 SUMMARY');
  results.forEach(r => r.error
    ? console.log(`  ❌ ${r.location}: ${r.error}`)
    : console.log(`  ✅ ${r.location}: Prebook #${r.pbook_no} — ${r.ok} OK, ${r.fail} failed`)
  );

  const out = `prebook-results-${Date.now()}.json`;
  fs.writeFileSync(out, JSON.stringify(results,null,2));
  console.log(`💾 ${out}`);
}

main().catch(e=>{ console.error('Fatal:',e.message); process.exit(1); });
