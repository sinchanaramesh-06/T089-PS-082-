"""
Tests for Business Rules BR-01 through BR-17
PS-082 Renewable Energy Certificate and Carbon Credit Trading Ledger
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest

# Ensure engine is in path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from carbon_exchange.engine import (
    rec_units, issuance_deadline, expiry_for_vintage, carbon_buffer,
    prorata_allocate, fee_components, Ledger, run
)

DATA = Path(__file__).parents[1] / "data"


# ==============================================================================
# BR-01: REC issuance ratio and application deadline
# ==============================================================================
def test_br_01_rec_quantity_rounds_down():
    """1 REC per 1 MWh of metered generation, rounding down."""
    assert rec_units("1000.8") == 1000
    assert rec_units("0.99") == 0
    assert rec_units("500.00") == 500
    assert rec_units("1240.7") == 1240


def test_br_01_six_month_application_deadline(tmp_path):
    """Issuance must be applied for within 6 months of generation month."""
    # March 2025 generation deadline is September 30, 2025
    assert issuance_deadline("2025-03") == date(2025, 9, 30)
    # December 2024 generation deadline is June 30, 2025
    assert issuance_deadline("2024-12") == date(2025, 6, 30)

    ledger = Ledger(DATA, tmp_path)
    # ISS-029: March 2025 applied on 2025-09-30 (last day) -> ISSUED
    ledger.apply_issuance("ISS-029")
    assert ledger.issuance_results[-1]["decision"] == "ISSUED"
    assert ledger.issuance_results[-1]["units_issued"] == 1240

    # ISS-030: March 2025 applied on 2025-10-01 (1 day late) -> LAPSED
    ledger.apply_issuance("ISS-030")
    assert ledger.issuance_results[-1]["decision"] == "LAPSED"
    assert "APPLICATION_AFTER" in ledger.issuance_results[-1]["reason"]


# ==============================================================================
# BR-02: Generator accreditation and audit flag
# ==============================================================================
def test_br_02_new_generator_requires_audit_flag(tmp_path):
    """Generator accredited < 1 year requires audit flag before issuance."""
    ledger = Ledger(DATA, tmp_path)
    # GEN-08 accredited 2025-06-01; applied 2025-09-15 (<1 year) with audit_flag false
    ledger.apply_issuance("ISS-023")
    assert ledger.issuance_results[-1]["decision"] == "HELD"
    assert ledger.issuance_results[-1]["reason"] == "AUDIT_REQUIRED"

    # Set audit flag -> held issuance is approved and issued
    ledger.set_audit("GEN-08", "2025-11-10")
    assert ledger.issuance_results[-1]["decision"] == "ISSUED"
    assert ledger.issuance_results[-1]["reason"] == "AUDIT_APPROVED_2025-11-10"


# ==============================================================================
# BR-03: Carbon credit issuance and buffer pool
# ==============================================================================
def test_br_03_carbon_credit_buffer_withholding():
    """1 credit per tonne CO2e; 5% withheld into buffer pool (rounded down)."""
    assert carbon_buffer(2000) == 100
    assert carbon_buffer(99) == 4
    assert carbon_buffer(100) == 5
    assert carbon_buffer(1) == 0


def test_br_03_carbon_issuance_creates_lots_and_buffer(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    ledger.apply_issuance("ISS-003")  # GEN-06: 2000 tCO2e
    res = ledger.issuance_results[-1]
    assert res["decision"] == "ISSUED"
    assert res["units_issued"] == 1900
    assert res["buffer_withheld"] == 100
    assert ledger.carbon_buffer_pool["GEN-06"] == 100


# ==============================================================================
# BR-04: Buffer pool release after 3 consecutive issuances
# ==============================================================================
def test_br_04_buffer_release_after_three_consecutive_issuances(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    # Apply 3 consecutive carbon issuances for GEN-06
    for iid in ["ISS-003", "ISS-007", "ISS-017"]:
        ledger.apply_issuance(iid)
    # After the 3rd, buffer pool is released to the generator
    assert ledger.carbon_buffer_pool["GEN-06"] == 0
    carbon_lots = [l for l in ledger.lots if l.holder == "GEN-06" and l.category == "CARBON"]
    # 1900 + 1900 + 1900 (units) + 100 + 100 + 100 (buffers) = 6000 total credits
    assert sum(l.qty for l in carbon_lots) == 6000


def test_br_04_reversal_resets_streak(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    ledger.apply_issuance("ISS-003")
    ledger.apply_issuance("ISS-007")
    assert ledger.carbon_streak["GEN-06"] == 2
    # Reversal resets streak to 0
    ledger.reverse("ISS-003", 50, "2025-08-01")
    assert ledger.carbon_streak["GEN-06"] == 0
    # Next issuance is count 1, not 3
    ledger.apply_issuance("ISS-017")
    assert ledger.carbon_streak["GEN-06"] == 1
    assert ledger.carbon_buffer_pool["GEN-06"] > 0


# ==============================================================================
# BR-05: Certificate category segregation
# ==============================================================================
def test_br_05_category_mismatch_in_order(tmp_path):
    """Solar and Non-solar are separate markets; order must match session category."""
    ledger = Ledger(DATA, tmp_path)
    ledger.open_session("SES-01")  # SES-01 is NON_SOLAR_REC
    # Attempt an order with SOLAR_REC in SES-01
    ledger.orders["TEST-CAT"] = {
        "order_id": "TEST-CAT", "session_id": "SES-01", "member_id": "ENT-01",
        "side": "BUY", "category": "SOLAR_REC", "quantity": "100",
        "price": "1800.00", "order_ts": "2025-10-15 13:10:00"
    }
    ledger.enter_order("TEST-CAT")
    assert ledger.order_states["TEST-CAT"].decision == "REJECTED"
    assert ledger.order_states["TEST-CAT"].reason == "CATEGORY_MISMATCH"


def test_br_05_solar_satisfies_non_solar_only_after_solar_target_met(tmp_path):
    """Solar REC satisfies non-solar shortfall only after solar target is fully met."""
    ledger = Ledger(DATA, tmp_path)
    # ENT-04 solar target is 200. At start, 0 solar retired.
    ledger.retire("RET-012")  # Attempt SOLAR_REC_FOR_NON_SOLAR before solar target met
    assert ledger.retirements_done[-1]["accepted"] is False
    assert ledger.retirements_done[-1]["reason"] == "SOLAR_TARGET_NOT_MET"


# ==============================================================================
# BR-06: Vintage and expiry (36 months; inclusive on expiry date)
# ==============================================================================
def test_br_06_expiry_calculation():
    """RECs expire 36 months after end of generation/issuance month."""
    assert expiry_for_vintage("2022-12") == date(2025, 12, 31)
    assert expiry_for_vintage("2023-01") == date(2026, 1, 31)
    assert expiry_for_vintage("2024-02") == date(2027, 2, 28)


def test_br_06_trading_valid_on_expiry_day(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    # HLD-019 vintage 2022-12 expires on 2025-12-31
    available_on_expiry = ledger.lots_for("GEN-04", "NON_SOLAR_REC", date(2025, 12, 31))
    assert any(l.lot_id == "HLD-019" for l in available_on_expiry)

    # Expiry run on the night of expiry date does NOT expire the lot
    ledger.run_expiry("2025-12-31")
    assert any(l.lot_id == "HLD-019" and not l.expired for l in ledger.lots)

    # Run expiry next day -> expired
    ledger.run_expiry("2026-01-01")
    assert not any(l.lot_id == "HLD-019" and l.qty > 0 for l in ledger.lots)


# ==============================================================================
# BR-07: Auction clearing at single uniform price
# ==============================================================================
def test_br_07_auction_uniform_clearing(tmp_path):
    """Double auction clears at single uniform price where buy meets sell."""
    # SES-01 clears at Rs 1,800 for 1,000 units
    ledger = run(DATA, tmp_path)
    summary = next(s for s in ledger.session_summaries if s["session_id"] == "SES-01")
    assert Decimal(summary["clearing_price"]) == Decimal("1800.0")
    assert summary["total_filled"] == 1000


# ==============================================================================
# BR-08: Marginal pro-rata allocation and residual units
# ==============================================================================
def test_br_08_marginal_prorata_allocation():
    """Pro-rata floor division across marginal orders leaves residual unfilled."""
    alloc = prorata_allocate(100, [50, 50, 51])
    assert alloc == [33, 33, 33]
    assert sum(alloc) == 99  # 1 residual left unfilled


# ==============================================================================
# BR-09: Floor and forbearance constraints
# ==============================================================================
def test_br_09_order_price_outside_band_rejected(tmp_path):
    """Orders outside Rs 1,000–Rs 3,000 are rejected at entry."""
    ledger = run(DATA, tmp_path)
    res = {r["order_id"]: r for r in ledger.session_results}
    assert res["ORD-096"]["decision"] == "REJECTED"
    assert res["ORD-096"]["reason"] == "PRICE_OUTSIDE_BAND"


# ==============================================================================
# BR-10: Fees and GST
# ==============================================================================
def test_br_10_fees_and_gst():
    """Exchange fee 0.5%, registry fee Rs 2/cert (seller), GST 18% on fees."""
    # Buy side: trade value 200,000, 100 certs
    bf = fee_components(Decimal("200000"), 100, "BUY")
    assert bf["exchange_fee"] == Decimal("1000.00")
    assert bf["registry_fee"] == Decimal("0.00")
    assert bf["gst_on_fees"] == Decimal("180.00")
    assert bf["net_cash"] == Decimal("-201180.00")

    # Sell side: trade value 200,000, 100 certs
    sf = fee_components(Decimal("200000"), 100, "SELL")
    assert sf["exchange_fee"] == Decimal("1000.00")
    assert sf["registry_fee"] == Decimal("200.00")
    assert sf["gst_on_fees"] == Decimal("216.00")
    assert sf["net_cash"] == Decimal("198584.00")


# ==============================================================================
# BR-11: Buy-order margin
# ==============================================================================
def test_br_11_buy_order_margin_blocking(tmp_path):
    """100% margin blocked at entry; rejected if available funds insufficient."""
    ledger = Ledger(DATA, tmp_path)
    ledger.open_session("SES-01")
    # ENT-01 opening funds: 3,000,000. Order: 100 @ 2200 -> margin = 220,000
    ledger.enter_order("ORD-001")
    assert ledger.accounts["ENT-01"].blocked == Decimal("220000.00")
    assert ledger.accounts["ENT-01"].available == Decimal("2780000.00")


# ==============================================================================
# BR-12: FIFO certificate transfer
# ==============================================================================
def test_br_12_fifo_transfer(tmp_path):
    """Oldest vintage lots are consumed and transferred first."""
    ledger = run(DATA, tmp_path)
    # Check that ENT-02 received transferred 2022-12 vintage from GEN-04 in SES-03 on expiry day
    snapshot = [r for r in ledger.registry_rows if r["as_of_date"] == "2025-12-31"
                and r["holder_id"] == "ENT-02" and r["vintage_month"] == "2022-12"]
    assert snapshot and snapshot[0]["quantity"] == 150


# ==============================================================================
# BR-13: RPO targets and shortfall penalty
# ==============================================================================
def test_br_13_rpo_targets_and_penalties(tmp_path):
    """Solar target 10%, non-solar 15%; shortfall penalty = shortfall * 3000."""
    ledger = Ledger(DATA, tmp_path)
    # ENT-01 consumption 10,000 MWh -> solar target = 1,000, non-solar = 1,500
    assert ledger.target("ENT-01", "SOLAR_REC") == 1000
    assert ledger.target("ENT-01", "NON_SOLAR_REC") == 1500


# ==============================================================================
# BR-14: RPO carry-forward
# ==============================================================================
def test_br_14_carry_forward_ninety_percent(tmp_path):
    """Retiring at least 90% allows carrying forward remaining shortfall once."""
    ledger = Ledger(DATA, tmp_path)
    # Synthetic retirement for ENT-03: 400 solar + 540 non-solar = 940 / 1000 = 94% >= 90%
    ledger.retirements_done = [
        dict(accepted=True, counted=True, entity_id="ENT-03", category="SOLAR_REC",
             quantity=400, compliance_year="2025-26"),
        dict(accepted=True, counted=True, entity_id="ENT-03", category="NON_SOLAR_REC",
             quantity=540, compliance_year="2025-26"),
    ]
    comp = ledger.compliance("2025-26")
    ent3_row = next(r for r in comp if r["entity_id"] == "ENT-03")
    assert ent3_row["shortfall_units"] == 60
    assert ent3_row["carry_forward_units"] == 60
    assert ent3_row["status"] == "CARRY_FORWARD"
    assert Decimal(ent3_row["penalty_amount"]) == Decimal("0.00")


# ==============================================================================
# BR-15: Reversal handling
# ==============================================================================
def test_br_15_reversal_creates_cash_liability(tmp_path):
    """Untraded units cancelled first, then deficit creates cash liability at last price."""
    ledger = run(DATA, tmp_path)
    gen5 = ledger.accounts["GEN-05"]
    # 900 deficit * Rs 1,800 last clearing price = Rs 1,620,000 liability
    assert gen5.liability == Decimal("1620000.00")


# ==============================================================================
# BR-16: Order validation and cancellation
# ==============================================================================
def test_br_16_order_validation_and_cancellation(tmp_path):
    ledger = run(DATA, tmp_path)
    results = {r["order_id"]: r for r in ledger.session_results}
    # Excess sell order rejected
    assert results["ORD-122"]["decision"] == "REJECTED"
    assert results["ORD-122"]["reason"] == "INSUFFICIENT_UNENCUMBERED_HOLDINGS"

    # Cancellation before session close succeeds
    assert results["ORD-126"]["decision"] == "CANCELLED"
    assert results["ORD-126"]["reason"] == "MEMBER_CANCELLED"


# ==============================================================================
# BR-17: Expiry processing
# ==============================================================================
def test_br_17_expiry_excludes_from_registry(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    ledger.run_expiry("2026-01-01")
    # All 2022-12 lots should be marked expired
    assert all(l.expired for l in ledger.lots if l.expiry and l.expiry < date(2026, 1, 1))
