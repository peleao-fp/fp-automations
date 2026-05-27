// ============================================================
// FLEXYMAX API CLIENT
// ============================================================
const axios    = require('axios');
const FormData = require('form-data');
const cfg      = require('./config');

// ── helpers ──────────────────────────────────────────────────

function buildForm(actionId, parameterMap, values) {
  // parameterMap: { fieldName: 'k0', ... }
  // values: { k0: value, k1: value, ... }

  const paramProps = {};
  Object.entries(values).forEach(([key, val]) => {
    let datatype = typeof val;
    if (val === null || val === undefined) datatype = 'null';
    else if (datatype === 'number') datatype = 'number';
    else if (datatype === 'boolean') datatype = 'boolean';
    else datatype = 'string';
    paramProps[key] = { datatype, blobIdentifiers: [] };
  });

  const form = new FormData();
  form.append('executeActionDTO', JSON.stringify({
    actionId,
    viewMode: true,
    paramProperties: paramProps,
    analyticsProperties: { isUserInitiated: false }
  }));
  form.append('parameterMap', JSON.stringify(parameterMap));

  Object.entries(values).forEach(([key, val]) => {
    if (val === null || val === undefined) {
      form.append(key, 'null');
    } else {
      form.append(key, String(val), { filename: 'blob', contentType: 'text/plain' });
    }
  });

  return form;
}

async function callAction(actionId, parameterMap, values) {
  const form = buildForm(actionId, parameterMap, values);
  const res = await axios.post(cfg.FLEXYMAX_BASE_URL, form, {
    headers: {
      ...form.getHeaders(),
      'accept': 'application/json',
      'x-anonymous-user-id': cfg.ANONYMOUS_USER_ID,
      'x-appsmith-environmentid': 'unused_env',
      'x-appsmith-version': 'v1.78',
      'origin': 'https://app.flexymax.com',
      'referer': 'https://app.flexymax.com/app/fullpot/prebooks-659f60bbb185274a675b8002?embed=true',
    }
  });
  const data = res.data;
  if (!data.responseMeta?.success) throw new Error(`Flexymax error: ${JSON.stringify(data)}`);
  return data.data?.body || [];
}

// ── public functions ──────────────────────────────────────────

// Search product by code/description → returns first match
async function searchProduct(searchText) {
  const rows = await callAction(
    cfg.ACTIONS.SEARCH_PRODUCT,
    {
      'tblPrebookProductList.pageSize': 'k0',
      'tblPrebookProductList.pageNo':   'k1',
      'inputSearchProducts.inputText':  'k2',
    },
    { k0: 10, k1: 1, k2: searchText }
  );
  return rows[0] || null; // first match
}

// Convert date string → Julian integer
async function dateToJulian(dateStr) {
  const rows = await callAction(
    cfg.ACTIONS.DATE_TO_JULIAN,
    { 'this.params.ldWhouse_date': 'k0' },
    { k0: dateStr }
  );
  return rows[0]?.juliantext || 0;
}

// Get default carrier for a shipto_uq
async function getDefaultCarrier(shipto_uq) {
  const rows = await callAction(
    cfg.ACTIONS.GET_CARRIERS,
    { ' this.params.lcShip_uq': 'k0' },
    { k0: shipto_uq }
  );
  const def = rows.find(r => r.defa_carrier === 1) || rows[0];
  return def || null;
}

// Get ship address for a shipto_uq
async function getShipAddress(shipto_uq) {
  const rows = await callAction(
    cfg.ACTIONS.GET_SHIP_ADDRESS,
    {
      ' this.params.Ship_state ':  'k0',
      ' this.params.Ship_city ':   'k1',
      'this.params.Ship_zip ':     'k2',
      ' this.params.Ship_phone ':  'k3',
      ' this.params.Ship_fax ':    'k4',
      ' this.params.Ship_name ':   'k5',
      ' this.params.Ship_address ':'k6',
      ' this.params.Ship_uq ':     'k7',
    },
    { k0: '', k1: '', k2: '', k3: '', k4: '', k5: '', k6: '', k7: shipto_uq }
  );
  return rows[0] || null;
}

