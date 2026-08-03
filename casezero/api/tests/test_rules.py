"""Rule packs: the immutability contract, the condition evaluator, and validation.

Two claims are on trial here.

The first is that policy is data. If adding a category is configuration rather than
code, the loader must reject a malformed pack loudly instead of running a half-valid
one — a pack that loads but silently omits an SLA is worse than a crash.

The second is that some keys are beyond the Policy Composer's reach. `IMMUTABLE_PATHS`
is only a real guarantee if `path_is_immutable` matches the paths a diff would
actually name, so these tests enumerate them literally.
"""

import pytest
import yaml

from api.kernel.rules import (
    CATEGORIES,
    RulePackError,
    evaluate_condition,
    load_all,
    load_yaml,
    missing_categories,
    path_is_append_only,
    path_is_immutable,
    validate,
)


class TestImmutabilityContract:
    """What the Policy Composer may and may not touch."""

    @pytest.mark.parametrize(
        "dotted",
        [
            "category",
            "version",
            "sla.High.working_days",
            "sla.Medium.working_days",
            "verification.confidence_floor",
            "verification.fallback_on_ambiguity",
            "resolution.require_verification",
            "communication.fmos_clause",
            "communication.fmos_clause.window_months",
            "communication.mandatory_disclosures",
            "audit",
            "audit.hash_chain",
        ],
    )
    def test_protected_paths_are_immutable(self, dotted):
        assert path_is_immutable(dotted)

    @pytest.mark.parametrize(
        "dotted",
        [
            "display_name",
            "sla.Low.extensions_allowed",
            "sla.breach_forecast_threshold",
            "urgency_rules",
            "verification.amount_tolerance_pct",
            "resolution.auto_approve_max_rm",
            "resolution.dual_control_above_rm",
            "resolution.narrative_template",
            "communication.register",
            "communication.prohibited_phrases",
        ],
    )
    def test_operational_paths_stay_editable(self, dotted):
        """The composer demo edits a threshold; that must remain possible."""
        assert not path_is_immutable(dotted)

    def test_protection_extends_to_descendants(self):
        assert path_is_immutable("communication.fmos_clause.text_en")
        assert path_is_immutable("audit.retain_years")

    def test_a_wildcard_matches_exactly_one_segment(self):
        # sla.*.working_days must not accidentally freeze the whole sla block.
        assert not path_is_immutable("sla")
        assert not path_is_immutable("sla.High")

    def test_disclosures_are_append_only(self):
        assert path_is_append_only("communication.mandatory_disclosures")
        assert path_is_append_only("communication.mandatory_disclosures.0")
        assert not path_is_append_only("communication.prohibited_phrases")


class TestConditionEvaluator:
    """The predicate language behind urgency. Small on purpose, and total."""

    @pytest.mark.parametrize(
        "condition,facts,expected",
        [
            ({"amount_rm": {"gte": 500}}, {"amount_rm": 500}, True),
            ({"amount_rm": {"gte": 500}}, {"amount_rm": 499.99}, False),
            ({"amount_rm": {"gt": 500}}, {"amount_rm": 500}, False),
            ({"amount_rm": {"lte": 250000}}, {"amount_rm": 250000}, True),
            ({"amount_rm": {"lt": 100}}, {"amount_rm": 99}, True),
            ({"segment": {"equals": "vulnerable"}}, {"segment": "VULNERABLE"}, True),
            ({"segment": {"not_equals": "retail"}}, {"segment": "vulnerable"}, True),
            ({"channel": {"in": ["email", "web"]}}, {"channel": "Email"}, True),
            ({"channel": {"in": ["email", "web"]}}, {"channel": "branch"}, False),
            ({"flags": {"contains": "fraud"}}, {"flags": ["FRAUD", "ring"]}, True),
            ({"body": {"contains": "unauthorised"}}, {"body": "An UNAUTHORISED debit"}, True),
        ],
    )
    def test_operators(self, condition, facts, expected):
        assert evaluate_condition(condition, facts) is expected

    def test_all_clauses_must_hold(self):
        condition = {"amount_rm": {"gte": 500}, "segment": {"equals": "vulnerable"}}
        assert evaluate_condition(condition, {"amount_rm": 900, "segment": "vulnerable"})
        assert not evaluate_condition(condition, {"amount_rm": 900, "segment": "retail"})

    def test_a_missing_fact_fails_closed(self):
        """An incomplete case goes to a human; it does not fall through to a match."""
        assert not evaluate_condition({"amount_rm": {"gte": 500}}, {})
        assert not evaluate_condition({"amount_rm": {"lt": 500}}, {"amount_rm": None})

    def test_a_non_numeric_fact_does_not_explode(self):
        assert not evaluate_condition({"amount_rm": {"gte": 500}}, {"amount_rm": "n/a"})

    def test_an_empty_condition_matches_nothing(self):
        """Otherwise a typo in a pack silently becomes a catch-all rule."""
        assert not evaluate_condition({}, {"amount_rm": 5000})

    def test_a_malformed_condition_is_an_error(self):
        with pytest.raises(RulePackError):
            evaluate_condition({"amount_rm": 500}, {"amount_rm": 500})

    def test_an_unknown_operator_is_an_error(self):
        with pytest.raises(RulePackError):
            evaluate_condition({"amount_rm": {"roughly": 500}}, {"amount_rm": 500})


