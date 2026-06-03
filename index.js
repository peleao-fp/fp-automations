require('dotenv').config();
const fs    = require('fs');
const cfg   = require('./config');
const flexy = require('./flexymax');
const { parseEmail } = require('./parser');

function formatDate(d) {
  return d.toLocaleDateString('en-US', { month:'long', day:'numeric', year:'numeric' });
}
function addDays(d, n) { const r=new Date(d); r.setDate(r.getDate()+n); return r; }

// Check if a product belongs to BOX prebook
function isBoxProduct(productStr) {
  const name = (productStr||'').trim().toUpperCase();
  return cfg.BY_BOX_PRODUCTS.some(p => name.includes(p.toUpperCase()));
}

// Look up grower UQ from email grower name
function findGrowerUq(growerName) {
  if (!growerName) return null;
  const upper = growerName.trim().toUpperCase();
  const entry = cfg.GROWER_MAP.find(g =>
    g.match.some(m => upper.includes(m.toUpperCase()))
  );
  if (entry && entry.uq) {
    console.log(`   Grower: ${entry.name} (${entry.uq})`);
    return entry.uq;
  }
  if (entry) console.warn(`   ⚠️ Grower "${growerName}" found but no UQ yet (${entry.name})`);
  else console.warn(`   ⚠️ Grower "${growerName}" not found in map`);
  return null;
}

// Smart search term extraction
function extractSearchTerm(s) {
  const parts = (s||'').trim().split(/\s+/);
  if (!parts.length) return '';
  const first = parts[0];
  // Short letter-only prefix + numeric code → combine (e.g. "UN 616-24-07" → "UN616-24-07")
  if (first.length <= 3 && /^[A-Za-z]+$/.test(first) && parts[1] && /\d/.test(parts[1])) {
    return first + parts[1];
  }
  // First token has numbers → it's a product code
  if (/\d/.test(first)) return first;
  // No numbers → descriptive name, use full description for exact match
  return (s||'').trim();
}

// Create ONE prebook (either BOX or UNITS)
async function createPrebook(location, type, lines, grower_name, dryRun=false) {
  const locCfg   = cfg.LOCATIONS[location]?.[type];
  if (!locCfg) throw new Error(`No config for ${location}/${type}`);

  // Look up grower UQ (only used for UNITS)
  const growerUq = type === 'UNITS' ? findGrowerUq(grower_name) : null;

  console.log(`\n${'='.repeat(55)}`);
  console.log(`📦 ${location} ${type} — ${locCfg.label}`);
  console.log(`   Grower: ${grower_name} | Products: ${lines.length}`);

  const shipDate = formatDate(addDays(new Date(), cfg.SHIPPING_DAYS_AHEAD));
  const pbDate   = shipDate; // prebook date = shipping date (7 days ahead)
  console.log(`   PB: ${pbDate} → Ship: ${shipDate}`);

  if (dryRun) {
    console.log('   [DRY RUN]');
    return { location, type, prebook_uq:'DRY_RUN', pbook_no:'DRY_RUN', ok:lines.length, fail:0 };
  }

  // Julian date
  const julian = await flexy.dateToJulian(shipDate);

  // Ship address (fetch dynamically)
  let ship_name='.', ship_address='.', ship_city='.', ship_state='.', ship_zip='.', ship_phone='.', ship_fax='.';
  try {
    const addr = await flexy.getShipAddress(locCfg.shipto_uq);
    if (addr) {
      ship_name    = addr.Ship_Name?.trim()    || '.';
      ship_address = addr.Ship_Address?.trim() || '.';
      ship_city    = addr.Ship_city?.trim()    || '.';
      ship_state   = addr.Ship_state?.trim()   || '.';
      ship_zip     = addr.Ship_zip?.trim()     || '.';
      ship_phone   = addr.Ship_phone?.trim()   || '.';
      ship_fax     = addr.Ship_fax?.trim()     || '.';
    }
  } catch(e) { console.warn(`   ⚠️ Ship address: ${e.message}`); }

  // Create header (carrier is hardcoded per location+type)
  const header = await flexy.createPrebookHeader({
    carrier_uq:     locCfg.carrier_uq,
    carrier_account: '.',
    carrier_zone:   '',
    shipto_uq:      locCfg.shipto_uq,
    customer_uq:    locCfg.customer_uq,
    whouse_uq:      locCfg.whouse_uq,
    ship_name, ship_address, ship_city, ship_state, ship_zip, ship_phone, ship_fax,
    terms_uq:       locCfg.terms_uq,
    salesman_uq:    cfg.SALESMAN_UQ,
    pb_date:        pbDate,
    shipping_date:  shipDate,
    juliantext:     julian,
    grower_uq:      null,
  });

  const prebook_uq = header.unico;
  const pbRead     = await flexy.readPrebookHeader(prebook_uq);
  const pbook_no   = pbRead?.pbook_no || '?';
  console.log(`   ✅ Prebook #${pbook_no} (${prebook_uq})`);

  let ok=0, fail=0;
  const failedItems = [];

  for (const line of lines) {
    const searchTerm = extractSearchTerm(line.product_code);
    process.stdout.write(`   → ${searchTerm} (${line.qty_boxes}bx)... `);
    try {
      const p = await flexy.searchProduct(searchTerm);
      if (!p) {
        console.log('NOT FOUND ⚠️');
        failedItems.push({ product: line.product_code, reason: 'Product not found in Flexymax' });
        fail++; continue;
      }

      // Field mapping depends on type
      const up_x_pack   = type === 'BOX'   ? (line.units_x_box || 1) : 1;
      const packs_case  = type === 'UNITS'  ? (line.units_x_box || 1) : 1;
      const sales_price = type === 'UNITS'  ? (line.unit_price || line.box_price) : line.box_price;
      const case_uq     = type === 'UNITS'  ? cfg.CASE_UQ.UNIT : cfg.CASE_UQ.BOX;
      // Grower: only on UNITS prebook, not BOX/Everyday
      const lineGrowerName = line.grower_name || grower_name;
      const grower_uq   = type === 'UNITS'  ? findGrowerUq(lineGrowerName) : null;

      await flexy.insertPrebookLine({
        prebook_uq,
        product_uq:    p.unico,
        case_uq,
        up_x_pack,
        up_x_case:     packs_case,
        sales_price,
        qty_boxes:     line.qty_boxes,
        salesman_uq:   cfg.SALESMAN_UQ,
        grower_uq,
      });
      console.log(`✅ ${p.description?.trim()}`);
      ok++;
    } catch(e) {
      console.log(`❌ ${e.message}`);
      failedItems.push({ product: line.product_code, reason: e.message });
      fail++;
    }
  }

  console.log(`   Result: ${ok} OK, ${fail} failed`);
  return { location, type, prebook_uq, pbook_no, ok, fail, success: true, failed_items: failedItems };
}

