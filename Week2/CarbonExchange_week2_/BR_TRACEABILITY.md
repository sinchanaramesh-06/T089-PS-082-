# Business-rule traceability register (BR-01–BR-17)

This register maps the 11 numbered requirements supplied by the project owner into 17 individually testable requirements. It is a test-planning and review aid; it does not assert that hidden evaluation has been passed.

| ID | Requirement | Main implementation area | Verification / remaining qualification |
|---|---|---|---|
| BR-01 | REC quantity = floor(metered MWh) | `rec_units`, `apply_issuance` | `test_rec_quantity_rounds_down`; add fractional and zero boundary cases for future changes |
| BR-02 | Six-month inclusive application deadline; later applications lapse | `issuance_deadline`, `apply_issuance` | `test_march_last_day_is_issued_and_next_day_lapses` |
| BR-03 | Accreditation under one year requires audit flag | `apply_issuance`, `set_audit` | `test_new_generator_issuance_is_held_then_issued_after_audit` |
| BR-04 | Carbon credit quantity and 5% buffer | `carbon_buffer`, `issue_now` | `test_carbon_buffer_is_five_percent`; buffer fractional policy is floor, documented assumption |
| BR-05 | Buffer release after three consecutive issuances | `issue_now`, `reverse` | `test_carbon_buffer_releases_after_third_consecutive_issuance`; reversal regression test added |
| BR-06 | Solar and non-solar category segregation | `category_for_generator`, `reserve_sell`, `retire` | category validation tests and planted retirement scenarios |
| BR-07 | Solar can cover non-solar only after solar target met | `retire`, `compliance` | `test_solar_substitution_requires_solar_target_first`; planted scenarios |
| BR-08 | Vintage expiry 36 months after issuance month; expiry-day trade valid | `expiry_for_vintage`, `lots_for`, `run_expiry` | `test_vintage_expiry_is_last_day_of_36th_month`, `test_expiry_day_trade_is_valid_and_lot_remains_until_next_day` |
| BR-09 | Uniform-price double auction, price priority and marginal pro-rata | `close_session`, `allocate` | `test_auction_uses_lower_exact_intersection_and_pro_rata_residual`; SES-01..06 scenarios |
| BR-10 | Price band; out-of-band rejection; forbearance allocation | `enter_order`, `close_session` | `test_out_of_band_and_excess_sell_orders_are_rejected`; SES-05 planted scenario |
| BR-11 | Exchange/registry fees and GST | `fee_components`, `settle_session` | `test_buyer_fees`, `test_seller_fees`; fees applied to filled value |
| BR-12 | T+1 fee settlement and proceeds sequencing | `settle_session` | Review settlement command dates in integration scenarios; timing is command-driven |
| BR-13 | 100% buy margin at entry; release on non-fill/rejection | `enter_order`, `close_session`, `cancel_order` | planted cancellation/non-fill cases; insufficient-margin case |
| BR-14 | FIFO vintage transfer | `lots_for`, `transfer` | FIFO sort by vintage, issue date and lot ID; additional synthetic multi-lot test recommended |
| BR-15 | RPO targets, 31 March cutoff, shortfall penalty | `target`, `retired_total`, `compliance` | planted RET-006 cutoff; synthetic target/penalty tests should be extended |
| BR-16 | 90% carry-forward once | `compliance`, `carry_used` | synthetic 90% scenario documented in baseline tests; category-allocation interpretation needs mentor confirmation |
| BR-17 | Reversal order, no retired-unit clawback, liability at latest same-category price | `reverse`, `last_price` | `test_reversal_cancels_untraded_units_and_records_cash_liability`; extend tests for buffer exhaustion and retired quantities |

## Important scope note

The source brief contains 11 numbered paragraphs, not 17 separately numbered rules. The IDs above split compound requirements into testable sub-rules for traceability. They should be reconciled with the mentor's preferred BR numbering if the original design document uses a different numbering scheme.

## Known ambiguities requiring evaluator/mentor confirmation

- Whether 5% carbon buffer withholding is rounded down, rounded to nearest, or retains fractional units. Current implementation floors to whole credits.
- Exact auction price discovery when no exact cumulative demand/supply equality exists. Current implementation uses maximum executable volume and a lower-price tie preference / crossing convention described in README.
- Whether the 90% carry-forward test is aggregate or separately category-based. Current implementation uses aggregate target attainment as described in README.
- Whether reversal should reset the three-issuance streak for every reversal. This build resets it for any carbon issuance reversal.
- Whether a T+1 fee should be posted only when a later dated settlement command is processed; the input command stream is authoritative for execution order.

A hidden evaluation result cannot be guaranteed without its input set and evaluator oracle. The project must be treated as a best-effort implementation against the published contract, not a certified pass.