class TestUrgencyAssignment:
    """Ordering is policy: vulnerability outranks amount."""

    def test_a_vulnerable_customer_outranks_a_small_amount(self, pack):
        decision = pack.assign_urgency({"customer_segment": "vulnerable", "amount_rm": 90})
        assert decision.urgency == "High"
        assert decision.rule_index == 0
        assert "vulnerable" in decision.because.lower()

    def test_large_amounts_are_high(self, pack):
        assert pack.assign_urgency({"amount_rm": 5000}).urgency == "High"

    def test_mid_amounts_are_medium(self, pack):
        decision = pack.assign_urgency({"amount_rm": 2450})
        assert decision.urgency == "Medium"
        # The pack gives no `because`, so the evaluator renders one for the Why panel.
        assert "at or above" in decision.because

    def test_small_amounts_fall_to_the_default(self, pack):
        decision = pack.assign_urgency({"amount_rm": 90})
        assert decision.urgency == "Low"
        assert "default" in decision.because.lower()

    def test_first_match_wins(self, pack):
        """RM5,000 satisfies both the High and the Medium rule."""
        assert pack.assign_urgency({"amount_rm": 5000}).rule_index == 1

    def test_a_pack_with_no_default_still_bounds_the_case(self, make_pack):
        pack = make_pack(
            {"urgency_rules": [{"when": {"amount_rm": {"gte": 5000}}, "then": "High"}]}
        )
        decision = pack.assign_urgency({"amount_rm": 10})
        assert decision.urgency == "Medium"
        assert decision.rule_index is None

    def test_every_decision_carries_a_reason(self, pack):
        for facts in ({"amount_rm": 9000}, {"amount_rm": 600}, {"amount_rm": 5}):
            assert pack.assign_urgency(facts).because


class TestTypedAccessors:
    """The kernel reads a pack through these, never through raw YAML keys."""

    def test_sla_days_match_the_pack(self, pack):
        assert pack.sla_working_days("High") == 5
        assert pack.sla_working_days("Medium") == 20
        assert pack.sla_working_days("Low") == 20

    def test_an_unknown_urgency_is_an_error_not_a_default(self, pack):
        with pytest.raises(RulePackError):
            pack.sla_working_days("Critical")

    def test_resolution_accessors(self, pack):
        assert pack.journal_type == "REVERSAL"
        assert pack.requires_verification == "PASS"
        assert pack.auto_approve_max_rm == 3000
        assert pack.dual_control_above_rm == 3000
        assert pack.debit_account == "GL-1450-FRAUD-SUSPENSE"

    def test_verification_accessors(self, pack):
        assert pack.confidence_floor == 0.75
        assert pack.fallback_on_ambiguity == "MANUAL_REVIEW"
        assert "amount_matches" in pack.required_evidence

    def test_communication_accessors(self, pack):
        assert pack.languages == ("en", "ms")
        assert pack.register == "dual"
        assert pack.fmos["window_months"] == 6
        assert {d["id"] for d in pack.mandatory_disclosures} >= {
            "BNM_ACK",
            "BNM_CASE_REF",
            "BNM_TIMELINE",
        }

    def test_defaults_apply_when_a_pack_omits_an_optional_key(self, make_pack):
        pack = make_pack(drop=["sla.breach_forecast_threshold", "verification.amount_tolerance_pct"])
        assert pack.breach_forecast_threshold == 0.20
        assert pack.amount_tolerance_pct == 1.0


