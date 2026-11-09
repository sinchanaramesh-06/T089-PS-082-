# PS-082 – Renewable Energy Certificate and Carbon Credit Trading Ledger — Sample Data Pack

Prepared by 10 SECONDS for Team T089.

## Files

| File | What it holds | Row count |
|---|---|---|
| `parameters.csv` | Band prices, fees, windows and RPO percentages | 14 data rows |
| `generators.csv` | 8 generators (technology, accreditation, funds) | 8 data rows |
| `entities.csv` | 10 obligated entities (consumption, funds) | 10 data rows |
| `opening_holdings.csv` | Certificates held at the start (vintage, expiry) | 19 data rows |
| `sessions.csv` | 6 trading sessions with category and timings | 6 data rows |
| `issuances.csv` | 40 issuance applications (REC or CARBON) | 40 data rows |
| `orders.csv` | Buy/sell orders for the sessions (applied by ORDER commands) | 149 data rows |
| `retirements.csv` | 30 retirement requests (applied by RETIRE commands) | 30 data rows |
| `commands.txt` | Ordered stream: issuances, audit flag, sessions, orders, cancels, settlement, reversal, retirements, expiry, prints | 247 command lines (excluding comments) |

Row numbers quoted below are 1-based data-row numbers (the header is row 0). Line numbers for `commands.txt` are physical line numbers including comment lines.

## Column reference

Conventions: dates `YYYY-MM-DD`; timestamps `YYYY-MM-DD HH:MM:SS` (24h, IST, no timezone suffix); money in Rs as plain decimals with 2 places (no commas, no symbol); percentages as plain numbers (12.5 means 12.5%); booleans `true`/`false`; IDs uppercase with a fixed prefix.

### `parameters.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| key | string | — | — | — |
| value | decimal/int/date | — | — | — |
| notes | string | — | — | — |

### `generators.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| generator_id | string | GEN-nn | — | — |
| generator_name | string | — | — | — |
| technology | enum | — | SOLAR, WIND, BIOMASS | SOLAR -> SOLAR_REC, else NON_SOLAR_REC |
| capacity_mw | int | MW | — | — |
| accreditation_date | date | — | — | < 1 year at application needs audit_flag |
| audit_flag | bool | — | — | opening value |
| opening_funds | decimal | Rs | — | member account |
| state | string | — | — | — |

### `entities.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| entity_id | string | ENT-nn | — | — |
| entity_name | string | — | — | — |
| annual_consumption_mwh | int | MWh | — | RPO base |
| opening_funds | decimal | Rs | — | — |
| state | string | — | — | — |
| carry_forward_from_prior_year | int | certificates | — | 0 in this pack |

### `opening_holdings.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| holding_id | string | HLD-nnn | — | — |
| holder_id | string | — | generators.csv | — |
| category | enum | — | SOLAR_REC, NON_SOLAR_REC, CARBON | — |
| vintage_month | string | YYYY-MM | — | issuance month |
| issue_date | date | — | — | — |
| expiry_date | date | — | — | last valid day (36 months after end of issuance month) |
| quantity | int | — | — | — |

### `sessions.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| session_id | string | SES-nn | — | — |
| session_date | date | — | — | — |
| category | enum | — | SOLAR_REC, NON_SOLAR_REC | separate markets |
| open_ts | timestamp | — | — | — |
| close_ts | timestamp | — | — | — |
| floor_price | decimal | Rs | — | — |
| forbearance_price | decimal | Rs | — | — |

### `issuances.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| issuance_id | string | ISS-nnn | — | — |
| generator_id | string | — | generators.csv | — |
| certificate_type | enum | — | REC, CARBON | — |
| generation_month | string | YYYY-MM | — | — |
| metered_mwh | decimal | MWh | — | REC: 1 per MWh rounded down |
| verified_tco2e | int | tCO2e | — | CARBON: 1 per tonne, 5% buffer |
| application_date | date | — | — | — |

### `orders.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| order_id | string | ORD-nnn | — | — |
| session_id | string | — | sessions.csv | — |
| member_id | string | — | GEN-nn or ENT-nn | — |
| side | enum | — | BUY, SELL | — |
| category | enum | — | SOLAR_REC, NON_SOLAR_REC | must match the session |
| quantity | int | — | — | — |
| price | decimal | Rs/certificate | — | — |
| order_ts | timestamp | — | — | — |

### `retirements.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| retirement_id | string | RET-nnn | — | — |
| entity_id | string | — | entities.csv | — |
| category | enum | — | SOLAR_REC, NON_SOLAR_REC, SOLAR_REC_FOR_NON_SOLAR | last = use solar certificates against the non-solar target |
| quantity | int | — | — | — |
| retirement_date | date | — | — | — |
| compliance_year | string | — | 2025-26 | — |

