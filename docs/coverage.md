# Coverage and confidence

Which projects from the two utilities' published plans are on the map, and how well
each one is located. Generated from the committed sources by
`python -m pipeline.build_dataset`, which writes both this report and
`data/seed/projects.csv`, so the two cannot disagree.

**115 of 252 parsed projects are located** and load into the
database. The other 137 are listed in full below, each with
the endpoint that could not be placed — a project with no located endpoint has no
center, so it is left out rather than guessed at.

## Per utility

| Utility | Parsed | Located | Confirmed | Low | Excluded |
| --- | --- | --- | --- | --- | --- |
| Dominion Energy South Carolina | 44 | 28 | 4 | 24 | 16 |
| Georgia Power | 208 | 87 | 35 | 52 | 121 |
| **Total** | **252** | **115** | **39** | **76** | **137** |

- **Parsed** — projects read out of the utility's own plan document into
  `data/seed/desc_projects.csv` / `gpc_projects.csv`.
- **Located** — projects with a center, written to `data/seed/projects.csv`:
  Parsed = Located + Excluded, per utility and overall.
- **Confirmed** — every endpoint in the project's name is a unique, exact-name match
  on an operator-tagged OpenStreetMap substation.
- **Low** — the project has a center, but at least one endpoint is placed less
  certainly: an OSM record with no `operator` tag, a hand-entered coordinate from
  `data/seed/location_overrides.csv`, the same-named candidate nearest the line's
  other end, or an endpoint that could not be placed at all (the center then rests
  on the other end). `low` does not mean the project is in the wrong place; it means
  the match is not self-evident.
- **Excluded** — no endpoint could be placed, so there is nothing to map.

## Why projects are excluded

| Reason | Count | What it means |
| --- | --- | --- |
| `ambiguous` | 2 | an endpoint's name fits several far-apart OSM substations, so none can be picked |
| `unlocated` | 129 | no OSM substation (and no manual override) matches any endpoint of the project |
| `wrong_state` | 6 | the only match lands more than 10 mi inside the other utility's state |

## Excluded projects

### Dominion Energy South Carolina — 16 of 44

| Project ID | Reason | Project | Endpoints tried |
| --- | --- | --- | --- |
| `0167C-D` | `unlocated` | Union Pier 115-13.8 kV Sub: Tap | 'Union Pier': no OSM substation |
| `6808 J` | `unlocated` | Eastover - Square D 115kV: Rebuild | 'Eastover': no OSM substation; 'Square D': no OSM substation |
| `6808 K` | `ambiguous` | Burton-St Helena 115kV: Rebuild Burton-Frogmore Transmission Section | 'Burton': 2 far-apart candidates; 'St Helena': no OSM substation |
| `6808 L` | `ambiguous` | Burton-St Helena 115kV: Frogmore Distribution - St Helena | 'Burton': 2 far-apart candidates; 'St Helena': no OSM substation |
| `6808 U` | `unlocated` | Hopkins-CIP 230kV: Rebuild | 'Hopkins': no OSM substation; 'CIP': no OSM substation |
| `6808 W` | `unlocated` | Square D - Hopkins 115kV: Rebuild | 'Square D': no OSM substation; 'Hopkins': no OSM substation |
| `6805 G` | `unlocated` | Edenwood Sub: #1 & #2 230-115kV Autobanks, Replace with 336MVA | 'Edenwood': no OSM substation |
| `1060A, I, L` | `unlocated` | Williams St Sub: Replace Sw House & Relays, AM Williams Sub: Replace Sw House, and McMeekin Sub: Add Sw House | 'Williams St': no OSM substation |
| `05004 P` | `unlocated` | Summerville: Replace and Spare 230-115kV 336MVA Auto Bank | 'Summerville': no OSM substation |
| `06367 A - C, H` | `unlocated` | Riverport Tap: Construct Tap | 'Riverport': no OSM substation |
| `06810 G` | `unlocated` | Goose Creek Reservoir: Rebuild Transmission Line Crossings | 'Goose Creek Reservoir': no OSM substation |
| `06810 H` | `unlocated` | Summerville 115kV Loop: Rebuild | 'Summerville': no OSM substation |
| `5392 A-C` | `unlocated` | Coit – Gills Creek 115kV: Construct | 'Coit': no OSM substation; 'Gills Creek': no OSM substation |
| `6853 B-F` | `unlocated` | Scout 230 kV Sub and Fold-in: Construct | 'Scout': no OSM substation |
| `6859` | `unlocated` | Dawson 230kV Sub and Fold-in: Construct and Rebuild | 'Dawson': no OSM substation |
| `6810 T` | `unlocated` | Cameron Jct – Cameron – St Matthews 46 kV Rebuild | 'Cameron Jct': no OSM substation; 'St Matthews': no OSM substation |