class TestValidation:
    """Each of these is a compliance breach expressed as a bad key."""

    def test_the_shipped_pack_is_valid(self, pack):
        assert pack.category == "unauthorized_transaction"
        assert pack.version >= 1
        assert pack.volume_share == 0.35

    def test_an_unknown_category_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="category"):
            validate(make_raw({"category": "crypto_dispute"}))

    def test_a_missing_sla_urgency_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="sla.Medium.working_days"):
            validate(make_raw(drop=["sla.Medium"]))

    def test_a_zero_day_sla_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="positive integer"):
            validate(make_raw({"sla.High.working_days": 0}))

    def test_an_out_of_range_confidence_floor_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="confidence_floor"):
            validate(make_raw({"verification.confidence_floor": 1.4}))

    def test_relaxing_require_verification_is_rejected(self, make_raw):
        """The one edit that would let money move on an unverified case."""
        with pytest.raises(RulePackError, match="Money never moves"):
            validate(make_raw({"resolution.require_verification": "ANY"}))

    def test_an_unknown_journal_type_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="journal_type"):
            validate(make_raw({"resolution.journal_type": "WRITE_OFF"}))

    def test_emptying_the_disclosures_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="mandatory_disclosures"):
            validate(make_raw({"communication.mandatory_disclosures": []}))

    def test_removing_the_fmos_clause_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="fmos_clause"):
            validate(make_raw(drop=["communication.fmos_clause"]))

    def test_shortening_the_fmos_window_is_rejected(self, make_raw):
        """Six months is the scheme's number, not the bank's."""
        with pytest.raises(RulePackError, match="window_months"):
            validate(make_raw({"communication.fmos_clause.window_months": 3}))

    def test_switching_off_the_hash_chain_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="hash_chain"):
            validate(make_raw({"audit.hash_chain": "optional"}))

    def test_an_urgency_rule_without_a_verdict_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="urgency_rules"):
            validate(make_raw({"urgency_rules": [{"when": {"amount_rm": {"gte": 1}}}]}))

    def test_an_invalid_urgency_value_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="then"):
            validate(make_raw({"urgency_rules": [{"when": {"amount_rm": {"gte": 1}}, "then": "Urgent"}]}))

    def test_empty_urgency_rules_are_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="non-empty"):
            validate(make_raw({"urgency_rules": []}))


class TestLoading:
    def test_invalid_yaml_raises_a_pack_error_not_a_yaml_error(self):
        with pytest.raises(RulePackError, match="Invalid YAML"):
            load_yaml("category: [unclosed")

    def test_a_non_mapping_document_is_rejected(self):
        with pytest.raises(RulePackError):
            load_yaml("- just\n- a\n- list\n")

    def test_source_yaml_is_retained_for_the_diff_view(self, shipped_yaml):
        pack = load_yaml(shipped_yaml)
        assert pack.source_yaml == shipped_yaml

    def test_a_round_trip_through_yaml_is_stable(self, pack):
        reloaded = load_yaml(yaml.safe_dump(pack.raw, sort_keys=False))
        assert reloaded.raw == pack.raw

    def test_load_all_reads_the_repository_packs(self):
        packs = load_all()
        assert "unauthorized_transaction" in packs
        for category, loaded in packs.items():
            assert category in CATEGORIES
            assert loaded.category == category

    def test_missing_categories_tracks_progress_towards_all_seven(self):
        packs = load_all()
        outstanding = missing_categories(packs)
        assert "unauthorized_transaction" not in outstanding
        assert len(packs) + len(outstanding) == len(CATEGORIES)


class TestDisclosureContract:
    """A check the linter does not implement must not be loadable."""

    def _with_disclosure(self, make_raw, disclosure):
        raw = make_raw()
        raw["communication"]["mandatory_disclosures"] = [disclosure]
        return raw

    def test_a_typo_in_a_check_name_is_rejected(self, make_raw):
        """`must_state_amount_rm` is one character from real and would always pass."""
        with pytest.raises(RulePackError, match="unsupported check"):
            validate(
                self._with_disclosure(
                    make_raw,
                    {"id": "AMOUNT", "requirement": "State it", "must_state_amount_rm": True},
                )
            )

    def test_a_disclosure_that_checks_nothing_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="checks nothing"):
            validate(
                self._with_disclosure(
                    make_raw, {"id": "VIBES", "requirement": "Be nice to the customer"}
                )
            )

    def test_a_disclosure_without_an_id_is_rejected(self, make_raw):
        with pytest.raises(RulePackError, match="must be a mapping with an id"):
            validate(self._with_disclosure(make_raw, {"text_contains": ["hello"]}))

    def test_duplicate_ids_are_rejected(self, make_raw):
        raw = make_raw()
        raw["communication"]["mandatory_disclosures"] = [
            {"id": "BNM_ACK", "text_contains": ["acknowledge"]},
            {"id": "BNM_ACK", "text_contains": ["complaint"]},
        ]
        with pytest.raises(RulePackError, match="duplicate disclosure id"):
            validate(raw)

    def test_every_supported_check_is_accepted(self, make_raw):
        validate(
            self._with_disclosure(
                make_raw,
                {
                    "id": "EVERYTHING",
                    "requirement": "Exercise the whole contract.",
                    "note": "Kept as documentation for the compliance officer.",
                    "text_contains": ["acknowledge"],
                    "must_include_case_ref": True,
                    "must_state_deadline_date": True,
                    "must_state_amount": True,
                    "applies_when_outcome_in": ["REJECTED"],
                },
            )
        )


