// ============================================================
// OM MIAMI FLOWERS SUGGESTED → 1 prebook (customer 1158)
//
// Usage:
//   node flowers/index.js --gist <gist_id> --subject "..." [--dry-run] [--out file.json]
//   node flowers/index.js --html body.html --subject "..." [--dry-run] [--today 2026-09-17]
//
// --dry-run still looks products up in Flexymax (read-only) but creates nothing.
// ============================================================
require('dotenv').config();
const fs     = require('fs');
const rootCfg = require('../config');
const flexy  = require('../flexymax');
const cfg    = require('./config');
const { readGistFile } = require('./gist');
const { parseFlowersEmail, collapseSpaces } = require('./parser');

function arg(args, name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
}

// ── dates ────────────────────────────────────────────────────

// Today's calendar date in the business timezone, as a UTC-midnight Date
function todayInTz(tz) {
  const ymd = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' })
    .format(new Date());
  return new Date(`${ymd}T00:00:00Z`);
}

function addDays(d, n) { const r = new Date(d); r.setUTCDate(r.getUTCDate() + n); return r; }

function formatDate(d) {
  return d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

// Next occurrence of `weekday` strictly after `from` (Thursday → Monday = +4)
function nextWeekday(from, weekday) {
  const diff = (weekday - from.getUTCDay() + 7) % 7 || 7;
  return addDays(from, diff);
}

function computeDates(todayOverride) {
  const today    = todayOverride ? new Date(`${todayOverride}T00:00:00Z`) : todayInTz(cfg.TIMEZONE);
  const delivery = nextWeekday(today, cfg.DELIVERY_WEEKDAY);
  const shipping = addDays(delivery, -cfg.SHIP_DAYS_BEFORE_DELIVERY);
  return { pb_date: formatDate(delivery), shipping_date: formatDate(shipping) };
}

// ── products ─────────────────────────────────────────────────

// The suggestion comes from Flexymax itself, so the description must match exactly
// (ignoring repeated spaces / case). No fuzzy fallback: better "not found" than a wrong product.
async function findProduct(line) {
  const wanted = collapseSpaces(line.product).toUpperCase();
  const rows   = await flexy.searchProducts(line.product, cfg.PRODUCT_SEARCH_PAGE_SIZE);
  const exact  = rows.filter(p => collapseSpaces(p.description).toUpperCase() === wanted);
  if (!exact.length) return null;
  const type = collapseSpaces(line.type).toUpperCase();
  return exact.find(p => p.active && collapseSpaces(p.class).toUpperCase() === type)
      || exact.find(p => p.active)
      || exact[0];
}

async function resolveLines(lines) {
  const resolved = [];
  const failed   = [];
  for (const line of lines) {
    process.stdout.write(`   → ${line.product} (${line.qty_boxes}bx)... `);
    try {
      const p = await findProduct(line);
      if (!p) {
        console.log('NOT FOUND ⚠️');
        failed.push({ product: line.product, qty_boxes: line.qty_boxes, reason: 'Descrição exata não encontrada no Flexymax' });
        continue;
      }
      console.log(`✅ ${collapseSpaces(p.description)} [${collapseSpaces(p.case_sh)} ${p.up_x_case}x${p.up_x_pack}${p.active ? '' : ' INACTIVE'}]`);
      resolved.push({ line, product: p });
    } catch (e) {
      console.log(`❌ ${e.message}`);
      failed.push({ product: line.product, qty_boxes: line.qty_boxes, reason: e.message });
    }
  }
  return { resolved, failed };
}

// ── prebook ──────────────────────────────────────────────────

async function createPrebook(resolved, dates) {
  const pb = cfg.PREBOOK;
  const julian = await flexy.dateToJulian(dates.shipping_date);

  let addr = null;
  try { addr = await flexy.getShipAddress(pb.shipto_uq); }
  catch (e) { console.warn(`   ⚠️ Ship address: ${e.message}`); }
  const a = f => addr?.[f]?.trim() || '.';

  const header = await flexy.createPrebookHeader({
    carrier_uq:      pb.carrier_uq,
    carrier_account: '.',
    carrier_zone:    '',
    shipto_uq:       pb.shipto_uq,
    customer_uq:     pb.customer_uq,
    whouse_uq:       pb.whouse_uq,
    ship_name: a('Ship_Name'), ship_address: a('Ship_Address'), ship_city: a('Ship_city'),
    ship_state: a('Ship_state'), ship_zip: a('Ship_zip'), ship_phone: a('Ship_phone'), ship_fax: a('Ship_fax'),
    terms_uq:        pb.terms_uq,
    salesman_uq:     rootCfg.SALESMAN_UQ,
    pb_date:         dates.pb_date,
    shipping_date:   dates.shipping_date,
    juliantext:      julian,
    grower_uq:       null,
  });

  const prebook_uq = header.unico;
  const pbRead     = await flexy.readPrebookHeader(prebook_uq);
  const pbook_no   = pbRead?.pbook_no || 0;
  console.log(`   ✅ Prebook #${pbook_no} (${prebook_uq})`);

  let ok = 0;
  const failed = [];
  for (const { line, product: p } of resolved) {
    process.stdout.write(`   + ${collapseSpaces(p.description)} ${line.qty_boxes}bx... `);
    try {
      await flexy.insertPrebookLine({
        prebook_uq,
        product_uq:  p.unico,
        case_uq:     p.case_uq,
        up_x_pack:   p.up_x_pack || 1,
        up_x_case:   p.up_x_case || 1,
        sales_price: p.sales_price || 0,
        qty_boxes:   line.qty_boxes,
        salesman_uq: rootCfg.SALESMAN_UQ,
        grower_uq:   null,
      });
      console.log('✅');
      ok++;
    } catch (e) {
      console.log(`❌ ${e.message}`);
      failed.push({ product: line.product, qty_boxes: line.qty_boxes, reason: e.message });
    }
  }
  return { prebook_uq, pbook_no, ok, failed };
}

// ── main ─────────────────────────────────────────────────────

function emptyResult(args) {
  return {
    location: cfg.LOCATION, type: cfg.TYPE, subject: arg(args, '--subject') || '', dry_run: args.includes('--dry-run'),
    success: false, pbook_no: 0, prebook_uq: '', ok: 0, fail: 0,
    error: null, failed_items: [], skipped_items: [],
    customer: cfg.PREBOOK.label, carrier: cfg.PREBOOK.carrier_name,
  };
}

// Fills `result` as it goes, so a crash midway still reports what was done
async function run(args, result) {
  const dryRun   = result.dry_run;
  const subject  = result.subject;
  const gistId   = arg(args, '--gist');
  const htmlFile = arg(args, '--html');

  console.log(`🌸 ${cfg.NAME} | ${dryRun ? 'DRY RUN' : 'LIVE'} | ${new Date().toISOString()}`);

  let html;
  if (gistId)        html = await readGistFile(gistId);
  else if (htmlFile) html = fs.readFileSync(htmlFile, 'utf8');
  else throw new Error('Usage: node flowers/index.js (--gist <id> | --html <file>) --subject "..." [--dry-run]');
  if (!html) throw new Error('Email body is empty');

  const parsed = parseFlowersEmail(subject, html);
  Object.assign(result, {
    expected_boxes: parsed.expected_boxes,
    total_boxes:    parsed.total_boxes,
    skipped_items:  parsed.skipped,
  });
  console.log(`📧 "${subject}" | customer in email: ${parsed.customer_no ?? '?'} | ${parsed.lines.length} products | ${parsed.total_boxes} boxes (email says ${parsed.expected_boxes ?? '?'})`);

  // Safety: never book a suggestion that belongs to another customer
  if (parsed.customer_no && parsed.customer_no !== cfg.CUSTOMER_NO) {
    throw new Error(`Email is for customer ${parsed.customer_no}, automation only books ${cfg.CUSTOMER_NO}`);
  }
  if (!parsed.lines.length) throw new Error('No products with Suggested_BX > 0 found in the email table');

  const dates = computeDates(arg(args, '--today'));
  Object.assign(result, dates);
  console.log(`📅 PB date (delivery): ${dates.pb_date} | Shipping: ${dates.shipping_date}`);

  console.log('\n🔎 Matching products');
  const { resolved, failed } = await resolveLines(parsed.lines);
  result.failed_items.push(...failed);

  if (!resolved.length) throw new Error('No product from the email was found in Flexymax — prebook not created');

  if (dryRun) {
    Object.assign(result, { success: true, pbook_no: 0, prebook_uq: 'DRY_RUN', ok: resolved.length });
  } else {
    console.log('\n📦 Creating prebook');
    const pb = await createPrebook(resolved, dates);
    result.failed_items.push(...pb.failed);
    Object.assign(result, { success: true, pbook_no: pb.pbook_no, prebook_uq: pb.prebook_uq, ok: pb.ok });
  }
  result.fail = result.failed_items.length;
}

async function main() {
  const args = process.argv.slice(2);
  const out  = arg(args, '--out') || 'flowers-result.json';
  const result = emptyResult(args);
  try {
    await run(args, result);
    console.log(`\n📊 ${result.dry_run ? 'DRY RUN' : `Prebook #${result.pbook_no}`} — ${result.ok} OK, ${result.fail} failed`);
  } catch (e) {
    console.error(`\n❌ ${e.message}`);
    Object.assign(result, { success: false, error: e.message, fail: result.failed_items.length });
  }
  fs.writeFileSync(out, JSON.stringify(result, null, 2));
  console.log(`💾 ${out}`);
  if (!result.success) process.exit(1);
}

if (require.main === module) main();

module.exports = { computeDates, findProduct };
