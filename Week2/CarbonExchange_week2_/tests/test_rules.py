from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from carbon_exchange.engine import (
    rec_units, issuance_deadline, expiry_for_vintage, carbon_buffer,
    prorata_allocate, fee_components, Ledger
)

def test_rec_quantity_rounds_down():
    assert rec_units("1000.8") == 1000
    assert rec_units("0.99") == 0

def test_march_application_deadline_is_september_30():
    assert issuance_deadline("2025-03") == date(2025, 9, 30)

def test_vintage_expiry_is_last_day_of_36th_month():
    assert expiry_for_vintage("2022-12") == date(2025, 12, 31)

def test_carbon_buffer_is_five_percent():
    assert carbon_buffer(2000) == 100
    assert carbon_buffer(99) == 4

def test_prorata_floor_leaves_one_unit():
    allocation = prorata_allocate(100, [50, 50, 51])
    assert allocation == [33, 33, 33]
    assert sum(allocation) == 99

def test_buyer_fees():
    f = fee_components(Decimal("200000"), 100, "BUY")
    assert f["exchange_fee"] == Decimal("1000.00")
    assert f["gst_on_fees"] == Decimal("180.00")
    assert f["net_cash"] == Decimal("-201180.00")

def test_seller_fees():
    f = fee_components(Decimal("200000"), 100, "SELL")
    assert f["exchange_fee"] == Decimal("1000.00")
    assert f["registry_fee"] == Decimal("200.00")
    assert f["gst_on_fees"] == Decimal("216.00")
    assert f["net_cash"] == Decimal("198584.00")

def test_solar_substitution_requires_solar_target_first(tmp_path):
    # Exercise the rule directly with a minimal in-memory-like fixture based on the supplied pack.
    data = Path(__file__).parents[1] / "data"
    ledger = Ledger(data, tmp_path)
    # ENT-04 has a solar target of 200. The attempted substitution is rejected before it is met.
    ledger.retire("RET-012")
    assert ledger.retirements_done[-1]["accepted"] is False
    assert ledger.retirements_done[-1]["reason"] == "SOLAR_TARGET_NOT_MET"

def test_supplied_pack_contains_expected_ordered_commands():
    data = Path(__file__).parents[1] / "data"
    lines = [x for x in (data / "commands.txt").read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]
    assert len(lines) == 247
    assert lines[0] == "APPLY_ISSUANCE|ISS-001"
    assert lines[-1] == "PRINT_COMPLIANCE|2025-26"
