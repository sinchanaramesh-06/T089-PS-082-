# PS-082 Carbon Exchange Registry and Settlement Engine — Week 2

Python 3.10+ command-file-driven implementation using the supplied PS-082 sample data pack.

## Contents
- `data/`: the exact 10 uploaded source files
- `src/carbon_exchange/engine.py`: registry, issuance, auction, settlement, retirement, compliance and reporting logic
- `src/carbon_exchange/cli.py`: command-line entry point
- `tests/`: pytest tests for key business-rule calculations and category validation
- `output/`: CSV reports created after a run

## Setup in VS Code

Windows:
```powershell
py -3.10 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
```

macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH=src
```

## Run
From the project root:
```bash
python -m carbon_exchange.cli --data data --output output
```

## Test
```bash
python -m pytest -v
```

## Generated CSV files
- `issuance_results.csv`
- `session_results.csv`
- `session_summary.csv`
- `registry_balances.csv`
- `compliance_report.csv`
- `member_accounts.csv`

## Processing rules
- `commands.txt` is processed strictly in file order.
- Blank lines and lines beginning with `#` are ignored.
- CSV identifiers and sample values are preserved.
- Monetary calculations use `Decimal`.
- Certificate transfers use vintage-first FIFO.
- Expiry is inclusive through the expiry date; `RUN_EXPIRY` expires lots only when `expiry_date < command_date`.

## Assumptions and data-pack conflicts to resolve
1. The README describes ENT-08's SES-04 buy as filling 300 × Rs 2,400 with opening funds of Rs 719,540. However, 300 × Rs 2,400 = Rs 720,000, which exceeds opening funds by Rs 460. The explicit margin rule says 100% of order value is blocked, so this implementation rejects that order for insufficient margin. Confirm the intended evaluator treatment with your mentor.
2. The sample pack says expected output files are not supplied. The engine generates outputs from the written business rules; there is no official output baseline in the uploaded files to compare field-for-field.
3. Carbon buffer withholding is rounded down to whole credits.
4. Uniform-price discovery maximizes executable volume and chooses the lower price when volumes tie. Marginal pro-rata allocation uses floor division and does not redistribute residual units.
5. The 90% carry-forward test is applied to combined solar and non-solar target units; the remaining aggregate shortfall is carried once.
6. The supplied CSV is treated as authoritative if a narrative example in the data-pack README conflicts with a row's actual values.

This is a Week 2 implementation baseline. Run the supplied sample, inspect generated reports, and review the assumptions with the mentor before final evaluation.
