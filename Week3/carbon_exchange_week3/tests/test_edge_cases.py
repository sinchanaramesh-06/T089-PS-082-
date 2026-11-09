"""
Explicit Edge Cases Test Suite (EC-01 through EC-08)
PS-082 Renewable Energy Certificate and Carbon Credit Trading Ledger
Week 3 Deliverable
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest

# Ensure engine is in path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from carbon_exchange.engine import Ledger, run, prorata_allocate, fee_components, Account

DATA = Path(__file__).parents[1] / "data"


def test_ec_01_clearing_lower_price_on_tie(tmp_path):
    """
    EC-01: Clearing where cumulative buy equals cumulative sell exactly at two
    different prices - choose the lower price.
    In SES-01: Cumulative demand = cumulative supply = 1,000 at prices from
    Rs 1,800 to Rs 2,200. Uniform clearing price must be the LOWEST price: Rs 1,800.
    """
    ledger = run(DATA, tmp_path)
    ses01 = next(s for s in ledger.session_summaries if s["session_id"] == "SES-01")
    assert Decimal(ses01["clearing_price"]) == Decimal("1800.0")
    assert ses01["total_filled"] == 1000
    assert ses01["residual_units"] == 0
    assert ses01["band_status"] == "NORMAL"


def test_ec_02_marginal_prorata_one_residual_unit(tmp_path):
    """
    EC-02: Marginal pro-rata leaving 1 residual unit after floor division.
    In SES-02: Clearing price Rs 2,000. Marginal buys total 151 (50, 50, 51) against
    100 marginal sell units.
    Floor division: floor(100*50/151)=33, floor(100*50/151)=33, floor(100*51/151)=33.
    Total allocated = 99 units. Exactly 1 residual unit left unfilled.
    """
    ledger = run(DATA, tmp_path)
    ses02 = next(s for s in ledger.session_summaries if s["session_id"] == "SES-02")
    assert Decimal(ses02["clearing_price"]) == Decimal("2000.0")
    assert ses02["residual_units"] == 1

    # Verify order-level allocations for ENT-05, ENT-06, ENT-07
    results = {r["order_id"]: r for r in ledger.session_results if r["session_id"] == "SES-02"}
    # ORD-033, ORD-034, ORD-035 (or marginal buy orders in SES-02)
    marginal_buys = [r for r in results.values() if r["clearing_price"] in ("2000", "2000.0", "2000.00") and r["side"] == "BUY" and r["decision"] == "PARTIAL_FILL"]
    assert any(r["filled_quantity"] == 33 for r in marginal_buys)


def test_ec_03_march_generation_applied_six_months_last_day(tmp_path):
    """
    EC-03: REC generated in March applied for exactly 6 months later on the last day.
    ISS-029: Generation 2025-03, applied on 2025-09-30 (last day of 6-month window) -> ISSUED.
    ISS-030: Generation 2025-03, applied on 2025-10-01 (1 day late) -> LAPSED.
    """
    ledger = Ledger(DATA, tmp_path)
    ledger.apply_issuance("ISS-029")
    ledger.apply_issuance("ISS-030")

    iss29 = next(r for r in ledger.issuance_results if r["issuance_id"] == "ISS-029")
    assert iss29["decision"] == "ISSUED"
    assert iss29["units_issued"] == 1240
    assert iss29["vintage_month"] == "2025-03"

    iss30 = next(r for r in ledger.issuance_results if r["issuance_id"] == "ISS-030")
    assert iss30["decision"] == "LAPSED"
    assert iss30["units_issued"] == 0
    assert "APPLICATION_AFTER_2025-09-30" in iss30["reason"]


def test_ec_04_solar_retirement_for_non_solar_rejected_before_solar_target(tmp_path):
    """
    EC-04: Solar REC retirement used for non-solar shortfall before solar target
    met - must be REJECTED.
    ENT-04 solar target = 200. With 0 solar retired, RET-003 attempts
    SOLAR_REC_FOR_NON_SOLAR -> REJECTED with reason SOLAR_TARGET_NOT_MET.
    After satisfying solar target, a subsequent substitution is permitted.
    """
    ledger = Ledger(DATA, tmp_path)
    # Attempt before solar target met (RET-012 requests substitution before solar target satisfied)
    ledger.retire("RET-012")
    ret12 = ledger.retirements_done[-1]
    assert ret12["accepted"] is False
    assert ret12["reason"] == "SOLAR_TARGET_NOT_MET"

    # Now satisfy solar target with 200 solar RECs
    ledger.new_lot("ENT-04", "SOLAR_REC", "2025-01", date(2025, 2, 1), date(2028, 1, 31), 250)
    ledger.retire("RET-015")  # Retires 200 solar RECs
    assert ledger.retirements_done[-1]["accepted"] is True

    # Now attempt substitution
    ledger.retire("RET-016")  # Retires 50 solar RECs for non-solar
    assert ledger.retirements_done[-1]["accepted"] is True
    assert ledger.retirements_done[-1]["reason"] == "RETIRED"


def test_ec_05_entity_retiring_exactly_ninety_percent_carries_forward(tmp_path):
    """
    EC-05: Entity retiring exactly 90 percent - carry-forward permitted.
    Entity ENT-03: Solar target = 400, Non-solar target = 600. Total = 1,000.
    Case A: Retires 400 solar + 500 non-solar = 900 (exactly 90.0%) -> CARRY_FORWARD, penalty 0.
    Case B: Retires 400 solar + 499 non-solar = 899 (89.9%) -> SHORTFALL, penalty charged.
    """
    ledger = Ledger(DATA, tmp_path)
    # Case A: Exactly 90.0%
    ledger.retirements_done = [
        dict(accepted=True, counted=True, entity_id="ENT-03", category="SOLAR_REC",
             quantity=400, compliance_year="2025-26"),
        dict(accepted=True, counted=True, entity_id="ENT-03", category="NON_SOLAR_REC",
             quantity=500, compliance_year="2025-26"),
    ]
    report_90 = ledger.compliance("2025-26")
    ent3_row = next(r for r in report_90 if r["entity_id"] == "ENT-03")
    assert ent3_row["shortfall_units"] == 100
    assert ent3_row["carry_forward_units"] == 100
    assert ent3_row["status"] == "CARRY_FORWARD"
    assert Decimal(ent3_row["penalty_amount"]) == Decimal("0.00")

    # Case B: 89.9% (< 90%)
    ledger_b = Ledger(DATA, tmp_path)
    ledger_b.retirements_done = [
        dict(accepted=True, counted=True, entity_id="ENT-03", category="SOLAR_REC",
             quantity=400, compliance_year="2025-26"),
        dict(accepted=True, counted=True, entity_id="ENT-03", category="NON_SOLAR_REC",
             quantity=499, compliance_year="2025-26"),
    ]
    report_89 = ledger_b.compliance("2025-26")
    ent3_row_b = next(r for r in report_89 if r["entity_id"] == "ENT-03")
    assert ent3_row_b["shortfall_units"] == 101
    assert ent3_row_b["carry_forward_units"] == 0
    assert ent3_row_b["status"] == "SHORTFALL"
    # Penalty = 101 shortfall * Rs 3,000 forbearance = Rs 303,000.00
    assert Decimal(ent3_row_b["penalty_amount"]) == Decimal("303000.00")


def test_ec_06_reversal_exceeding_untraded_plus_buffer(tmp_path):
    """
    EC-06: Reversal exceeding untraded holdings plus buffer.
    GEN-05 issued 1,000 NON_SOLAR RECs, sold 900 in SES-01 (100 remaining untraded).
    Reversal of 1,000 units on 2025-12-05:
    1. 100 untraded cancelled.
    2. Buffer = 0 (no buffer for RECs).
    3. Deficit = 900 units owed in rupees at last clearing price (Rs 1,800 from SES-01).
    Total monetary liability = 900 * 1800 = Rs 1,620,000.00.
    Already-retired / transferred units in buyer hands are NOT clawed back.
    """
    ledger = run(DATA, tmp_path)
    gen5 = ledger.accounts["GEN-05"]
    assert gen5.liability == Decimal("1620000.00")
    # Untraded units of generator are cancelled
    assert not any(l.source == "ISS-008" and l.holder == "GEN-05" and l.qty > 0 for l in ledger.lots)
    # Traded buyer certificates are NOT clawed back
    assert any(l.source == "ISS-008" and l.holder in ("ENT-01", "ENT-03") for l in ledger.lots)


def test_ec_07_buy_order_margin_equals_available_fee_makes_account_negative(tmp_path):
    """
    EC-07: Buy order where margin equals exactly available funds, then fee makes
    the account negative.
    1. Account has available funds Rs 116,000.00.
    2. Buy order: 58 units @ Rs 2,000.00 -> Margin = 58 * 2000 = Rs 116,000.00.
    3. Margin matches available funds exactly: Order ACCEPTED, available funds becomes 0.00.
    4. Session clears at Rs 2,000.00. Filled = 58.
    5. Fees: Exchange fee 0.5% (Rs 580.00) + GST 18% (Rs 104.40) = Rs 684.40.
    6. At settlement: Debits Rs 116,684.40. Funds become Rs -684.40.
    7. Account is now negative; subsequent buy orders are REJECTED for INSUFFICIENT_MARGIN.
    """
    ledger = Ledger(DATA, tmp_path)
    # Set up member account with exact funds 116,000.00
    ledger.accounts["ENT-TEST"] = Account("ENT-TEST", Decimal("116000.00"), Decimal("116000.00"))
    ledger.sessions["SES-TEST"] = {
        "session_id": "SES-TEST", "category": "SOLAR_REC", "session_date": "2026-03-25",
        "open_ts": "2026-03-25 13:00:00", "close_ts": "2026-03-25 15:00:00",
        "floor_price": "1000.00", "forbearance_price": "3000.00"
    }
    ledger.open_session("SES-TEST")

    # Seller with 58 units
    ledger.accounts["GEN-TEST"] = Account("GEN-TEST", Decimal("50000.00"), Decimal("50000.00"))
    ledger.new_lot("GEN-TEST", "SOLAR_REC", "2026-01", date(2026, 1, 1), date(2029, 1, 31), 58)

    # Buy order exactly matching available funds
    ledger.orders["ORD-TEST-BUY"] = {
        "order_id": "ORD-TEST-BUY", "session_id": "SES-TEST", "member_id": "ENT-TEST",
        "side": "BUY", "category": "SOLAR_REC", "quantity": "58", "price": "2000.00",
        "order_ts": "2026-03-25 13:10:00"
    }
    ledger.orders["ORD-TEST-SELL"] = {
        "order_id": "ORD-TEST-SELL", "session_id": "SES-TEST", "member_id": "GEN-TEST",
        "side": "SELL", "category": "SOLAR_REC", "quantity": "58", "price": "2000.00",
        "order_ts": "2026-03-25 13:15:00"
    }

    # Order entry: Accepted!
    ledger.enter_order("ORD-TEST-BUY")
    assert ledger.order_states["ORD-TEST-BUY"].decision == "ACCEPTED"
    assert ledger.accounts["ENT-TEST"].blocked == Decimal("116000.00")
    assert ledger.accounts["ENT-TEST"].available == Decimal("0.00")

    ledger.enter_order("ORD-TEST-SELL")
    assert ledger.order_states["ORD-TEST-SELL"].decision == "ACCEPTED"

    # Close and clear session
    ledger.close_session("SES-TEST")
    assert ledger.order_states["ORD-TEST-BUY"].filled == 58
    assert ledger.order_states["ORD-TEST-BUY"].trade_value == Decimal("116000.00")
    assert ledger.order_states["ORD-TEST-BUY"].exchange_fee == Decimal("580.00")
    assert ledger.order_states["ORD-TEST-BUY"].gst == Decimal("104.40")

    # Settle session: Debit makes funds negative (-684.40)
    ledger.settle_session("SES-TEST", "2026-03-26")
    assert ledger.accounts["ENT-TEST"].funds == Decimal("-684.40")
    assert ledger.accounts["ENT-TEST"].available == Decimal("-684.40")

    # Attempt a subsequent buy order: Must be REJECTED due to negative available balance
    ledger.sessions["SES-TEST-2"] = {
        "session_id": "SES-TEST-2", "category": "SOLAR_REC", "session_date": "2026-03-27",
        "open_ts": "2026-03-27 13:00:00", "close_ts": "2026-03-27 15:00:00",
        "floor_price": "1000.00", "forbearance_price": "3000.00"
    }
    ledger.open_session("SES-TEST-2")
    ledger.orders["ORD-TEST-BUY-2"] = {
        "order_id": "ORD-TEST-BUY-2", "session_id": "SES-TEST-2", "member_id": "ENT-TEST",
        "side": "BUY", "category": "SOLAR_REC", "quantity": "10", "price": "1500.00",
        "order_ts": "2026-03-27 13:10:00"
    }
    ledger.enter_order("ORD-TEST-BUY-2")
    assert ledger.order_states["ORD-TEST-BUY-2"].decision == "REJECTED"
    assert ledger.order_states["ORD-TEST-BUY-2"].reason == "INSUFFICIENT_MARGIN"


def test_ec_08_trade_matched_on_expiry_date_is_valid(tmp_path):
    """
    EC-08: Trade matched on the certificate expiry date.
    SES-03 is conducted on 2025-12-31.
    GEN-04 holding HLD-019 (vintage 2022-12, 150 units) expires 2025-12-31.
    Because trading is valid ON the expiry date, FIFO transfers it in SES-03.
    Nightly RUN_EXPIRY on 2025-12-31 must not expire traded units.
    On 2026-01-01, untraded expired units are retired.
    """
    ledger = run(DATA, tmp_path)
    # Check ORD-052 executed on 2025-12-31 in SES-03
    ord52 = next(r for r in ledger.session_results if r["session_id"] == "SES-03" and r["order_id"] == "ORD-052")
    assert ord52["filled_quantity"] == 150
    assert ord52["decision"] == "FILLED"

    # Transferred lot is in ENT-02 registry balances as of 2025-12-31
    ent02_reg = [r for r in ledger.registry_rows if r["as_of_date"] == "2025-12-31"
                 and r["holder_id"] == "ENT-02" and r["vintage_month"] == "2022-12"]
    assert len(ent02_reg) > 0
    assert ent02_reg[0]["quantity"] == 150