// Create prebook header → returns { unico, pbook_no }
async function createPrebookHeader(params) {
  const {
    carrier_uq, carrier_account, carrier_zone,
    shipto_uq, customer_uq, whouse_uq,
    ship_name, ship_address, ship_city, ship_state, ship_zip, ship_phone, ship_fax,
    terms_uq, salesman_uq, pb_date, shipping_date, juliantext,
    cporder_no = '', details = '', takefrom = '', label_reference = '',
    grower_uq = null, cargo_uq = null,
  } = params;

  const rows = await callAction(
    cfg.ACTIONS.CREATE_PREBOOK,
    {
      'JSONPrebookInsert.formData.account':               'k0',
      'JSONPrebookInsert.formData.carrier_uq':            'k1',
      '(JSONPrebookInsert.formData?.cporder_no || \'\')': 'k2',
      'JSONPrebookInsert.formData.ship_address':          'k3',
      'JSONPrebookInsert.formData.pb_date':               'k4',
      'JSONPrebookInsert.formData.cargo_uq':              'k5',
      '(JSONPrebookInsert.formData?.juliantext|| \'\')':  'k6',
      '(JSONPrebookInsert.formData?.details || \'\')':    'k7',
      'JSONPrebookInsert.formData.shipto_uq':             'k8',
      'JSONPrebookInsert.formData.whouse_uq':             'k9',
      '(JSONPrebookInsert.formData?.takefrom|| \'\')':    'k10',
      'JSONPrebookInsert.formData.ship_name':             'k11',
      'JSONPrebookInsert.formData.ship_zip':              'k12',
      'JSONPrebookInsert.formData.ship_fax':              'k13',
      'JSONPrebookInsert.formData.ship_phone':            'k14',
      'JSONPrebookInsert.formData.terms_uq':              'k15',
      '(JSONPrebookInsert.formData?.label_reference|| \'\')': 'k16',
      'appsmith.store.loSalesRepInfo[0].unico':           'k17',
      'JSONPrebookInsert.formData.ship_city':             'k18',
      'JSONPrebookInsert.formData.grower_uq':             'k19',
      'JSONPrebookInsert.formData.ship_state':            'k20',
      'JSONPrebookInsert.formData.shipping_date':         'k21',
      '(JSONPrebookInsert.formData?.zone || \'\')':       'k22',
      'JSONPrebookInsert.formData.customer_uq':           'k23',
    },
    {
      k0:  carrier_account || '.',
      k1:  carrier_uq,
      k2:  cporder_no,
      k3:  ship_address || '.',
      k4:  pb_date,
      k5:  cargo_uq,
      k6:  String(juliantext || ''),
      k7:  details,
      k8:  shipto_uq,
      k9:  whouse_uq,
      k10: takefrom,
      k11: ship_name || '.',
      k12: ship_zip  || '.',
      k13: ship_fax  || '.',
      k14: ship_phone|| '.',
      k15: terms_uq,
      k16: label_reference,
      k17: salesman_uq,
      k18: ship_city || '.',
      k19: grower_uq,
      k20: ship_state|| '.',
      k21: shipping_date,
      k22: carrier_zone || '',
      k23: customer_uq,
    }
  );

  if (!rows[0] || rows[0].error) throw new Error(`Create header failed: ${JSON.stringify(rows[0])}`);
  return rows[0]; // { unico, message }
}

// Insert prebook line → returns { unico }
async function insertPrebookLine(params) {
  const {
    prebook_uq, product_uq, case_uq,
    up_x_pack, up_x_case, units_per_case,
    sales_price, qty_boxes,
    salesman_uq,
    grower_uq = '',
  } = params;

  const rows = await callAction(
    cfg.ACTIONS.INSERT_LINE,
    {
      'JSONFormAddPrebook.formData.up_x_pack':                        'k0',
      '\'\'':                                                          'k1',
      '(JSONFormAddPrebook.formData?.customGPM || 0)':                'k2',
      '(JSONFormAddPrebook.formData?.retail_price || 0)':             'k3',
      'dsPrebookHeader.data[0].unico':                                'k4',
      'JSONFormAddPrebook.formData.up_x_case':                        'k5',
      '(JSONFormAddPrebook.formData?.additional_notes || \'\')':      'k6',
      'JSONFormAddPrebook.formData.sales_price':                      'k7',
      'JSONFormAddPrebook.formData.customBoxQty':                     'k8',
      'JSONFormAddPrebook.sourceData.unico':                          'k9',
      'JSONFormAddPrebook.formData.customGrower_uq':                  'k10',
      '(JSONFormAddPrebook.formData?.upc || \'\')':                   'k11',
      '(JSONFormAddPrebook.formData?.customFood || \'\' )':           'k12',
      '(JSONFormAddPrebook.formData?.food || false)':                 'k13',
      '(JSONFormAddPrebook.formData?.upc_notes || \'\')':             'k14',
      'appsmith.store.loSalesRepInfo[0].unico':                       'k15',
      'JSONFormAddPrebook.formData.customUxCase':                     'k16',
      'JSONFormAddPrebook.formData.instructions':                     'k17',
      '(JSONFormAddPrebook.formData?.boxcode || \'\')':               'k18',
      '(JSONFormAddPrebook.formData?.upc_text || \'\')':              'k19',
      '(JSONFormAddPrebook.formData?.color_breakdown || \'\')':       'k20',
      'JSONFormAddPrebook.formData.case_uq':                          'k21',
      '(JSONFormAddPrebook.formData?.boxcode2 || \'\')':              'k22',
      '(JSONFormAddPrebook.formData?.customCutPoint || 0 )':          'k23',
    },
    {
      k0:  up_x_pack   || 1,
      k1:  '',
      k2:  0,
      k3:  0,
      k4:  prebook_uq,
      k5:  up_x_case   || 1,
      k6:  '',
      k7:  sales_price,
      k8:  qty_boxes,
      k9:  product_uq,
      k10: grower_uq,
      k11: '',
      k12: '',
      k13: false,
      k14: '',
      k15: salesman_uq,
      k16: units_per_case || up_x_case || 1,
      k17: '',
      k18: '',
      k19: '',
      k20: '',
      k21: case_uq,
      k22: '',
      k23: 0,
    }
  );

  if (!rows[0] || rows[0].error) throw new Error(`Insert line failed: ${JSON.stringify(rows[0])}`);
  return rows[0];
}

module.exports = {
  readPrebookHeader,
  searchProduct,
  dateToJulian,
  getDefaultCarrier,
  getShipAddress,
  createPrebookHeader,
  insertPrebookLine,
};

async function readPrebookHeader(prebook_uq) {
  const rows = await callAction(
    '659f60bcb185274a675b81e1',
    { 'appsmith.store.lcPrebook_Uq': 'k0' },
    { k0: prebook_uq }
  );
  return rows[0] || null;
}
