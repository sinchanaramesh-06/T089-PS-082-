# PS-082 Carbon Exchange Registry and Settlement Engine — Week 3
## Full Rules, Validation, and Edge Cases

Python 3.10+ command-file-driven trading ledger and settlement engine developed for PS-082 (Renewable Energy Certificate and Carbon Credit Trading Ledger).

---

## 1. Features Implemented in Week 3

- **Full Business-Rule Coverage (BR-01 to BR-17)**:
  - Metered REC issuance with 6-month calendar month-end deadline.
  - Generator accreditation rules with 1-year audit flag gating.
  - Carbon credit issuance with 5% buffer withholding and 3-issuance streak release.
  - Solar vs Non-Solar market segregation and conditional retirement substitution.
  - 36-month vintage expiry with inclusive expiry-date trading.
  - Uniform-price double auction with lower-price tie breaking.
  - Marginal pro-rata allocation with integer floor division and residual unit tracking.
  - Floor (Rs 1,000) and Forbearance (Rs 3,000) bounds and cap-bound pro-rating.
  - Trading fees (0.5% exchange fee, Rs 2/cert registry fee, 18% GST).
  - 100% buy margin blocking, release on rejection/cancel, conversion on settlement.
  - FIFO certificate transfers preserving vintage, issue date, and expiry.
  - RPO target evaluation (10% solar, 15% non-solar), March 31 cutoff, and shortfall penalties.
  - One-time 90% carry-forward allowance.
  - Reversal deficit recovery sequence (untraded $\rightarrow$ buffer $\rightarrow$ cash liability).
  - Order validation, holdings checks, and immutability.
  - Registry snapshot filtering and expiry exclusion.

- **Explicit Edge Cases Handled (EC-01 to EC-08)**:
  - **EC-01**: Clearing price tie-breaking choosing lowest price (SES-01).
  - **EC-02**: Marginal pro-rata leaving 1 residual unit after floor division (SES-02).
  - **EC-03**: March generation applied on exact 6-month last day (ISS-029 vs ISS-030).
  - **EC-04**: Solar retirement substitution rejected before solar target satisfied (RET-003).
  - **EC-05**: Entity retiring exactly 90.0% qualifying for carry-forward vs 89.9% shortfall.
  - **EC-06**: Reversal exceeding untraded + buffer converted to monetary liability (ISS-008).
  - **EC-07**: Buy margin matching available funds; fee debit drives funds negative (-684.40), blocking subsequent buys.
  - **EC-08**: Trade matched on expiry date valid and transferred; unexpired until next day.

---

## 2. Directory Structure

```text
carbon_exchange_week3/
├── data/                             # Input data files
│   ├── parameters.csv                # System band prices, fees, and RPO %
│   ├── generators.csv                # Registered renewable generators
│   ├── entities.csv                  # Obligated entities & consumption
│   ├── opening_holdings.csv          # Initial certificate inventory
│   ├── sessions.csv                  # Auction sessions configuration
│   ├── issuances.csv                 # Metered generation & reduction claims
│   ├── orders.csv                    # Buy and sell order stream
│   ├── retirements.csv               # Compliance retirement requests
│   └── commands.txt                  # Ordered command execution sequence
├── src/
│   └── carbon_exchange/
│       ├── __init__.py
│       ├── cli.py                    # Command-line interface
│       └── engine.py                 # Core trading, settlement & compliance engine
├── tests/
│   ├── test_rules.py                 # Tests for all 17 rules (BR-01 to BR-17)
│   ├── test_edge_cases.py            # Tests for all 8 edge cases (EC-01 to EC-08)
│   └── test_integration.py           # End-to-end simulation & CSV schema checks
├── output/                           # Evaluation output CSV files
├── BR_TRACEABILITY.md                # Complete traceability register
├── WEEK3_SOFTWARE_DESIGN_DOCUMENT.md # Full Week 3 architecture & design document
├── run_all_tests.py                  # Standalone test runner (no dependencies)
└── requirements.txt                  # Python dependencies
```

---

## 3. How to Run

### Setup Environment
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### Run Engine
From the `carbon_exchange_week3` directory:
```bash
python -m carbon_exchange.cli --data data --output output
```

### Run Tests
Using pytest:
```bash
python -m pytest -v
```

Using the standalone runner (runs in standard Python without external libraries):
```bash
python run_all_tests.py
```

---

## 4. Generated Output CSV Files

The engine generates 6 CSV reports in the `--output` directory:
1. `issuance_results.csv`: Outcome of every issuance application.
2. `session_results.csv`: Per-order fills, clearing prices, fees, and net cash.
3. `session_summary.csv`: Per-session uniform price, volume, residual units, and band status.
4. `registry_balances.csv`: Holdings by holder, category, and vintage as of report dates.
5. `compliance_report.csv`: Annual RPO targets, retirements, shortfall, and carry-forward.
6. `member_accounts.csv`: Member funds, blocked margins, and reversal liabilities.
