import argparse
from pathlib import Path
from .engine import run

def main():
    p=argparse.ArgumentParser(description="PS-082 carbon exchange command-line engine")
    p.add_argument("--data",default="data")
    p.add_argument("--output",default="output")
    a=p.parse_args()
    ledger=run(Path(a.data),Path(a.output))
    print("PS-082 processing complete.")
    print(f"Issuance outcomes: {len(ledger.issuance_results)}")
    print(f"Trading sessions: {len(ledger.session_summaries)}")
    print(f"Retirement requests: {len(ledger.retirements_done)}")
    print(f"Reports: {Path(a.output).resolve()}")

if __name__=="__main__":
    main()