## Command file format

`commands.txt` holds one command per line in the form `COMMAND_NAME|arg1|arg2|...`. Commands must be processed strictly in file order. Lines starting with `#` are comments and blank lines are ignored. Every command used in this pack:

| Command | Arguments (in order) | Meaning |
|---|---|---|
| `APPLY_ISSUANCE` | `issuance_id` | Process the issuance row (window, audit, rounding, buffer) |
| `SET_AUDIT_FLAG` | `generator_id|date` | Audit flag set; held issuances of that generator are issued |
| `OPEN_SESSION` | `session_id` | Open order entry |
| `ORDER` | `order_id` | Enter the order row (validate band, holdings, margin) |
| `CANCEL_ORDER` | `order_id|timestamp` | Cancel (rejected after close) |
| `CLOSE_SESSION` | `session_id` | Close and clear (uniform price) |
| `SETTLE_SESSION` | `session_id|date` | T+1 fee and funds settlement |
| `REVERSE` | `issuance_id|quantity|date` | Reversal of an issuance |
| `RETIRE` | `retirement_id` | Process the retirement row |
| `RUN_EXPIRY` | `date` | Expire certificates whose expiry_date is before this date |
| `PRINT_REGISTRY` | `date` | Registry balances by holder, category and vintage |
| `PRINT_COMPLIANCE` | `compliance_year` | Year-end compliance report |

## Planted scenarios

Every edge case in the brief, mapped to the exact record where it occurs, followed by extra traps.

- **EC-01 Clearing where cumulative buy equals cumulative sell exactly at two different prices - choose the lower price**
  - SES-01: buys ENT-01 100@2200 + ENT-03 900@2200 against sells GEN-06 100@1800 + GEN-05 900@1700 (ENT-02 buy 1500 and GEN-07 sell 2600 never cross); cumulative buy = cumulative sell = 1000 at EVERY price from 1800 to 2200 -> the uniform clearing price must be the LOWEST such price, 1800 — `orders.csv SES-01 rows`
- **EC-02 Marginal pro-rata leaving 1 residual unit after floor division**
  - SES-02: clearing price 2000; marginal buys at 2000 total 151 (50, 50, 51) against the 100 marginal sell units -> pro-rata floor(100x50/151)=33, 33, floor(100x51/151)=33 = 99 filled, 1 residual unit unfilled — `orders.csv SES-02 rows (ENT-05, ENT-06, ENT-07)`
- **EC-03 REC generated in March applied for exactly 6 months later on the last day**
  - ISS-029: generation month 2025-03 applied 2025-09-30 = last day of the 6-month window -> issue 1240 RECs (1240.7 rounded down); ISS-030 applied 2025-10-01 -> LAPSED — `issuances.csv rows 29 and 30`
- **EC-04 Solar REC retirement used for non-solar shortfall before solar target met - must be REJECTED**
  - ENT-04 (solar target 200, retired solar so far 0): RET-003 uses SOLAR_REC against the NON_SOLAR target before the solar target is met -> REJECTED; after RET for 200 solar, a later SOLAR_REC_FOR_NON_SOLAR is allowed — `retirements.csv RET-003`
- **EC-05 Entity retiring exactly 90 percent - carry-forward permitted**
  - ENT-03 (4,000 MWh): targets solar 400 / non-solar 600; retires 400 solar and exactly 540 non-solar = 90.0% -> shortfall 60 may be carried forward once (no penalty this year) — `retirements.csv RET-002`
- **EC-06 Reversal exceeding untraded holdings plus buffer**
  - ISS-008: GEN-05 has no opening holdings; it is issued 1,000 NON_SOLAR RECs (vintage 2025-05, no buffer for RECs), sells 900 in SES-01, then REVERSE on 2025-12-05 for the full 1,000: cancel the 100 untraded, buffer 0, GEN-05 owes 900 x last NON_SOLAR clearing price in rupees; units already retired by buyers are not clawed back — `issuances.csv row 8; commands.txt line 93`
