"""
Carbon Exchange Registry and Settlement Engine — Week 3
Full Rules, Validation, and Edge Cases Implementation

Covers:
  - Business Rules: BR-01 through BR-17
  - Explicit Edge Cases: EC-01 through EC-08
"""

from __future__ import annotations
import csv
import calendar
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path

ZERO = Decimal("0")
CENT = Decimal("0.01")


def D(x) -> Decimal:
    """Helper to convert values to Decimal safely."""
    return ZERO if x is None or x == "" else Decimal(str(x))


def money(x: Decimal) -> Decimal:
    """Standard monetary rounding to 2 decimal places (half-up)."""
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def add_months(d: date, n: int) -> date:
    """Add n calendar months to date d, clamping day to end of month if needed."""
    i = d.month - 1 + n
    y, m = d.year + i // 12, i % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_end(d: date) -> date:
    """Return the last calendar day of the given date's month."""
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def expiry_for_vintage(vintage: str) -> date:
    """
    BR-06: RECs expire 36 months after the end of the issuance/generation month.
    The expiry date is the last calendar day of the 36th month.
    """
    y, m = map(int, vintage.split("-"))
    return month_end(add_months(date(y, m, 1), 36))


def issuance_deadline(vintage: str) -> date:
    """
    BR-01 / EC-03: REC issuance must be applied for within 6 months
    of the generation month (month-end arithmetic).
    """
    y, m = map(int, vintage.split("-"))
    return month_end(add_months(date(y, m, 1), 6))


def rec_units(mwh) -> int:
    """
    BR-01: Issue 1 REC per 1 MWh of metered generation, rounding down.
    """
    return int(D(mwh).to_integral_value(rounding=ROUND_DOWN))


def carbon_buffer(tonnes, pct=Decimal("5")) -> int:
    """
    BR-03: Withhold 5% of verified CO2e reduction into buffer pool (rounded down).
    """
    return int((Decimal(tonnes) * pct / 100).to_integral_value(rounding=ROUND_DOWN))