### Georgia Power — 121 of 208

| Project ID | Reason | Project | Endpoints tried |
| --- | --- | --- | --- |
| `18670` | `unlocated` | GTC: BANKS CROSSING - POND FORK 115 KV | 'BANKS CROSSING': no OSM substation; 'POND FORK': no OSM substation |
| `19676` | `unlocated` | ADAMSVILLE - JACK MCDONOUGH 230KV LINE REBUILD | 'ADAMSVILLE': no OSM substation; 'JACK MCDONOUGH': no OSM substation |
| `18800` | `unlocated` | ECHECONNEE-WELLSTON 115KV REBUILD | 'ECHECONNEE': no OSM substation; 'WELLSTON': no OSM substation |
| `19187` | `unlocated` | GRID - BREMEN - CROOKED CREEK (APC) 115 KV PROJECT | 'BREMEN': no OSM substation; 'CROOKED CREEK': no OSM substation |
| `18153` | `unlocated` | GTC: BONAIRE PRI-ECHECONNEE 115 KV PARTIAL REBUILD | 'BONAIRE PRI': no OSM substation; 'ECHECONNEE': no OSM substation |
| `20342` | `unlocated` | GTC: CAMDEN INDUSTRIAL PARK 230/115KV NEW SUBSTATION | 'CAMDEN INDUSTRIAL PARK': no OSM substation |
| `20590` | `unlocated` | GTC: EATONTON PRIMARY - LICK CREEK 115KV LINE SWITCH REPLACEMENT | 'EATONTON PRIMARY': no OSM substation; 'LICK CREEK': no OSM substation |
| `13753` | `unlocated` | MEAG: ALCOVY ROAD - SKC 115 KV RECONDUCTOR | 'ALCOVY ROAD': no OSM substation; 'SKC': no OSM substation |
| `20466` | `unlocated` | SMART VALVE INSTALLATION | 'SMART VALVE': no OSM substation |
| `20431` | `unlocated` | VILLA RICA LOW SIDE BREAKER | 'VILLA RICA LOW SIDE': no OSM substation |
| `20684` | `unlocated` | CAMDEN INDUSTRIAL PARK (GPC) | 'CAMDEN INDUSTRIAL PARK': no OSM substation |
| `18774` | `unlocated` | GTC: HEARD COUNTY - TENASKA 500KV (SECOND LINE) | 'HEARD COUNTY': no OSM substation; 'TENASKA': no OSM substation |
| `18889` | `unlocated` | JEFFERSON STREET#3 - NORTHWEST (WHITE) 115 KV RECONDUCTOR | 'JEFFERSON STREET#3': no OSM substation; 'NORTHWEST': no OSM substation |
| `20326` | `unlocated` | ANTHONY SHOALS STATCOM SYSTEM | 'ANTHONY SHOALS STATCOM SYSTEM': no OSM substation |
| `20152` | `unlocated` | CC - CASS PINE- HILL VIEW 230 KV LINE- CC IMPROVEMENTS | 'CASS PINE': no OSM substation; 'HILL VIEW': no OSM substation |
| `20175` | `unlocated` | CC - PROJECT CHRONOS- SK/HYUNDAI | 'PROJECT CHRONOS': no OSM substation; 'SK': no OSM substation |
| `18691` | `unlocated` | GTC: LIZARD LOPE - WESTOVER 115 KV NEW LINE | 'LIZARD LOPE': no OSM substation; 'WESTOVER': no OSM substation |
| `20018` | `unlocated` | CC - QTS FAYETTEVILLE TRANSMISSION NEEDS | 'QTS FAYETTEVILLE': no OSM substation |
| `19597` | `wrong_state` | ADAMSVILLE - BUZZARD ROOST 230KV REBUILD AND JUMPER UPGRADE | 'ADAMSVILLE': no OSM substation; 'BUZZARD ROOST': only match 'Buzzard Roost Dam Substation' is in the other state |
| `20243` | `unlocated` | CC - GARRETT ROAD SWITCHING STATION - TRAE LANE | 'GARRETT ROAD SWITCHING STATION': no OSM substation; 'TRAE LANE': no OSM substation |
| `20216` | `unlocated` | CC - STONEWALL TELL ROAD (TA REALTY) | 'STONEWALL TELL ROAD': no OSM substation |
| `18679` | `unlocated` | DU: EAST DALTON - OOSTANAULA 115KV REBUILD | 'EAST DALTON': no OSM substation; 'OOSTANAULA': no OSM substation |
| `20491` | `unlocated` | EAST POINT RELAY MODERNIZATION | 'EAST POINT': no OSM substation |
| `16007` | `unlocated` | FENWICK STREET - SAND BAR FERRY 115KV (RECONDUCTOR/REBUILD) | 'FENWICK STREET': no OSM substation; 'SAND BAR FERRY': no OSM substation |
| `20516` | `unlocated` | GOAT ROCK 230KV SWITCH, JUMPER, & LINE TRAP REPLACEMENT | 'GOAT ROCK': no OSM substation |
| `20474` | `unlocated` | GRADY 230/115KV RELAY MODERNIZATION | 'GRADY': no OSM substation |
| `19706` | `unlocated` | GRID - GAINESVILLE #2 EQUIPMENT REPLACEMENT | 'GAINESVILLE #2': no OSM substation |
| `21137` | `unlocated` | GTC: CONYERS - CORNISH MOUNTAIN 115KV LINE UPGRADE | 'CONYERS': no OSM substation; 'CORNISH MOUNTAIN': no OSM substation |
| `19334` | `unlocated` | GTC: LAGRANGE - NORTH OPELIKA 230 KV | 'LAGRANGE': no OSM substation; 'NORTH OPELIKA': no OSM substation |
| `20015` | `unlocated` | GTC: MORNING HORNET 2ND 230/115 KV BANK & THUMBS UP 115KV TL | 'MORNING HORNET 2ND': no OSM substation |
| `19636` | `wrong_state` | HAMMOND - WEISS DAM 115KV LINE REBUILD | 'HAMMOND': only match 'Hammonds Substation' is in the other state; 'WEISS DAM': no OSM substation |
| `20512` | `unlocated` | KATHLEEN AREA IMPROVEMENTS | 'KATHLEEN AREA': no OSM substation |
| `20270` | `unlocated` | MEAG: RAY PLACE RD - WASHINGTON #3 | 'RAY PLACE RD': no OSM substation; 'WASHINGTON #3': no OSM substation |
| `20271` | `unlocated` | MEAG: RAY PLACE RD - WASHINGTON (WASHINGTON - WASHINGTON 3) | 'RAY PLACE RD': no OSM substation; 'WASHINGTON': no OSM substation |
| `18690` | `unlocated` | PALMYRA REACTOR REMOVAL | 'PALMYRA REACTOR': no OSM substation |
| `19966` | `unlocated` | SAV: CC - BIG OGEECHEE 500/230KV (CC NETWORK IMPROVEMENTS) | 'BIG OGEECHEE': no OSM substation |
| `20489` | `unlocated` | SCOTTDALE RELAY MODERNIZATION | 'SCOTTDALE': no OSM substation |
| `17900` | `unlocated` | UNION CITY - YATES 230 KV WHITE LINE REBUILD | 'UNION CITY': no OSM substation; 'YATES': no OSM substation |
| `20691` | `unlocated` | UNION CITY - YATES 230KV (WHITE) SWITCH AND TRAP REPLACEMENT | 'UNION CITY': no OSM substation; 'YATES': no OSM substation |
| `20223` | `unlocated` | CC - PROJECT PAYTON BAINBRIDGE | 'PROJECT PAYTON BAINBRIDGE': no OSM substation |
| `21022` | `unlocated` | OHARA BREAKER REPLACEMENT | 'OHARA': no OSM substation |
| `20668` | `unlocated` | DRESDEN LINE PROTECTIVE RELAYING | 'DRESDEN LINE PROTECTIVE RELAYING': no OSM substation |
| `20273` | `unlocated` | GTC: DRESDEN 500KV BUS EXPANSION | 'DRESDEN': no OSM substation |
| `20151` | `unlocated` | CC - CASS PINE 230/25 NEW SUB - QCELLS - CC IMPROVEMENTS | 'CASS PINE': no OSM substation |
| `19287` | `unlocated` | GRADY-WEST END 115KV REBUILD | 'GRADY': no OSM substation; 'WEST END': no OSM substation |
| `18832` | `unlocated` | MEAG: FORTSON SUBSTATION MODERNIZATION | 'FORTSON': no OSM substation |
| `20509` | `unlocated` | CC - EMBLEM RIVERSIDE CUSTOMER SUB (FLEXENTIAL) | 'EMBLEM RIVERSIDE CUSTOMER': no OSM substation |
| `19635` | `unlocated` | GTC: HICKORY LEVEL - VILLA RICA 230KV LINE RECONDUCTOR | 'HICKORY LEVEL': no OSM substation; 'VILLA RICA': no OSM substation |
| `20771` | `unlocated` | CC - GULLATT ROAD TRANSMISSION IMPROVEMENTS | 'GULLATT ROAD': no OSM substation |
| `18736` | `unlocated` | CC - MICROSOFT - SHUGART (CCO06) | 'MICROSOFT': no OSM substation; 'SHUGART': no OSM substation |
| `20781` | `unlocated` | CC - SUMMER LAKE - VILLA RICA 230KV REBUILD (CC IMPROVEMENT) | 'SUMMER LAKE': no OSM substation; 'VILLA RICA': no OSM substation |
| `20736` | `unlocated` | CC - TA REALTY ELLENWOOD NETWORK IMPROVEMENTS | 'TA REALTY ELLENWOOD NETWORK': no OSM substation |
| `20858` | `wrong_state` | GTC: ADAMSVILLE - BUZZARD ROOST 230KV REBUILD | 'ADAMSVILLE': no OSM substation; 'BUZZARD ROOST': only match 'Buzzard Roost Dam Substation' is in the other state |
| `20776` | `unlocated` | GTC: DOUGLASVILLE - VILLA RICA 230KV REBUILD (CC IMPROVEMENT) | 'DOUGLASVILLE': no OSM substation; 'VILLA RICA': no OSM substation |
| `09662` | `unlocated` | GTC: EAST WALTON 500/230KV PROJECT | 'EAST WALTON': no OSM substation |
| `20505` | `unlocated` | GTC: GARRETT RD - V. RICA 230KV LINE RECONDUCTOR (CC NET IM) | 'GARRETT RD': no OSM substation; 'V. RICA': no OSM substation |
| `19622` | `unlocated` | GTC: RIDDLEVILLE BUS REPLACEMENT | 'RIDDLEVILLE': no OSM substation |
| `19606` | `unlocated` | GTC: SKC 115KV BUS AND JUMPER REPLACEMENT | 'SKC': no OSM substation |
| `20506` | `unlocated` | GTC: SWITCH WAY - THORNTON ROAD 230KV LINE REBUILD | 'SWITCH WAY': no OSM substation; 'THORNTON ROAD': no OSM substation |
| `19248` | `unlocated` | SANDERSVILLE #1 - WADLEY PRI. 115KV REBUILD/RECONDUCTOR | 'SANDERSVILLE #1': no OSM substation; 'WADLEY PRI': no OSM substation |
| `20717` | `unlocated` | CC - TOMOCHICHI 500/230KV SOLUTION (CC NETWORK IMPROVEMENTS) | 'TOMOCHICHI': no OSM substation |
| `18573` | `unlocated` | GRID - ARKWRIGHT - LLOYD SHOALS 115KV | 'ARKWRIGHT': no OSM substation; 'LLOYD SHOALS': no OSM substation |
| `20591` | `unlocated` | GTC: EATONTON PRIMARY (035591) - LICK CREEK 115KV REBUILD | 'EATONTON PRIMARY': no OSM substation; 'LICK CREEK': no OSM substation |
| `20150` | `unlocated` | CC - HILL VIEW & GRASSY HOLLOW SUB - CC IMPROVEMENTS | 'HILL VIEW': no OSM substation |
| `20024` | `unlocated` | DYER ROAD - EAST ROANOKE 115KV (REBUILD) | 'DYER ROAD': no OSM substation; 'EAST ROANOKE': no OSM substation |
| `19997` | `unlocated` | AULTMAN ROAD-PERRY 115KV LINE REBUILD | 'AULTMAN ROAD': no OSM substation; 'PERRY': no OSM substation |
| `20797` | `unlocated` | CC - EAST VILLA RICA AREA SWITCHING STATION (CC IMPROVEMENT) | 'EAST VILLA RICA AREA SWITCHING STATION': no OSM substation |
| `20774` | `unlocated` | CC - VILLA RICA UPGRADES (CC NETWORK IMPROVEMENTS) | 'VILLA RICA': no OSM substation |
| `21048` | `unlocated` | FITZGERALD - PITTS 115 KV LINE REBUILD | 'FITZGERALD': no OSM substation; 'PITTS': no OSM substation |
| `19992` | `unlocated` | GTC: BOSTWICK - EAST SOCIAL CIRCLE 230KV RECONDUCTOR | 'BOSTWICK': no OSM substation; 'EAST SOCIAL CIRCLE': no OSM substation |
| `20777` | `unlocated` | JACK MCDONOUGH - NORTHWEST (BLACK) 230KV RECONDUCTOR | 'JACK MCDONOUGH': no OSM substation; 'NORTHWEST': no OSM substation |
| `19630` | `unlocated` | MEAG: THOMASVILLE 230/115KV AUTOBANK REPLACEMENT | 'THOMASVILLE': no OSM substation |
| `20482` | `unlocated` | PITTMAN ROAD - WEST POINT DAM (USA) 115KV REBUILD | 'PITTMAN ROAD': no OSM substation; 'WEST POINT DAM': no OSM substation |
| `20656` | `unlocated` | PLANT YATES BREAKER AND HALF STATION | 'PLANT YATES': no OSM substation |
| `21069` | `unlocated` | SMART VALVES AT EAST VILLA RICA SWITCHING STATION | 'SMART VALVES AT EAST VILLA RICA SWITCHING STATION': no OSM substation |
| `20274` | `unlocated` | UNION CITY - YATES 230KV (BLACK) LINE REBUILD | 'UNION CITY': no OSM substation; 'YATES': no OSM substation |
| `13166` | `unlocated` | FIRST AVENUE - NORTH COLUMBUS 115KV LINE REBUILD | 'FIRST AVENUE': no OSM substation; 'NORTH COLUMBUS': no OSM substation |
| `20586` | `unlocated` | GTC: NORTH DUBLIN 230/115KV TRANSFORMERS AND BUS-TIE BREAKER | 'NORTH DUBLIN': no OSM substation |
| `21062` | `unlocated` | ASHLEY PARK-WANSLEY 500KV | 'ASHLEY PARK': no OSM substation; 'WANSLEY': no OSM substation |
| `21047` | `unlocated` | BROADWAY - ECHECONNEE 115 KV LINE REBUILD | 'BROADWAY': no OSM substation; 'ECHECONNEE': no OSM substation |
| `21036` | `wrong_state` | BUZZARD ROOST - FACTORY SHOALS 230KV NEW LINE | 'BUZZARD ROOST': only match 'Buzzard Roost Dam Substation' is in the other state; 'FACTORY SHOALS': no OSM substation |
| `21138` | `unlocated` | GLENWOOD SPRINGS - PORTERDALE PRIMARY 230KV LINE SWITCH REPL | 'GLENWOOD SPRINGS': no OSM substation; 'PORTERDALE PRIMARY': no OSM substation |
| `20849` | `unlocated` | GTC: CLIFTONDALE - LINE CREEK 230KV LINE | 'CLIFTONDALE': no OSM substation; 'LINE CREEK': no OSM substation |
| `19950` | `unlocated` | GTC: DRESDEN - TALBOT 500KV LINE | 'DRESDEN': no OSM substation; 'TALBOT': no OSM substation |
| `21123` | `unlocated` | GTC: TENASKA - WANSLEY 500KV NEW LINE | 'TENASKA': no OSM substation; 'WANSLEY': no OSM substation |
| `21141` | `unlocated` | LLOYD SHOALS - PORTERDALE PRIMARY 115KV REBUILD | 'LLOYD SHOALS': no OSM substation; 'PORTERDALE PRIMARY': no OSM substation |
| `20285` | `unlocated` | LOWER RIVER - WEBB (APC) 115KV RECONDUCTOR | 'LOWER RIVER': no OSM substation; 'WEBB': no OSM substation |
| `17706` | `unlocated` | MEAG: AULTMAN ROAD - FORT VALLEY #1 115 KV REBUILD | 'AULTMAN ROAD': no OSM substation; 'FORT VALLEY #1': no OSM substation |
| `11051` | `unlocated` | MEAG: SLAPPEY DRIVE - WESTOVER 115KV LINE REBUILD | 'SLAPPEY DRIVE': no OSM substation; 'WESTOVER': no OSM substation |
| `20989` | `unlocated` | SAV: RICE HOPE NEW AUTO TRANSFORMER | 'RICE HOPE NEW AUTO TRANSFORMER': no OSM substation |
| `21129` | `wrong_state` | ANNISTON - HAMMOND 230KV LINE | 'ANNISTON': no OSM substation; 'HAMMOND': only match 'Hammonds Substation' is in the other state |
| `20764` | `unlocated` | ATKINSON - NORTHSIDE DRIVE 115KV REBUILD | 'ATKINSON': no OSM substation; 'NORTHSIDE DRIVE': no OSM substation |
| `20761` | `unlocated` | ATKINSON - NORTHWEST 115KV REBUILD | 'ATKINSON': no OSM substation; 'NORTHWEST': no OSM substation |
| `21130` | `unlocated` | CC - NORTH GEORGIA DATA NETWORK UPGRADES | 'NORTH GEORGIA DATA NETWORK': no OSM substation |
| `10478` | `unlocated` | CORNELIA - TALLULAH LODGE 115KV REBUILD | 'CORNELIA': no OSM substation; 'TALLULAH LODGE': no OSM substation |
| `21097` | `unlocated` | EAST POINT - TRIBUTARY 230KV REBUILD | 'EAST POINT': no OSM substation; 'TRIBUTARY': no OSM substation |
| `20480` | `unlocated` | EAST POINT - UNION CITY 230KV BLACK LINE RECONDUCTOR | 'EAST POINT': no OSM substation; 'UNION CITY': no OSM substation |
| `19627` | `unlocated` | ECHECONNEE-WELLSTON 115KV LINE REBUILD | 'ECHECONNEE': no OSM substation; 'WELLSTON': no OSM substation |
| `21063` | `unlocated` | FARLEY (APC)-TAZEWELL 500KV | 'FARLEY': no OSM substation; 'TAZEWELL': no OSM substation |
| `21128` | `unlocated` | GOAT ROCK REACTORS INSTALLATION | 'GOAT ROCK REACTORS': no OSM substation |
| `21116` | `unlocated` | GOSHEN AREA STRATEGIC SOLUTION | 'GOSHEN AREA STRATEGIC SOLUTION': no OSM substation |
| `21073` | `unlocated` | GTC: BIG SMARR - TOMOCHICHI 500KV | 'BIG SMARR': no OSM substation; 'TOMOCHICHI': no OSM substation |
| `21014` | `wrong_state` | GTC: BUZZARD ROOST - CAVENDER DRIVE 230KV NEW LINE | 'BUZZARD ROOST': only match 'Buzzard Roost Dam Substation' is in the other state; 'CAVENDER DRIVE': no OSM substation |
| `21013` | `unlocated` | GTC: CAVENDER DRIVE 500/230KV AUTOBANK | 'CAVENDER DRIVE': no OSM substation |
| `21111` | `unlocated` | GTC: HARTWELL DAM - HARTWELL ENERGY 230KV SERIES REACTORS | 'HARTWELL DAM': no OSM substation; 'HARTWELL ENERGY': no OSM substation |
| `21113` | `unlocated` | GTC: HARTWELL ENERGY - MIDDLE FORK 230KV LINE | 'HARTWELL ENERGY': no OSM substation; 'MIDDLE FORK': no OSM substation |
| `21131` | `unlocated` | GTC: POND FORK - MIDWAY 115KV LINE | 'POND FORK': no OSM substation; 'MIDWAY': no OSM substation |
| `21076` | `unlocated` | GTC: TALBOT #2 - TAZEWELL 500KV LINE | 'TALBOT #2': no OSM substation; 'TAZEWELL': no OSM substation |
| `20857` | `unlocated` | NEW CAVENDER DRIVE - TRIBUTARY 230KV LINE | 'NEW CAVENDER DRIVE': no OSM substation; 'TRIBUTARY': no OSM substation |
| `21093` | `unlocated` | NORTH SPA 230KV STRATEGIC PROJECT | 'NORTH SPA': no OSM substation |
| `19995` | `unlocated` | TALLULAH LODGE - TOCCOA 115 KV REBUILD | 'TALLULAH LODGE': no OSM substation; 'TOCCOA': no OSM substation |
| `21098` | `unlocated` | TRIBUTARY - THORNTON RD 230KV REBUILD | 'TRIBUTARY': no OSM substation; 'THORNTON RD': no OSM substation |
| `20160` | `unlocated` | THOMASTON 230 NEW BUILD SUB | 'THOMASTON 230 NEW BUILD': no OSM substation |
| `19626` | `unlocated` | GLENWOOD SPRINGS 115KV CAP BANK | 'GLENWOOD SPRINGS': no OSM substation |
| `20690` | `unlocated` | EAST POINT - UNION CITY (WHITE) 230KV REBUILD | 'EAST POINT': no OSM substation; 'UNION CITY': no OSM substation |
| `10811` | `unlocated` | BOWEN #10 500/230KV AUTOBANK REPLACEMENT | 'BOWEN #10': no OSM substation |
| `21099` | `unlocated` | MEAG: PIO NONO 230/115KV AREA SOLUTION | 'PIO NONO': no OSM substation |
| `21114` | `unlocated` | MEAG: SOUTH GRIFFIN 230/115KV BANK #5 | 'SOUTH GRIFFIN': no OSM substation |
| `20767` | `unlocated` | ARKWRIGHT BUS AND JUMPER REPLACEMENT | 'ARKWRIGHT': no OSM substation |
| `21075` | `unlocated` | GTC: EAST WALTON - MIDDLE FORK 500KV | 'EAST WALTON': no OSM substation; 'MIDDLE FORK': no OSM substation |
| `09661` | `unlocated` | MCGRAU FORD - MIDDLE FORK 500KV LINE PROJECT | 'MCGRAU FORD': no OSM substation; 'MIDDLE FORK': no OSM substation |