- **EC-07 Buy order where margin equals exactly available funds, then fee makes the account negative**
  - ENT-08 opening funds 719,540.00: SES-04 buy 300@2400 fills at 2000 (600,000 + exchange fee 3,000 + GST 540 = 603,540 settled T+1), leaving exactly 116,000.00; its SES-06 buy 58@2000 needs margin exactly 116,000 (accepted, available funds 0); SES-06 clears at 2000 (buys 258 = sells 258 at 2000, ENT-01's 100@1900 keeps 1900 from balancing), so the fee 580 + GST 104.40 takes ENT-08 to -684.40 and blocks further buys — `orders.csv ENT-08 rows in SES-04 (300@2400) and SES-06 (58@2000); entities.csv ENT-08`
- **EC-08 Trade matched on the certificate expiry date**
  - SES-03 is on 2025-12-31; GEN-04 holding HLD-019 (vintage 2022-12, 150 units) expires 2025-12-31 and is its oldest vintage, so FIFO sells it in SES-03 -> the trade is VALID (expiry day); RUN_EXPIRY that night must not expire traded units — `opening_holdings.csv HLD-019; orders.csv GEN-04 sell 150@1500 in SES-03`
- **Extra traps (not in the brief, but realistic):**
  - ISS-023: GEN-08 accredited 2025-06-01 (< 1 year) applies without audit flag -> HELD until SET_AUDIT_FLAG arrives (2025-11-10), then issued — `issuances.csv row 23; commands.txt line 58`
  - GEN-06 carbon issuances: 5% buffer withheld on each (100, 110, 90, 105 credits); after the 3rd consecutive issuance without reversal the buffer so far (300) is released — `issuances.csv rows 3, 7, 17, 20, 25`
  - ENT-10 buy 500@3500 in SES-03 is above forbearance 3000 -> REJECTED at entry; GEN-07 sell @950 in SES-05 is below floor -> REJECTED — `orders.csv ENT-10 row in SES-03; GEN-07 row in SES-05`
  - SES-05: demand 1,000 at the forbearance price 3000 against 600 supply -> all in-band sells clear and the two buys are pro-rated 360/240 — `orders.csv SES-05 rows`
  - GEN-02 sell 99,999 in SES-06 exceeds its unencumbered SOLAR_REC holdings -> REJECTED — `orders.csv GEN-02 row in SES-06`
  - Duplicate order row ORD-041 (identical, twice) -> second ignored — `orders.csv rows 41 and 42`
  - RET-006 dated 2026-04-01 is after 31 March -> does not count for 2025-26 — `retirements.csv RET-006`
  - CANCEL_ORDER ORD-126 at 14:50 before SES-06 close is accepted (margin released); CANCEL_ORDER ORD-100 at 15:00:01 after SES-05 close -> REJECTED — `commands.txt lines 240 and 191`

## What is NOT in this pack

Expected outputs are not provided for this set. Validate your engine with your own test suite against the rules in your brief (BR-01 … BR-nn). A separate hidden input set with the same schema will be used at final evaluation; outputs are compared field-for-field, so follow the column formats above exactly in your own output.

## Output format expected at evaluation

Produce these CSV files (header row, same conventions as above, rows sorted as stated). Where the brief is silent on a format detail the choice below is binding for evaluation.

### `issuance_results.csv`

One row per APPLY_ISSUANCE / SET_AUDIT_FLAG outcome.

Columns, in order: `issuance_id`, `generator_id`, `decision`, `reason`, `units_issued`, `buffer_withheld`, `vintage_month`, `expiry_date`

### `session_results.csv`

One row per order per session (all orders, including rejected).

Columns, in order: `session_id`, `order_id`, `member_id`, `side`, `decision`, `reason`, `quantity`, `filled_quantity`, `clearing_price`, `trade_value`, `exchange_fee`, `registry_fee`, `gst_on_fees`, `net_cash`

### `session_summary.csv`

One row per session.

Columns, in order: `session_id`, `category`, `clearing_price`, `total_filled`, `residual_units`, `band_status`

### `registry_balances.csv`

One row per holder/category/vintage with quantity > 0 per PRINT_REGISTRY date.

Columns, in order: `as_of_date`, `holder_id`, `category`, `vintage_month`, `expiry_date`, `quantity`, `encumbered_quantity`

### `compliance_report.csv`

One row per entity for the compliance year.

Columns, in order: `entity_id`, `consumption_mwh`, `solar_target`, `solar_retired`, `non_solar_target`, `non_solar_retired`, `solar_used_for_non_solar`, `shortfall_units`, `carry_forward_units`, `penalty_amount`, `status`

### `member_accounts.csv`

Final funds position per member.

Columns, in order: `member_id`, `opening_funds`, `blocked_margin`, `available_funds`, `reversal_liability`

Binding choices: `band_status` is NORMAL, FLOOR_BOUND or FORBEARANCE_BOUND; `status` in compliance is COMPLIANT, CARRY_FORWARD or SHORTFALL; the last clearing price for reversal liability is the latest session of the same category; margin blocked = quantity x order price; fees are charged on filled value at the clearing price; a RETIRE for more certificates than the entity holds is REJECTED INSUFFICIENT_HOLDINGS (several bulk retirements are like that on purpose). Bulk orders priced 1000-1200 (buys) and 2600-3000 (sells) never cross and must appear as UNFILLED with margin released.