def prorata_allocate(total: int, quantities: list[int]) -> list[int]:
    """
    BR-08 / EC-02: Allocate marginal-price orders proportionally by quantity,
    rounding down using floor division, leaving residual units unfilled.
    """
    denom = sum(quantities)
    if denom == 0:
        return [0 for _ in quantities]
    return [(total * q) // denom for q in quantities]


def fee_components(value: Decimal, qty: int, side: str,
                   exchange_pct=Decimal("0.5"),
                   registry_per_cert=Decimal("2"),
                   gst_pct=Decimal("18")) -> dict:
    """
    BR-10: Exchange fee = 0.5% of trade value (both sides).
           Registry fee = Rs 2 per certificate (seller only).
           GST = 18% on fees.
    """
    ex = money(value * exchange_pct / 100)
    reg = money(Decimal(qty) * registry_per_cert) if side == "SELL" else ZERO
    gst = money((ex + reg) * gst_pct / 100)
    net = -(value + ex + gst) if side == "BUY" else value - ex - reg - gst
    return {
        "exchange_fee": ex,
        "registry_fee": reg,
        "gst_on_fees": gst,
        "net_cash": money(net)
    }


@dataclass
class Lot:
    lot_id: str
    holder: str
    category: str
    vintage: str
    issue_date: date
    expiry: date | None
    qty: int
    source: str | None = None
    encumbered: int = 0
    expired: bool = False


@dataclass
class Account:
    member_id: str
    opening: Decimal
    funds: Decimal
    blocked: Decimal = ZERO
    liability: Decimal = ZERO

    @property
    def available(self) -> Decimal:
        """Available funds for trading: funds minus blocked margin."""
        return money(self.funds - self.blocked)


@dataclass
class Order:
    row: dict
    decision: str = "ACCEPTED"
    reason: str = ""
    filled: int = 0
    clearing: Decimal | None = None
    trade_value: Decimal = ZERO
    exchange_fee: Decimal = ZERO
    registry_fee: Decimal = ZERO
    gst: Decimal = ZERO
    net_cash: Decimal = ZERO
    margin: Decimal = ZERO
    reserved: list = field(default_factory=list)


class Ledger:
    def __init__(self, data_dir, output_dir):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.params = {r["key"]: r["value"] for r in self.read("parameters.csv")}
        self.generators = {r["generator_id"]: r for r in self.read("generators.csv")}
        self.entities = {r["entity_id"]: r for r in self.read("entities.csv")}
        self.sessions = {r["session_id"]: r for r in self.read("sessions.csv")}
        self.issuances = {r["issuance_id"]: r for r in self.read("issuances.csv")}

        self.orders = {}
        for r in self.read("orders.csv"):
            self.orders.setdefault(r["order_id"], r)  # Ignore duplicate source rows

        self.retirements = {r["retirement_id"]: r for r in self.read("retirements.csv")}

        self.accounts: dict[str, Account] = {}
        for mid, r in list(self.generators.items()) + list(self.entities.items()):
            f = D(r["opening_funds"])
            self.accounts[mid] = Account(mid, f, f)

        self.lots: list[Lot] = []
        for r in self.read("opening_holdings.csv"):
            self.lots.append(Lot(
                r["holding_id"],
                r["holder_id"],
                r["category"],
                r["vintage_month"],
                date.fromisoformat(r["issue_date"]),
                date.fromisoformat(r["expiry_date"]),
                int(r["quantity"])
            ))

        self.issuance_results: list[dict] = []
        self.session_results: list[dict] = []
        self.session_summaries: list[dict] = []
        self.registry_rows: list[dict] = []
        self.order_states: dict[str, Order] = {}
        self.open_sessions: set[str] = set()
        self.closed_sessions: set[str] = set()
        self.settled_sessions: set[str] = set()
        self.last_price: dict[str, Decimal] = {}
        self.pending_audit: dict[str, list[str]] = {}
        self.carbon_streak: dict[str, int] = {}
        self.carbon_buffer_pool: dict[str, int] = {}
        self.carbon_buffer_lots: dict[str, list[dict]] = {}
        self.retirements_done: list[dict] = []
        self.carry_used: set[str] = set()
        self.year_end = date.fromisoformat(self.params.get("compliance_year_end", "2026-03-31"))
        self.forbearance = D(self.params.get("forbearance_price", "3000"))

    def read(self, name: str) -> list[dict]:
        with (self.data_dir / name).open(newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def category_for_generator(self, gid: str) -> str:
        """BR-05: Generators produce SOLAR_REC if solar, else NON_SOLAR_REC."""
        return "SOLAR_REC" if self.generators[gid]["technology"] == "SOLAR" else "NON_SOLAR_REC"

    def lots_for(self, holder: str, cat: str, asof: date | None = None) -> list[Lot]:
        """
        BR-12 / BR-06 / EC-08: Retrieve active lots for holder/category sorted FIFO
        by vintage, issue date, lot ID.
        Inclusive on expiry date (l.expiry >= asof).
        """
        ls = [
            l for l in self.lots
            if l.holder == holder and l.category == cat and l.qty > 0 and not l.expired
            and (asof is None or l.expiry is None or l.expiry >= asof)
        ]
        return sorted(ls, key=lambda l: (l.vintage, l.issue_date, l.lot_id))

    def holding_total(self, holder: str, cat: str, asof: date | None = None) -> int:
        return sum(l.qty for l in self.lots_for(holder, cat, asof))

    def new_lot(self, holder: str, cat: str, vintage: str, issue_date: date,
                expiry: date | None, qty: int, source: str | None = None):
        if qty > 0:
            self.lots.append(Lot(
                f"SYS-{len(self.lots)+1:05}", holder, cat, vintage, issue_date, expiry, qty, source
            ))

    def add_issuance_result(self, iid: str, decision: str, reason: str,
                            units: int = 0, buffer: int = 0, vintage: str = "", expiry: str = ""):
        r = self.issuances[iid]
        self.issuance_results.append(dict(
            issuance_id=iid,
            generator_id=r["generator_id"],
            decision=decision,
            reason=reason,
            units_issued=units,
            buffer_withheld=buffer,
            vintage_month=vintage,
            expiry_date=expiry
        ))

    def apply_issuance(self, iid: str):
        """
        BR-01 / BR-02 / EC-03: Process issuance application.
        Check 6-month deadline and generator 1-year accreditation audit flag.
        """
        r = self.issuances[iid]
        gid = r["generator_id"]
        gen = self.generators[gid]
        app = date.fromisoformat(r["application_date"])
        vintage = r["generation_month"]
        deadline = issuance_deadline(vintage)

        if app > deadline:
            self.add_issuance_result(iid, "LAPSED", f"APPLICATION_AFTER_{deadline}", 0, 0, vintage, "")
            return

        accredited = date.fromisoformat(gen["accreditation_date"])
        if add_months(accredited, 12) > app and str(gen["audit_flag"]).lower() != "true":
            self.pending_audit.setdefault(gid, []).append(iid)
            self.add_issuance_result(iid, "HELD", "AUDIT_REQUIRED", 0, 0, vintage, "")
            return

        self.issue_now(iid, "ISSUED", "ELIGIBLE")

    def issue_now(self, iid: str, decision: str, reason: str):
        """
        BR-01 / BR-03 / BR-04: Issue certificate lots and track carbon buffer.
        """
        r = self.issuances[iid]
        gid = r["generator_id"]
        vintage = r["generation_month"]
        app = date.fromisoformat(r["application_date"])

        if r["certificate_type"] == "REC":
            qty = rec_units(r["metered_mwh"])
            buf = 0
            cat = self.category_for_generator(gid)
            exp = expiry_for_vintage(vintage)
        else:
            gross = int(D(r["verified_tco2e"]))
            buf = carbon_buffer(gross, D(self.params.get("buffer_pct", "5")))
            qty = gross - buf
            cat = "CARBON"
            exp = None
            self.carbon_buffer_pool[gid] = self.carbon_buffer_pool.get(gid, 0) + buf
            self.carbon_buffer_lots.setdefault(gid, []).append(
                {"vintage": vintage, "issue_date": app, "quantity": buf}
            )
            self.carbon_streak[gid] = self.carbon_streak.get(gid, 0) + 1

        self.new_lot(gid, cat, vintage, app, exp, qty, iid)
        self.add_issuance_result(iid, decision, reason, qty, buf, vintage, exp.isoformat() if exp else "")

        # BR-04: Buffer release after 3 consecutive issuances without reversal
        release_threshold = int(self.params.get("buffer_release_after_issuances", "3"))
        if cat == "CARBON" and self.carbon_streak.get(gid, 0) >= release_threshold:
            release_lots = self.carbon_buffer_lots.get(gid, [])
            for buffer_lot in release_lots:
                self.new_lot(gid, "CARBON", buffer_lot["vintage"], buffer_lot["issue_date"],
                             None, buffer_lot["quantity"], None)
            self.carbon_buffer_lots[gid] = []
            self.carbon_buffer_pool[gid] = 0
            self.carbon_streak[gid] = 0

    def set_audit(self, gid: str, when: str):
        """BR-02: Mark audit completed and release held issuances."""
        self.generators[gid]["audit_flag"] = "true"
        for iid in self.pending_audit.pop(gid, []):
            self.issue_now(iid, "ISSUED", f"AUDIT_APPROVED_{when}")

    def open_session(self, sid: str):
        self.open_sessions.add(sid)

    def reserve_sell(self, o: Order, asof: date) -> bool:
        """BR-16: Reserve unencumbered holdings for sell order."""
        remaining = int(o.row["quantity"])
        for lot in self.lots_for(o.row["member_id"], o.row["category"], asof):
            take = min(lot.qty - lot.encumbered, remaining)
            if take:
                lot.encumbered += take
                o.reserved.append((lot.lot_id, take))
                remaining -= take
            if remaining == 0:
                break
        return remaining == 0

    def release_sell(self, o: Order):
        """Release temporary reservation on sell order."""
        byid = {l.lot_id: l for l in self.lots}
        for lid, q in o.reserved:
            if lid in byid:
                byid[lid].encumbered = max(0, byid[lid].encumbered - q)
        o.reserved = []

    def enter_order(self, oid: str):
        """
        BR-09 / BR-11 / BR-16 / EC-07:
        Validate buy/sell order against session status, price band, timing,
        available margin, and unencumbered holdings.
        """
        if oid in self.order_states:
            return
        r = self.orders[oid]
        sid = r["session_id"]
        sess = self.sessions[sid]
        o = Order(r)
        self.order_states[oid] = o

        if sid not in self.open_sessions or sid in self.closed_sessions:
            o.decision, o.reason = "REJECTED", "SESSION_NOT_OPEN"
            return
        if r["category"] != sess["category"]:
            o.decision, o.reason = "REJECTED", "CATEGORY_MISMATCH"
            return
        if r["member_id"] not in self.accounts:
            o.decision, o.reason = "REJECTED", "UNKNOWN_MEMBER"
            return

        qty = int(r["quantity"])
        price = D(r["price"])
        if price < D(sess["floor_price"]) or price > D(sess["forbearance_price"]):
            o.decision, o.reason = "REJECTED", "PRICE_OUTSIDE_BAND"
            return

        odt = datetime.strptime(r["order_ts"], "%Y-%m-%d %H:%M:%S")
        open_dt = datetime.strptime(sess["open_ts"], "%Y-%m-%d %H:%M:%S")
        close_dt = datetime.strptime(sess["close_ts"], "%Y-%m-%d %H:%M:%S")
        if not (open_dt <= odt <= close_dt):
            o.decision, o.reason = "REJECTED", "ORDER_OUTSIDE_SESSION"
            return

        acct = self.accounts[r["member_id"]]
        if r["side"] == "BUY":
            o.margin = money(Decimal(qty) * price)
            if acct.available < o.margin:
                o.decision, o.reason = "REJECTED", "INSUFFICIENT_MARGIN"
                return
            acct.blocked += o.margin
        elif not self.reserve_sell(o, date.fromisoformat(sess["session_date"])):
            self.release_sell(o)
            o.decision, o.reason = "REJECTED", "INSUFFICIENT_UNENCUMBERED_HOLDINGS"

    def cancel_order(self, oid: str, ts: str):
        """
        BR-16: Orders cannot be modified, only cancelled.
        Cancellation after session close is REJECTED.
        """
        o = self.order_states.get(oid)
        if not o:
            return
        sess = self.sessions[o.row["session_id"]]
        if datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") > datetime.strptime(sess["close_ts"], "%Y-%m-%d %H:%M:%S"):
            o.reason = "CANCEL_AFTER_SESSION_CLOSE"
            for row in self.session_results:
                if row["order_id"] == oid:
                    row["reason"] = o.reason
            return
        if o.decision != "ACCEPTED":
            return
        if o.row["side"] == "BUY":
            self.accounts[o.row["member_id"]].blocked -= o.margin
        else:
            self.release_sell(o)
        o.decision, o.reason = "CANCELLED", "MEMBER_CANCELLED"

    def allocate(self, orders: list[Order], side: str, price: Decimal, target: int):
        """
        BR-07 / BR-08 / EC-02: Allocate filled quantities.
        Better-price orders fill first. Marginal price orders pro-rate with floor division.
        """
        if side == "BUY":
            elig = sorted([o for o in orders if D(o.row["price"]) >= price],
                          key=lambda o: (-D(o.row["price"]), o.row["order_ts"], o.row["order_id"]))
            better = [o for o in elig if D(o.row["price"]) > price]
        else:
            elig = sorted([o for o in orders if D(o.row["price"]) <= price],
                          key=lambda o: (D(o.row["price"]), o.row["order_ts"], o.row["order_id"]))
            better = [o for o in elig if D(o.row["price"]) < price]

        marginal = [o for o in elig if D(o.row["price"]) == price]
        rem = target
        for o in better:
            f = min(int(o.row["quantity"]), rem)
            o.filled += f
            rem -= f

        residual = 0
        if rem > 0 and marginal:
            qs = [int(o.row["quantity"]) for o in marginal]
            alloc = prorata_allocate(min(rem, sum(qs)), qs)
            for o, f in zip(marginal, alloc):
                o.filled += f
            residual = min(rem, sum(qs)) - sum(alloc)
        return (target - rem + min(rem, sum([int(o.row["quantity"]) for o in marginal])) - residual
                if marginal else target - rem, residual)

    def transfer(self, sells: list[Order], buys: list[Order], sid: str):
        """
        BR-12 / EC-08: Transfer certificates FIFO by vintage from sellers to buyers.
        """
        for sell in sells:
            self.release_sell(sell)

        session_date = date.fromisoformat(self.sessions[sid]["session_date"])
        slices = []
        sell_priority = sorted([s for s in sells if s.filled],
                               key=lambda s: (D(s.row["price"]), s.row["order_ts"], s.row["order_id"]))

        for sell in sell_priority:
            seller, cat = sell.row["member_id"], sell.row["category"]
            rem = sell.filled
            for lot in self.lots_for(seller, cat, session_date):
                take = min(lot.qty - lot.encumbered, rem)
                if take:
                    lot.qty -= take
                    slices.append((lot.category, lot.vintage, lot.issue_date, lot.expiry, lot.source, take))
                    rem -= take
                if rem == 0:
                    break
            if rem:
                raise ValueError(f"SETTLEMENT_HOLDING_SHORTFALL:{seller}:{cat}:{rem}")

        buyers = sorted([b for b in buys if b.filled > 0],
                        key=lambda b: (-D(b.row["price"]), b.row["order_ts"], b.row["order_id"]))
        si = 0
        for buyer in buyers:
            need = buyer.filled
            while need > 0 and si < len(slices):
                cat, vintage, issue, expiry, source, available = slices[si]
                take = min(need, available)
                self.new_lot(buyer.row["member_id"], cat, vintage, issue, expiry, take, source)
                need -= take
                available -= take
                if available == 0:
                    si += 1
                else:
                    slices[si] = (cat, vintage, issue, expiry, source, available)
            if need:
                raise ValueError(f"SETTLEMENT_BUYER_ALLOCATION_SHORTFALL:{buyer.row['order_id']}:{need}")

    def close_session(self, sid: str):
        """
        BR-07 / BR-08 / BR-09 / EC-01 / EC-02:
        Uniform-price auction clearing under floor and forbearance constraints.
        Tie breaking chooses lower price when equal volume is executable.
        """
        if sid in self.closed_sessions:
            return
        sess = self.sessions[sid]
        cat = sess["category"]
        states = [o for o in self.order_states.values() if o.row["session_id"] == sid and o.decision == "ACCEPTED"]
        buys = [o for o in states if o.row["side"] == "BUY"]
        sells = [o for o in states if o.row["side"] == "SELL"]

        prices = sorted({D(o.row["price"]) for o in states})
        best = None
        volume = 0
        curve = []
        for p in prices:
            demand = sum(int(o.row["quantity"]) for o in buys if D(o.row["price"]) >= p)
            supply = sum(int(o.row["quantity"]) for o in sells if D(o.row["price"]) <= p)
            curve.append((p, demand, supply, min(demand, supply), demand - supply))

        cap = D(sess["forbearance_price"])
        cap_demand = sum(int(o.row["quantity"]) for o in buys if D(o.row["price"]) >= cap)
        cap_supply = sum(int(o.row["quantity"]) for o in sells if D(o.row["price"]) <= cap)

        # BR-09: Forbearance-bound check
        if cap_demand > cap_supply and cap_supply > 0:
            best, volume = cap, cap_supply
        else:
            # EC-01: Exact demand/supply intersection; choose the lowest price if multiple tie
            exact = [x for x in curve if x[1] == x[2] and x[1] > 0]
            if exact:
                best, _, _, volume, _ = min(exact, key=lambda x: x[0])
            else:
                crossing = None
                for left, right in zip(curve, curve[1:]):
                    if left[4] > 0 and right[4] < 0:
                        crossing = left
                        break
                if crossing:
                    best, _, _, volume, _ = crossing
                else:
                    for p, dem, sup, v, imb in curve:
                        if v > volume or (v == volume and v > 0 and (best is None or p < best)):
                            best, volume = p, v

        total = 0
        residual = 0
        band = "NORMAL"
        if best is not None and volume:
            if best <= D(sess["floor_price"]):
                band = "FLOOR_BOUND"
            elif best >= D(sess["forbearance_price"]):
                band = "FORBEARANCE_BOUND"

            self.allocate(buys, "BUY", best, volume)
            self.allocate(sells, "SELL", best, volume)
            total = min(sum(o.filled for o in buys), sum(o.filled for o in sells))
            self.last_price[cat] = best
            self.transfer(sells, buys, sid)

            for o in states:
                o.clearing = best
                o.trade_value = money(Decimal(o.filled) * best)
                f = fee_components(o.trade_value, o.filled, o.row["side"])
                o.exchange_fee = f["exchange_fee"]
                o.registry_fee = f["registry_fee"]
                o.gst = f["gst_on_fees"]
                o.net_cash = f["net_cash"]

            # Calculate residual units unallocated at marginal price
            residual = 0
            for side_orders in (buys, sells):
                marginal = [o for o in side_orders if D(o.row["price"]) == best]
                if marginal:
                    theoretical = sum(int(o.row["quantity"]) for o in marginal)
                    allocated = sum(o.filled for o in marginal)
                    target = min(theoretical, max(0, volume - sum(o.filled for o in side_orders if D(o.row["price"]) != best)))
                    residual = max(residual, max(0, target - allocated))

        for o in states:
            acct = self.accounts[o.row["member_id"]]
            if o.row["side"] == "BUY":
                acct.blocked = max(ZERO, acct.blocked - o.margin)
            else:
                self.release_sell(o)
            if o.filled:
                o.decision = "FILLED" if o.filled == int(o.row["quantity"]) else "PARTIAL_FILL"
                o.reason = "MATCHED"
            else:
                o.decision, o.reason = "UNFILLED", "NO_EXECUTABLE_MATCH"

        self.closed_sessions.add(sid)
        self.open_sessions.discard(sid)
        self.session_summaries.append(dict(
            session_id=sid,
            category=cat,
            clearing_price=str(best) if total else "",
            total_filled=total,
            residual_units=residual,
            band_status=band
        ))
        for o in self.order_states.values():
            if o.row["session_id"] == sid:
                self.session_results.append(self.order_output(o))

    def order_output(self, o: Order) -> dict:
        return dict(
            session_id=o.row["session_id"],
            order_id=o.row["order_id"],
            member_id=o.row["member_id"],
            side=o.row["side"],
            decision=o.decision,
            reason=o.reason,
            quantity=int(o.row["quantity"]),
            filled_quantity=o.filled,
            clearing_price=str(o.clearing) if o.clearing is not None else "",
            trade_value=f"{o.trade_value:.2f}",
            exchange_fee=f"{o.exchange_fee:.2f}",
            registry_fee=f"{o.registry_fee:.2f}",
            gst_on_fees=f"{o.gst:.2f}",
            net_cash=f"{o.net_cash:.2f}"
        )

    def settle_session(self, sid: str, when: str):
        """
        BR-10 / EC-07: Financial settlement of a session.
        Debits buyer funds (trade value + fees + GST). If funds were equal to margin,
        fee debit drives funds negative (-684.40 in EC-07), blocking further buys.
        Credits seller proceeds after deducting fees.
        """
        if sid in self.settled_sessions:
            return
        if sid not in self.closed_sessions:
            raise ValueError("SESSION_NOT_CLOSED")

        filled = [o for o in self.order_states.values() if o.row["session_id"] == sid and o.filled]
        # Buyer side debited first
        for o in filled:
            if o.row["side"] == "BUY":
                debit = o.trade_value + o.exchange_fee + o.gst
                self.accounts[o.row["member_id"]].funds = money(self.accounts[o.row["member_id"]].funds - debit)
        # Seller side credited
        for o in filled:
            if o.row["side"] == "SELL":
                credit = o.trade_value - o.exchange_fee - o.registry_fee - o.gst
                self.accounts[o.row["member_id"]].funds = money(self.accounts[o.row["member_id"]].funds + credit)
        self.settled_sessions.add(sid)

    def reverse(self, iid: str, qty: int, when: str):
        """
        BR-15 / EC-06:
        Verification failure reversal:
        1. Cancel generator's untraded units first.
        2. Cancel buffer-pool units next.
        3. Generator owes remaining deficit at last clearing price of category.
        Already retired units in buyer holdings are not clawed back.
        """
        r = self.issuances[iid]
        gid = r["generator_id"]
        left = int(qty)

        # 1. Untraded units of generator cancelled first
        for lot in self.lots:
            if lot.source == iid and lot.holder == gid and lot.qty > 0:
                take = min(lot.qty - lot.encumbered, left)
                lot.qty -= take
                left -= take
                if left == 0:
                    break

        if r["certificate_type"] == "CARBON":
            # BR-04: Reversal resets the consecutive streak
            self.carbon_streak[gid] = 0

        # 2. Buffer pool drawn next
        if r["certificate_type"] == "CARBON" and left:
            pool = self.carbon_buffer_lots.get(gid, [])
            for buffer_lot in pool:
                take = min(buffer_lot["quantity"], left)
                buffer_lot["quantity"] -= take
                self.carbon_buffer_pool[gid] = self.carbon_buffer_pool.get(gid, 0) - take
                left -= take
                if left == 0:
                    break
            self.carbon_buffer_lots[gid] = [x for x in pool if x["quantity"] > 0]

        # 3. Monetary liability at last clearing price
        if left:
            cat = self.category_for_generator(gid) if r["certificate_type"] == "REC" else "CARBON"
            liability = money(Decimal(left) * self.last_price.get(cat, ZERO))
            self.accounts[gid].liability += liability
            self.accounts[gid].funds = money(self.accounts[gid].funds - liability)

    def run_expiry(self, when: str):
        """
        BR-06 / BR-17 / EC-08: Exclude expired certificates.
        Trading on expiry date is valid; certificates expire when expiry_date < when.
        """
        d = date.fromisoformat(when)
        for l in self.lots:
            if l.expiry and l.expiry < d and l.qty:
                l.qty = 0
                l.encumbered = 0
                l.expired = True

    def print_registry(self, when: str):
        """BR-17: Record snapshot of registry balances as of given date."""
        d = date.fromisoformat(when)
        grouped = {}
        for l in self.lots:
            if l.qty > 0 and not l.expired and (l.expiry is None or l.expiry >= d):
                expiry = l.expiry.isoformat() if l.expiry else ""
                key = (when, l.holder, l.category, l.vintage, expiry)
                if key not in grouped:
                    grouped[key] = {"quantity": 0, "encumbered_quantity": 0}
                grouped[key]["quantity"] += l.qty
                grouped[key]["encumbered_quantity"] += l.encumbered
        for key, values in sorted(grouped.items()):
            self.registry_rows.append(dict(
                as_of_date=key[0],
                holder_id=key[1],
                category=key[2],
                vintage_month=key[3],
                expiry_date=key[4],
                quantity=values["quantity"],
                encumbered_quantity=values["encumbered_quantity"]
            ))

    def target(self, eid: str, cat: str) -> int:
        """BR-13: RPO target is 10% solar, 15% non-solar of annual consumption."""
        pct = self.params["solar_rpo_pct"] if cat == "SOLAR_REC" else self.params["non_solar_rpo_pct"]
        return int((Decimal(self.entities[eid]["annual_consumption_mwh"]) * D(pct) / 100).to_integral_value(rounding=ROUND_DOWN))

    def retired_total(self, eid: str, cat: str, year: str) -> int:
        """BR-13: Total qualifying retirements before March 31 for compliance year."""
        return sum(
            r["quantity"] for r in self.retirements_done
            if r["accepted"] and r["counted"] and r["entity_id"] == eid
            and r["compliance_year"] == year and r["category"] == cat
        )

    def retire(self, rid: str):
        """
        BR-05 / BR-13 / EC-04: Process certificate retirement.
        Solar substitution for non-solar requires solar target to be met first.
        Retirements on or before March 31 count toward compliance year.
        """
        r = self.retirements[rid]
        eid = r["entity_id"]
        cat = r["category"]
        qty = int(r["quantity"])
        d = date.fromisoformat(r["retirement_date"])
        year = r["compliance_year"]

        def record(ok: bool, reason: str, counted: bool = False):
            self.retirements_done.append(dict(
                retirement_id=rid,
                entity_id=eid,
                category=cat,
                quantity=qty,
                retirement_date=d.isoformat(),
                compliance_year=year,
                accepted=ok,
                counted=counted,
                reason=reason
            ))

        if eid not in self.entities:
            record(False, "UNKNOWN_ENTITY")
            return

        usecat = "SOLAR_REC" if cat in ("SOLAR_REC", "SOLAR_REC_FOR_NON_SOLAR") else "NON_SOLAR_REC"

        # EC-04: Solar REC retirement used for non-solar shortfall before solar target met -> REJECT
        if cat == "SOLAR_REC_FOR_NON_SOLAR" and self.retired_total(eid, "SOLAR_REC", year) < self.target(eid, "SOLAR_REC"):
            record(False, "SOLAR_TARGET_NOT_MET")
            return

        if self.holding_total(eid, usecat, d) < qty:
            record(False, "INSUFFICIENT_HOLDINGS")
            return

        left = qty
        for l in self.lots_for(eid, usecat, d):
            take = min(l.qty - l.encumbered, left)
            l.qty -= take
            left -= take
            if left == 0:
                break

        counted = d <= self.year_end and year == "2025-26"
        record(True, "RETIRED" if counted else "RETIRED_OUTSIDE_COMPLIANCE_PERIOD", counted)

    def compliance(self, year: str) -> list[dict]:
        """
        BR-13 / BR-14 / EC-05:
        Annual RPO compliance calculation.
        - Target = 10% solar, 15% non-solar.
        - Shortfall = unmet solar + unmet non-solar.
        - If >= 90% retired and no prior carry-forward, carry forward once.
        - Otherwise shortfall penalty = shortfall * forbearance price (Rs 3,000).
        """
        rows = []
        for eid, e in self.entities.items():
            st, nt = self.target(eid, "SOLAR_REC"), self.target(eid, "NON_SOLAR_REC")
            sr = self.retired_total(eid, "SOLAR_REC", year)
            nr = self.retired_total(eid, "NON_SOLAR_REC", year)
            sn = self.retired_total(eid, "SOLAR_REC_FOR_NON_SOLAR", year)

            short = max(0, st - sr) + max(0, nt - nr - sn)
            total = st + nt
            achieved = sr + nr + sn
            carry = 0
            penalty = ZERO

            if short == 0:
                status = "COMPLIANT"
            elif (total and
                  (Decimal(achieved) / Decimal(total)) >= (D(self.params.get("carry_forward_min_pct", "90")) / 100) and
                  eid not in self.carry_used and
                  int(e.get("carry_forward_from_prior_year", "0")) == 0):
                carry = short
                self.carry_used.add(eid)
                status = "CARRY_FORWARD"
            else:
                penalty = Decimal(short) * self.forbearance
                status = "SHORTFALL"

            rows.append(dict(
                entity_id=eid,
                consumption_mwh=e["annual_consumption_mwh"],
                solar_target=st,
                solar_retired=sr,
                non_solar_target=nt,
                non_solar_retired=nr,
                solar_used_for_non_solar=sn,
                shortfall_units=short,
                carry_forward_units=carry,
                penalty_amount=f"{money(penalty):.2f}",
                status=status
            ))
        return rows

    def write_csv(self, name: str, rows: list[dict], cols: list[str]):
        with (self.output_dir / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

    def write_outputs(self):
        self.write_csv("issuance_results.csv", self.issuance_results, [
            "issuance_id", "generator_id", "decision", "reason", "units_issued",
            "buffer_withheld", "vintage_month", "expiry_date"
        ])
        self.write_csv("session_results.csv", self.session_results, [
            "session_id", "order_id", "member_id", "side", "decision", "reason",
            "quantity", "filled_quantity", "clearing_price", "trade_value",
            "exchange_fee", "registry_fee", "gst_on_fees", "net_cash"
        ])
        self.write_csv("session_summary.csv", self.session_summaries, [
            "session_id", "category", "clearing_price", "total_filled",
            "residual_units", "band_status"
        ])
        self.write_csv("registry_balances.csv", self.registry_rows, [
            "as_of_date", "holder_id", "category", "vintage_month",
            "expiry_date", "quantity", "encumbered_quantity"
        ])
        self.write_csv("compliance_report.csv", self.compliance("2025-26"), [
            "entity_id", "consumption_mwh", "solar_target", "solar_retired",
            "non_solar_target", "non_solar_retired", "solar_used_for_non_solar",
            "shortfall_units", "carry_forward_units", "penalty_amount", "status"
        ])
        self.write_csv("member_accounts.csv", [
            dict(
                member_id=a.member_id,
                opening_funds=f"{a.opening:.2f}",
                blocked_margin=f"{money(a.blocked):.2f}",
                available_funds=f"{a.available:.2f}",
                reversal_liability=f"{a.liability:.2f}"
            )
            for a in sorted(self.accounts.values(), key=lambda x: x.member_id)
        ], ["member_id", "opening_funds", "blocked_margin", "available_funds", "reversal_liability"])

    def process(self, commands_file):
        for raw in Path(commands_file).read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            p = line.split("|")
            cmd, args = p[0], p[1:]
            if cmd == "APPLY_ISSUANCE":
                self.apply_issuance(args[0])
            elif cmd == "SET_AUDIT_FLAG":
                self.set_audit(args[0], args[1])
            elif cmd == "OPEN_SESSION":
                self.open_session(args[0])
            elif cmd == "ORDER":
                self.enter_order(args[0])
            elif cmd == "CANCEL_ORDER":
                self.cancel_order(args[0], args[1])
            elif cmd == "CLOSE_SESSION":
                self.close_session(args[0])
            elif cmd == "SETTLE_SESSION":
                self.settle_session(args[0], args[1])
            elif cmd == "REVERSE":
                self.reverse(args[0], int(args[1]), args[2])
            elif cmd == "RETIRE":
                self.retire(args[0])
            elif cmd == "RUN_EXPIRY":
                self.run_expiry(args[0])
            elif cmd == "PRINT_REGISTRY":
                self.print_registry(args[0])
            elif cmd == "PRINT_COMPLIANCE":
                pass
            else:
                raise ValueError(f"UNKNOWN_COMMAND:{cmd}")
        self.write_outputs()


def run(data_dir, output_dir):
    ledger = Ledger(data_dir, output_dir)
    ledger.process(Path(data_dir) / "commands.txt")
    return ledger