class TestEveryShippedPack:
    """The seven-category claim, held to the brief rather than to good intentions."""

    @pytest.fixture(scope="class")
    @classmethod
    def packs(cls):
        return load_all()

    def test_all_seven_categories_are_present(self, packs):
        assert missing_categories(packs) == ()
        assert set(packs) == set(CATEGORIES)

    def test_volume_shares_match_the_brief_and_sum_to_one(self, packs):
        expected = {
            "unauthorized_transaction": 0.35,
            "billing_error": 0.22,
            "mis_selling": 0.18,
            "atm_debit_card": 0.12,
            "insurance_takaful": 0.06,
            "loan_financing": 0.05,
            "emoney_digital": 0.02,
        }
        assert {c: p.volume_share for c, p in packs.items()} == expected
        assert round(sum(p.volume_share for p in packs.values()), 6) == 1.0

    def test_sla_tiers_match_the_brief_exactly(self, packs):
        """High: 5 WD. Medium: 20 WD. Low: 20 WD + extensions. Every category."""
        for category, pack in packs.items():
            assert pack.sla_working_days("High") == 5, category
            assert pack.sla_working_days("Medium") == 20, category
            assert pack.sla_working_days("Low") == 20, category
            assert pack.raw["sla"]["Low"]["extensions_allowed"] is True, category

    def test_no_pack_can_move_money_without_a_pass(self, packs):
        for category, pack in packs.items():
            assert pack.requires_verification == "PASS", category

    def test_every_pack_carries_the_six_month_fmos_window(self, packs):
        for category, pack in packs.items():
            assert pack.fmos["window_months"] == 6, category
            assert pack.fmos["applies_when"]["claim_amount_rm"]["lte"] == 250000, category
            assert pack.fmos["text_en"] and pack.fmos["text_ms"], category

    def test_every_pack_is_bilingual(self, packs):
        for category, pack in packs.items():
            assert pack.languages == ("en", "ms"), category

    def test_every_pack_carries_the_four_baseline_disclosures(self, packs):
        baseline = {"BNM_ACK", "BNM_CASE_REF", "BNM_TIMELINE", "CONTACT_CHANNEL"}
        for category, pack in packs.items():
            ids = {d["id"] for d in pack.mandatory_disclosures}
            assert baseline <= ids, f"{category} is missing {baseline - ids}"

    def test_every_pack_forbids_over_promising(self, packs):
        for category, pack in packs.items():
            assert "we guarantee" in pack.prohibited_phrases, category

    def test_thresholds_are_coherent(self, packs):
        """Auto-approval may not exceed the point where two people are required."""
        for category, pack in packs.items():
            assert pack.auto_approve_max_rm <= pack.dual_control_above_rm, category

    def test_every_pack_has_a_terminal_urgency_rule(self, packs):
        """No case may fall off the end of the rules with an unbounded deadline."""
        for category, pack in packs.items():
            assert "default" in pack.raw["urgency_rules"][-1], category

    def test_urgency_rules_reference_only_facts_the_pipeline_can_supply(self, packs):
        """A condition on a fact nobody produces silently never fires."""
        available = {
            "amount_rm",
            "customer_segment",
            "product_type",
            "policy_type",
            "dispute_subtype",
            "is_repeat_complaint",
            "card_still_active",
            "suspected_skimming",
            "credit_bureau_impact",
            "recall_window_open",
        }
        for category, pack in packs.items():
            for rule in pack.raw["urgency_rules"]:
                unknown = set(rule.get("when", {})) - available
                assert not unknown, f"{category} references unknown facts {unknown}"

    def test_vulnerability_outranks_amount_in_every_category(self, packs):
        """One policy stance, applied consistently across all seven packs."""
        for category, pack in packs.items():
            decision = pack.assign_urgency({"customer_segment": "vulnerable", "amount_rm": 1})
            assert decision.urgency == "High", category

    def test_mis_selling_never_auto_resolves(self, packs):
        """The category where automation assembles the file and a human decides."""
        assert packs["mis_selling"].auto_approve_max_rm == 0
        assert packs["insurance_takaful"].auto_approve_max_rm == 0

    def test_reversal_and_credit_adjustment_are_used_where_they_belong(self, packs):
        assert packs["unauthorized_transaction"].journal_type == "REVERSAL"
        assert packs["atm_debit_card"].journal_type == "REVERSAL"
        assert packs["emoney_digital"].journal_type == "REVERSAL"
        assert packs["billing_error"].journal_type == "CREDIT_ADJUSTMENT"
        assert packs["mis_selling"].journal_type == "CREDIT_ADJUSTMENT"
        assert packs["loan_financing"].journal_type == "CREDIT_ADJUSTMENT"

    def test_every_pack_uses_its_own_suspense_account(self, packs):
        """Shared GL accounts make the reconciliation story unprovable."""
        accounts = [p.debit_account for p in packs.values()]
        assert len(set(accounts)) == len(accounts)
