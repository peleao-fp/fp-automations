module.exports = {
  FLEXYMAX_BASE_URL: 'https://app.flexymax.com/api/v1/actions/execute',
  ANONYMOUS_USER_ID: 'ba68aa44-49dc-4dbf-8145-864bb24cd52d',

  ACTIONS: {
    SEARCH_PRODUCT:   '659f60bcb185274a675b81e0',
    CREATE_PREBOOK:   '659f60bcb185274a675b81fc',
    INSERT_LINE:      '659f60bcb185274a675b81f0',
    READ_HEADER:      '659f60bcb185274a675b81e1',
    GET_SHIP_ADDRESS: '659f60bcb185274a675b820a',
    DATE_TO_JULIAN:   '659f60bcb185274a675b8201',
  },

  SALESMAN_UQ:         'C9145113',
  SHIPPING_DAYS_AHEAD: 7,

  // Products that go to BOX prebook (Everyday / glass items)
  BY_BOX_PRODUCTS: [
    'BUBBLE BALL 8 INCHES', 'BUBBLE BALL 6 INCHES', 'BUBBLE BALL 6"',
    'BUBBLE BALL 10INCH', 'BUBBLE BALL 10 INCHES',
    'CLASSIC URN 11 INCHES', 'CLASSIC URN 8 INCHES',
    'CUBE 4X4X4', 'CUBE 5X5X5', 'CUBE 6X6X6',
    'CYLINDER 05X08', 'CYLINDER 05X10',
    'CYLINDER 4 INCHES 4 X 4', 'CYLINDER 5 INCHES 5 X 5',
    'CYLINDER 6 INCHES', 'CYLINDER 6 INCHES - 6 X 6',
    'ROSE VASE 8 INCHES',
  ],

  // Full location config (UNITS + BOX) with hardcoded carriers and warehouses
  LOCATIONS: {
    FLL: {
      UNITS: {
        label:        'Full Pot FLL - Unit HardGoods (3045)',
        customer_uq:  '8D53FD6B',
        shipto_uq:    '37BC4BF7',
        carrier_uq:   'VIY57130',  // GUILLERMO FLL DLVRY
        whouse_uq:    'ICPU0328',  // UNITS-HG-FORT - FT LAUDERDALE
        terms_uq:     'C768DD5B',  // NET 45
      },
      BOX: {
        label:        'Full Pot FLL - Box HardGoods (1187)',
        customer_uq:  'D800E473',
        shipto_uq:    'CE7C32A1',
        carrier_uq:   'VIY57130',  // GUILLERMO FLL DLVRY
        whouse_uq:    'R8Y24414',  // BOX-HG- FORT - FT LAUDERDALE
        terms_uq:     '729D291F',  // 10TH NEXT MONTH
      },
    },
    WPB: {
      UNITS: {
        label:        'WPB HardGoods Units (4341)',
        customer_uq:  '8D96D3B2',
        shipto_uq:    '6C230940',
        carrier_uq:   '5T156327',  // GUILLERMO WPB DLVRY
        whouse_uq:    '9EVR0098',  // WPB HARDGOODS - WEST PALM BEACH
        terms_uq:     'C768DD5B',
      },
      BOX: {
        label:        'WPB HardGoods Boxes (4340)',
        customer_uq:  '5A95DB7D',
        shipto_uq:    '7F9666BD',
        carrier_uq:   '5T156327',  // GUILLERMO WPB DLVRY
        whouse_uq:    '9EVR0098',  // WPB HARDGOODS - WEST PALM BEACH
        terms_uq:     'C768DD5B',
      },
    },
    NPL: {
      UNITS: {
        label:        'Naples HardGoods Units (5272)',
        customer_uq:  '9A8B3BB3',
        shipto_uq:    '36357CDB',
        carrier_uq:   'FJRC8519',  // GUILLE-NPL-DELIVERY
        whouse_uq:    '23L79975',  // NAPLES HARDGOODS - NAPLES
        terms_uq:     'C768DD5B',
      },
      BOX: {
        label:        'Naples HardGoods Boxes (5271)',
        customer_uq:  '54EA7737',
        shipto_uq:    '73D93C8C',
        carrier_uq:   'FJRC8519',  // GUILLE-NPL-DELIVERY
        whouse_uq:    '23L79975',  // NAPLES HARDGOODS - NAPLES
        terms_uq:     'C768DD5B',
      },
    },
    ORL: {
      UNITS: {
        label:        'HG Units MCO - Orlando (6299)',
        customer_uq:  'BC0FED72',
        shipto_uq:    'D3101F70',
        carrier_uq:   '52YK8077',  // AIRSETRANS TRUCK
        whouse_uq:    'TJL56186',  // ORL HG UNITS - ORLANDO
        terms_uq:     'C768DD5B',
      },
      BOX: {
        label:        'HG Boxes MCO - Orlando (6300)',
        customer_uq:  '634994FD',
        shipto_uq:    'B2AFE63D',
        carrier_uq:   '52YK8077',  // AIRSETRANS TRUCK
        whouse_uq:    'U6539357',  // ORL HG BOXES - ORLANDO
        terms_uq:     'C768DD5B',
      },
    },
  },

  // Location detection keywords (keep for parser)
  LOCATION_KEYWORDS: {
    FLL: ['FLL', 'FORT LAUDERDALE', 'LAUDERDALE', 'PMP', 'POMPANO'],
    WPB: ['WPB', 'WEST PALM', 'PALM BEACH'],
    NPL: ['NPL', 'NAPLES', 'NAP'],
    ORL: ['ORL', 'ORLANDO', 'MCO'],
  },
};
