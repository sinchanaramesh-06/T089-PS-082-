
from pathlib import Path
from decimal import Decimal
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from carbon_exchange.engine import Ledger, run

DATA = Path(__file__).parents[1] / "data"

def test_sample_command_stream_completes_and_writes_reports(tmp_path):
    ledger = run(DATA, tmp_path)
    assert len(ledger.session_summaries) == 6
    assert len(ledger.retirements_done) == 30
    for name in ["issuance_results.csv","session_results.csv","session_summary.csv",
                 "registry_balances.csv","compliance_report.csv","member_accounts.csv"]:
        assert (tmp_path / name).exists()

def test_march_last_day_is_issued_and_next_day_lapses(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    ledger.apply_issuance("ISS-029")
    ledger.apply_issuance("ISS-030")
    assert ledger.issuance_results[-2]["decision"] == "ISSUED"
    assert ledger.issuance_results[-2]["units_issued"] == 1240
    assert ledger.issuance_results[-1]["decision"] == "LAPSED"

def test_new_generator_issuance_is_held_then_issued_after_audit(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    ledger.apply_issuance("ISS-023")
    assert ledger.issuance_results[-1]["decision"] == "HELD"
    ledger.set_audit("GEN-08", "2025-11-10")
    assert ledger.issuance_results[-1]["decision"] == "ISSUED"
    assert ledger.issuance_results[-1]["reason"] == "AUDIT_APPROVED_2025-11-10"

def test_carbon_buffer_releases_after_third_consecutive_issuance(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    for iid in ["ISS-003", "ISS-007", "ISS-017"]:
        ledger.apply_issuance(iid)
    assert ledger.carbon_buffer_pool["GEN-06"] == 0
    carbon_lots = [x for x in ledger.lots if x.holder=="GEN-06" and x.category=="CARBON"]
    assert sum(x.qty for x in carbon_lots) == 6000

def test_reversal_cancels_untraded_units_and_records_cash_liability(tmp_path):
    ledger = run(DATA, tmp_path)
    gen5 = ledger.accounts["GEN-05"]
    assert gen5.liability == 900 * 1800
    # The liability is recorded against the generator; traded buyer certificates are not clawed back.
    assert gen5.funds < gen5.opening + DecimalLike(1)

def test_auction_uses_lower_exact_intersection_and_pro_rata_residual(tmp_path):
    ledger = run(DATA, tmp_path)
    summaries = {x["session_id"]:x for x in ledger.session_summaries}
    assert DecimalLike(summaries["SES-01"]["clearing_price"]) == 1800
    assert DecimalLike(summaries["SES-02"]["clearing_price"]) == 2000
    assert summaries["SES-02"]["residual_units"] == 1

def DecimalLike(x):
    from decimal import Decimal
    return Decimal(str(x))

def test_expiry_day_trade_is_valid_and_lot_remains_until_next_day(tmp_path):
    ledger = run(DATA, tmp_path)
    rows = [r for r in ledger.session_results if r["session_id"]=="SES-03" and r["order_id"]=="ORD-052"]
    assert rows and rows[0]["filled_quantity"] == 150
    # HLD-019's 2022-12 vintage is transferred on its final valid day.
    snapshot = [r for r in ledger.registry_rows if r["as_of_date"]=="2025-12-31"
                and r["holder_id"]=="ENT-02" and r["vintage_month"]=="2022-12"]
    assert snapshot and snapshot[0]["quantity"] == 150
    ledger2 = Ledger(DATA, tmp_path)
    ledger2.run_expiry("2025-12-31")
    assert any(l.lot_id=="HLD-019" and l.qty==150 and not l.expired for l in ledger2.lots)
    ledger2.run_expiry("2026-01-01")
    assert not any(l.lot_id=="HLD-019" and l.qty>0 for l in ledger2.lots)

def test_out_of_band_and_excess_sell_orders_are_rejected(tmp_path):
    ledger = run(DATA, tmp_path)
    byid = {r["order_id"]:r for r in ledger.session_results}
    assert byid["ORD-096"]["decision"] == "REJECTED"
    assert byid["ORD-096"]["reason"] == "PRICE_OUTSIDE_BAND"
    assert byid["ORD-122"]["decision"] == "REJECTED"
    assert byid["ORD-122"]["reason"] == "INSUFFICIENT_UNENCUMBERED_HOLDINGS"

def test_solar_rec_substitution_is_blocked_before_solar_target(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    ledger.retire("RET-012")
    assert ledger.retirements_done[-1]["accepted"] is False
    assert ledger.retirements_done[-1]["reason"] == "SOLAR_TARGET_NOT_MET"

def test_margin_is_strictly_one_hundred_percent_of_limit_order_value(tmp_path):
    ledger = run(DATA, tmp_path)
    byid = {r["order_id"]:r for r in ledger.session_results}
    # Supplied pack's ENT-08 opening funds are Rs 719,540; 300 x Rs 2,400 = Rs 720,000.
    assert byid["ORD-083"]["decision"] == "REJECTED"
    assert byid["ORD-083"]["reason"] == "INSUFFICIENT_MARGIN"


def test_exact_ninety_percent_carry_forward_is_permitted_once(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    # Synthetic qualifying compliance record: 400/400 solar + 540/600 non-solar.
    ledger.retirements_done = [
        dict(accepted=True, counted=True, entity_id="ENT-03", category="SOLAR_REC",
             quantity=400, compliance_year="2025-26"),
        dict(accepted=True, counted=True, entity_id="ENT-03", category="NON_SOLAR_REC",
             quantity=540, compliance_year="2025-26"),
    ]
    row = next(x for x in ledger.compliance("2025-26") if x["entity_id"]=="ENT-03")
    assert row["shortfall_units"] == 60
    assert row["carry_forward_units"] == 60
    assert row["status"] == "CARRY_FORWARD"
    row_again = next(x for x in ledger.compliance("2025-26") if x["entity_id"]=="ENT-03")
    assert row_again["status"] == "SHORTFALL"

def test_solar_rec_can_cover_non_solar_after_solar_target_is_met(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    from datetime import date
    ledger.new_lot("ENT-04","SOLAR_REC","2025-01",date(2025,2,1),date(2028,1,31),250)
    ledger.retire("RET-015")  # 200 solar RECs meet ENT-04's solar target.
    assert ledger.retirements_done[-1]["accepted"] is True
    ledger.retire("RET-016")  # 50 solar RECs can now be applied to non-solar.
    assert ledger.retirements_done[-1]["accepted"] is True

def test_cancel_before_close_releases_order_and_after_close_is_rejected(tmp_path):
    ledger = run(DATA, tmp_path)
    byid = {r["order_id"]:r for r in ledger.session_results}
    assert byid["ORD-126"]["decision"] == "CANCELLED"
    assert byid["ORD-100"]["reason"] == "CANCEL_AFTER_SESSION_CLOSE"

def test_retirement_exceeding_holdings_is_rejected(tmp_path):
    ledger = run(DATA, tmp_path)
    ret = next(x for x in ledger.retirements_done if x["retirement_id"]=="RET-020")
    assert ret["accepted"] is False
    assert ret["reason"] == "INSUFFICIENT_HOLDINGS"


def test_forbearance_bound_clears_sells_and_prorates_buys(tmp_path):
    ledger = Ledger(DATA, tmp_path)
    ledger.sessions["TST"] = {
        "session_id":"TST", "session_date":"2026-04-20", "category":"NON_SOLAR_REC",
        "open_ts":"2026-04-20 13:00:00", "close_ts":"2026-04-20 15:00:00",
        "floor_price":"1000", "forbearance_price":"3000"
    }
    rows = [
        dict(order_id="TB1",session_id="TST",member_id="ENT-01",side="BUY",category="NON_SOLAR_REC",quantity="600",price="3000",order_ts="2026-04-20 13:10:00"),
        dict(order_id="TB2",session_id="TST",member_id="ENT-02",side="BUY",category="NON_SOLAR_REC",quantity="400",price="3000",order_ts="2026-04-20 13:11:00"),
        dict(order_id="TS1",session_id="TST",member_id="GEN-04",side="SELL",category="NON_SOLAR_REC",quantity="300",price="2000",order_ts="2026-04-20 13:12:00"),
        dict(order_id="TS2",session_id="TST",member_id="GEN-06",side="SELL",category="NON_SOLAR_REC",quantity="300",price="2500",order_ts="2026-04-20 13:13:00"),
    ]
    for row in rows: ledger.orders[row["order_id"]] = row
    ledger.open_session("TST")
    for row in rows: ledger.enter_order(row["order_id"])
    ledger.close_session("TST")
    summary = ledger.session_summaries[-1]
    assert summary["band_status"] == "FORBEARANCE_BOUND"
    assert summary["clearing_price"] == "3000"
    fills = {o.row["order_id"]:o.filled for o in ledger.order_states.values()}
    assert fills["TB1"] == 360 and fills["TB2"] == 240
    assert fills["TS1"] + fills["TS2"] == 600