// Process one email → up to 2 prebooks (BOX + UNITS)
async function processEmail(data, dryRun=false) {
  const { location, grower_name, lines } = data;
  if (!location) throw new Error(`Cannot detect location from: "${data.subject}"`);
  if (!cfg.LOCATIONS[location]) throw new Error(`No config for location: ${location}`);

  // Split lines into BOX and UNITS groups
  const boxLines   = lines.filter(l => isBoxProduct(l.product_code));
  const unitsLines = lines.filter(l => !isBoxProduct(l.product_code));

  console.log(`\n🌍 ${location}: ${boxLines.length} BOX products, ${unitsLines.length} UNITS products`);

  const results = [];

  if (boxLines.length > 0) {
    try {
      const r = await createPrebook(location, 'BOX', boxLines, grower_name, dryRun);
      results.push(r);
    } catch(e) {
      console.error(`❌ ${location} BOX: ${e.message}`);
      results.push({ location, type:'BOX', success:false, error:e.message });
    }
  }

  if (unitsLines.length > 0) {
    try {
      const r = await createPrebook(location, 'UNITS', unitsLines, grower_name, dryRun);
      results.push(r);
    } catch(e) {
      console.error(`❌ ${location} UNITS: ${e.message}`);
      results.push({ location, type:'UNITS', success:false, error:e.message });
    }
  }

  return results;
}

async function main() {
  const args    = process.argv.slice(2);
  const dryRun  = args.includes('--dry-run');
  const jsonIdx = args.indexOf('--json');
  const htmlIdx = args.indexOf('--html');
  const subjIdx = args.indexOf('--subject');

  console.log(`🌸 Prebook Automation | ${dryRun?'DRY RUN':'LIVE'} | ${new Date().toLocaleString()}`);

  let emailList = [];

  if (jsonIdx >= 0) {
    const file = args[jsonIdx+1];
    const data = JSON.parse(fs.readFileSync(file,'utf8'));
    emailList = Array.isArray(data) ? data : [data];
    console.log(`📂 Loaded from ${file}`);
  } else if (htmlIdx >= 0) {
    const htmlFile = args[htmlIdx+1];
    const subject  = subjIdx >= 0 ? args[subjIdx+1] : '';
    const html     = fs.readFileSync(htmlFile,'utf8');
    console.log(`📧 Parsing: "${subject}"`);
    const parsed = parseEmail(subject, html);
    if (!parsed.location) { console.error(`❌ Cannot detect location from: "${subject}"`); process.exit(1); }
    if (!parsed.lines.length) { console.log('📭 No products found.'); return; }
    emailList = [parsed];
    console.log(`   Location: ${parsed.location} | Products: ${parsed.lines.length}`);
  } else {
    console.error('Usage: node index.js --json file.json [--dry-run]');
    console.error('       node index.js --subject "NPL SUGGESTED" --html body.html [--dry-run]');
    process.exit(1);
  }

  const allResults = [];
  for (const emailData of emailList) {
    try {
      const results = await processEmail(emailData, dryRun);
      allResults.push(...results);
    } catch(e) {
      console.error(`❌ ${emailData.location}: ${e.message}`);
      allResults.push({ location:emailData.location, success:false, error:e.message });
    }
  }

  // Summary
  console.log(`\n${'='.repeat(55)}`);
  console.log('📊 SUMMARY');
  allResults.forEach(r => r.error
    ? console.log(`  ❌ ${r.location} ${r.type||''}: ${r.error}`)
    : console.log(`  ✅ ${r.location} ${r.type}: Prebook #${r.pbook_no} — ${r.ok} OK, ${r.fail} failed`)
  );

  const out = `prebook-results-${Date.now()}.json`;
  fs.writeFileSync(out, JSON.stringify(allResults,null,2));
  console.log(`💾 ${out}`);
}

main().catch(e=>{ console.error('Fatal:',e.message); process.exit(1); });
