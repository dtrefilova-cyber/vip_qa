"""Unit tests for VIP deterministic scoring (synced with portal 79064ed)."""

from core.vip_friendly_scoring import (
    CallToActionFacts,
    EaseFacts,
    EaseLevel,
    FriendlyDevelopmentFacts,
    build_perfect_friendly_facts,
    score_call_to_action,
    score_ease,
    score_friendly_development,
    score_quoted_closing,
    score_vip_friendly,
)
from core.vip_scoring_common import (
    ClosingFacts,
    ContactFacts,
    Objection,
    ObjectionHandling,
    PrepFacts,
    SharedCallContext,
    score_closing,
    score_contact,
    score_prep,
)
from core.vip_short_scoring import (
    SlipHandlingFacts,
    build_perfect_short90s_facts,
    score_slip_handling,
    score_vip_short_90s,
)


def test_contact_all_four_elements():
    f = ContactFacts(
        greeted=True,
        used_client_name=True,
        named_project=True,
        availability_check_relevant=True,
        availability_check_done=True,
    )
    assert score_contact(f).points == 5.0


def test_contact_missing_one():
    f = ContactFacts(
        greeted=True,
        used_client_name=False,
        named_project=True,
        availability_check_relevant=True,
        availability_check_done=True,
    )
    result = score_contact(f)
    assert result.points == 2.5
    assert any("ім'я клієнта" in r for r in result.reasons)


def test_contact_missing_names_all_elements():
    f = ContactFacts(
        greeted=False,
        used_client_name=False,
        named_project=False,
        availability_check_done=False,
    )
    result = score_contact(f)
    assert result.points == 0.0
    blob = " ".join(result.reasons)
    assert "привітання" in blob
    assert "ім'я клієнта" in blob
    assert "назва проєкту" in blob
    assert "перевірка зручності" in blob


def test_prep_no_objections_auto_max():
    f = PrepFacts(objections_present=False, objections=[])
    assert score_prep(f).points == 10.0


def test_prep_worst_of_multiple_objections():
    f = PrepFacts(
        objections_present=True,
        objections=[
            Objection(type="no_time", handling=ObjectionHandling.RESOLVED_WITH_CHECK),
            Objection(type="no_payout", handling=ObjectionHandling.FORMAL),
        ],
    )
    assert score_prep(f).points == 2.5


def test_slip_handling_all_done():
    f = SlipHandlingFacts(
        client_attempted_to_end_call=True,
        reason_stated_by_client=True,
        reason_clarified_by_manager=False,
        manager_reacted_appropriately=True,
        proposed_callback=True,
        specified_concrete_time=True,
        confirmed_agreement_or_clear_refusal=True,
        client_flatly_refused_any_callback=False,
    )
    assert score_slip_handling(f, SharedCallContext()).points == 10.0


def test_vip_friendly_max_score_is_57_5():
    result = score_vip_friendly(build_perfect_friendly_facts(), SharedCallContext())
    assert result.max_score == 57.5
    assert result.total_score == 57.5
    assert result.rubric_version == "v1_friendly_ease75"


def test_ease_high_is_7_5():
    assert score_ease(EaseFacts(level=EaseLevel.HIGH, signals=[])).points == 7.5
    assert score_ease(EaseFacts(level=EaseLevel.HIGH, signals=[])).max_points == 7.5


def test_vip_short_90s_max_score_is_30():
    result = score_vip_short_90s(build_perfect_short90s_facts(), SharedCallContext())
    assert result.max_score == 30.0
    assert result.total_score == 30.0


def test_friendly_development_full_signals():
    f = FriendlyDevelopmentFacts(
        asked_relevant_personal_questions=True,
        followed_up_on_client_answer=True,
        supported_client_initiated_topic=True,
        returned_to_personal_info_later=True,
        evidence=["Менеджер: як пройшли вихідні?", "Менеджер: а що плануєте?"],
    )
    assert score_friendly_development(f, "Менеджер: як пройшли вихідні?\nМенеджер: а що плануєте?").points == 7.5


def test_closing_missing_names_specific_element():
    f = ClosingFacts(
        asked_if_more_questions=True,
        said_goodbye=False,
        thanked_and_left_contact_open=True,
    )
    result = score_closing(f, SharedCallContext())
    assert result.points == 2.5
    assert any("прощання" in r for r in result.reasons)


def _closing(*, thanked: bool, goodbye: bool = True, questions: bool = True, quote_mode: bool = False):
    return ClosingFacts(
        asked_if_more_questions=questions,
        said_goodbye=goodbye,
        thanked_and_left_contact_open=thanked,
        quote_mode=quote_mode,
    )


def test_missing_thank_you_does_not_reduce_an_otherwise_good_close():
    """Подяка і відкритий контакт не ріжуть завершення, якщо решта закриття є."""
    ctx = SharedCallContext()
    plain_without = score_closing(_closing(thanked=False), ctx)
    plain_with = score_closing(_closing(thanked=True), ctx)
    assert plain_without.points == 5.0
    assert plain_without.points == plain_with.points
    assert plain_without.reasons == []

    quoted_without = score_quoted_closing(_closing(thanked=False, quote_mode=True))
    quoted_with = score_quoted_closing(_closing(thanked=True, quote_mode=True))
    assert quoted_without.points == 5.0
    assert quoted_without.points == quoted_with.points
    assert quoted_without.reasons == []

    goodbye_gap_without = score_closing(_closing(thanked=False, goodbye=False), ctx)
    goodbye_gap_with = score_closing(_closing(thanked=True, goodbye=False), ctx)
    assert goodbye_gap_without.points == goodbye_gap_with.points == 2.5

    short_with = score_vip_short_90s(build_perfect_short90s_facts(), ctx)
    short_facts = build_perfect_short90s_facts()
    short_facts.closing.thanked_and_left_contact_open = False
    short_without = score_vip_short_90s(short_facts, ctx)
    assert short_without.total_score == short_with.total_score == 30.0
    assert next(item.points for item in short_without.criteria if item.key == "closing") == 5.0

    def friendly(thanked: bool):
        facts = build_perfect_friendly_facts()
        facts.closing.thanked_and_left_contact_open = thanked
        facts.closing.quote_mode = True
        return score_vip_friendly(facts, ctx)

    friendly_without = friendly(False)
    friendly_with = friendly(True)
    assert friendly_without.total_score == friendly_with.total_score == 57.5
    closing = next(item for item in friendly_without.criteria if item.key == "closing")
    assert closing.points == 5.0
    assert not any("подяк" in reason for reason in closing.reasons)


def test_closing_guides_do_not_require_thank_you():
    from guides_content import GUIDE_VIP_FRIENDLY, GUIDE_VIP_SHORT_90S

    phrase = "подякував за час та залишив можливість подальшого контакту"
    for guide in (GUIDE_VIP_SHORT_90S, GUIDE_VIP_FRIENDLY):
        item = next(row for row in guide if row["title"] == "Завершення")
        blob = " ".join(str(item.get(key) or "") for key in ("description", "scale", "notes"))
        assert phrase not in blob
    short = next(row for row in GUIDE_VIP_SHORT_90S if row["title"] == "Завершення")
    assert "уточнив, чи немає у клієнта запитань" in short["description"]
    assert "попрощався" in short["description"]


def test_ai_models_registers_portal_tasks():
    from ai_models import VIP_FACT_TASKS, get_task_config

    assert "facts_vip_short_contact" in VIP_FACT_TASKS
    assert "facts_vip_friendly_cta" in VIP_FACT_TASKS
    cfg = get_task_config("facts_vip_friendly_bonus")
    assert cfg["registered"] is True
    assert cfg["model"]


def _bonus(**overrides):
    from core.vip_friendly_scoring import BonusOfferFacts

    fields = dict(
        deposit_bonus_offered_first=True,
        all_terms_stated=True,
        benefits_explained=False,
        bonus_devalued=False,
        no_deposit_bonus_applicable=False,
        no_deposit_bonus_offered_after=False,
        betking_x2_applicable=False,
        betking_x2_booster_offered=False,
        fs_applicable=False,
    )
    fields.update(overrides)
    return BonusOfferFacts(**fields)


def _bonus_with_terms(*, fs="n/a", fs_applicable=False, wager="вейджера немає", deposit_quote=""):
    from core.vip_friendly_scoring import BonusOfferFacts, BonusTermsStated

    return BonusOfferFacts(
        deposit_bonus_offered_first=True,
        all_terms_stated=False,
        benefits_explained=False,
        fs_applicable=fs_applicable,
        first_deposit_bonus_quote=deposit_quote,
        terms_stated=BonusTermsStated(
            min_deposit="від 300 гривень",
            validity="діє три дні",
            wager=wager,
            fs_count_and_bet=fs,
        ),
    )


def test_friendly_bonus_checklist_is_in_prompt_and_guide_only():
    from guides_content import GUIDE_VIP_FRIENDLY, GUIDE_VIP_SHORT_90S
    from prompts_vip_friendly import get_vip_friendly_analysis_prompt, get_vip_friendly_bonus_prompt
    from prompts_vip_short import get_vip_short_90s_analysis_prompt
    from core.vip_friendly_scoring import FRIENDLY_BONUS_FIVE_POINT_RULES

    item = next(row for row in GUIDE_VIP_FRIENDLY if row["title"] == "Пропозиція бонусів")
    assert item["description"] == FRIENDLY_BONUS_FIVE_POINT_RULES
    assert FRIENDLY_BONUS_FIVE_POINT_RULES in get_vip_friendly_bonus_prompt()
    assert FRIENDLY_BONUS_FIVE_POINT_RULES in get_vip_friendly_analysis_prompt()
    assert "2,5 — запропонував, але без однієї обов'язкової умови або формально" in item["scale"]
    assert "0 — не запропонував депозитний першим / почав із бездепу / знецінив." in item["scale"]
    assert "5 балів — виконано всі обов'язкові умови бонусу" not in get_vip_short_90s_analysis_prompt()
    short_blob = "\n".join(
        " ".join(str(row.get(key) or "") for key in ("title", "description", "scale", "notes"))
        for row in GUIDE_VIP_SHORT_90S
    )
    assert "5 балів — виконано всі обов'язкові умови бонусу" not in short_blob


def test_benefits_are_required_only_when_the_client_hesitates():
    from core.vip_friendly_scoring import score_bonus_offer

    assert score_bonus_offer(_bonus()).points == 5.0
    hesitating = score_bonus_offer(_bonus(client_hesitates=True))
    assert hesitating.points == 2.5
    assert "переваги, коли клієнт вагається" in hesitating.reasons[0]
    assert score_bonus_offer(_bonus(client_hesitates=True, benefits_explained=True)).points == 5.0

    look = "Клієнт: [0:20] Подивлюсь"
    assert score_bonus_offer(_bonus(), look).points == 2.5
    assert score_bonus_offer(_bonus(benefits_explained=True), look).points == 5.0
    unsure = "Клієнт: [0:20] Не знаю, чи заберу"
    assert score_bonus_offer(_bonus(), unsure).points == 2.5


def test_unprofitable_bonus_is_not_a_bonus_offer_miss():
    from core.vip_friendly_scoring import score_bonus_offer

    objection = "Клієнт: [0:20] Бонус невигідний, нічого не дає"
    scored = score_bonus_offer(_bonus(client_hesitates=True), objection)
    assert scored.points == 5.0
    assert "переваги" not in " ".join(scored.reasons)

    mixed = "Клієнт: [0:20] Не знаю, чи заберу, бонус нічого не дає"
    assert score_bonus_offer(_bonus(), mixed).points == 5.0

    both = "Клієнт: [0:18] Бонус нічого не дає\nКлієнт: [0:22] Не знаю, чи заберу"
    assert score_bonus_offer(_bonus(), both).points == 2.5


def test_no_deposit_and_betking_booster_are_not_always_required():
    from core.vip_friendly_scoring import score_bonus_offer

    assert score_bonus_offer(_bonus()).points == 5.0
    skipped = score_bonus_offer(_bonus(no_deposit_bonus_applicable=True))
    assert skipped.points == 2.5
    assert "бездепозитний бонус" in skipped.reasons[0]
    offered = _bonus(no_deposit_bonus_applicable=True, no_deposit_bonus_offered_after=True)
    assert score_bonus_offer(offered).points == 5.0

    assert score_bonus_offer(_bonus(betking_x2_booster_offered=False)).points == 5.0
    betking = score_bonus_offer(_bonus(betking_x2_applicable=True))
    assert betking.points == 2.5
    assert "бустер Х2" in betking.reasons[0]
    assert score_bonus_offer(_bonus(betking_x2_applicable=True, betking_x2_booster_offered=True)).points == 5.0


def test_bonus_terms_require_wager_and_fs_only_when_fs_apply():
    from core.vip_friendly_scoring import score_bonus_offer

    assert score_bonus_offer(_bonus_with_terms()).points == 5.0
    assert score_bonus_offer(_bonus_with_terms(fs=None)).points == 5.0
    assert score_bonus_offer(_bonus_with_terms(wager="n/a")).points == 2.5
    spins_only = score_bonus_offer(_bonus_with_terms(fs="20 фріспінів", fs_applicable=True))
    assert spins_only.points == 2.5
    voiced = _bonus_with_terms(fs="20 фріспінів, ставка 5 гривень", fs_applicable=True)
    assert score_bonus_offer(voiced).points == 5.0
    in_offer = _bonus_with_terms(
        fs=None,
        deposit_quote="депозитний бонус і 20 фріспінів, ставка 5 гривень",
    )
    assert score_bonus_offer(in_offer).points == 5.0
    named_only = _bonus_with_terms(fs=None, deposit_quote="депозитний бонус, будуть фріспіни")
    assert score_bonus_offer(named_only).points == 2.5
    absent = _bonus_with_terms(fs="n/a", deposit_quote="депозитний бонус без фріспінів")
    assert score_bonus_offer(absent).points == 5.0


def test_zero_and_half_bands_stay_for_structure_devalue_and_a_missing_term():
    from core.vip_friendly_scoring import score_bonus_offer

    missing_deposit = score_bonus_offer(_bonus(deposit_bonus_offered_first=False))
    assert missing_deposit.points == 0.0
    devalued = score_bonus_offer(_bonus(bonus_devalued=True, benefits_explained=True))
    assert devalued.points == 0.0
    assert devalued.reasons == ["Не запропонував депозитний бонус першим / знецінив бонус"]
    missing_terms = score_bonus_offer(_bonus(all_terms_stated=False))
    assert missing_terms.points == 2.5


def test_grounded_bonus_offer_follows_the_new_checklist():
    from core.vip_friendly_scoring import BonusOfferFacts, ground_bonus_offer, score_bonus_offer, score_vip_friendly_call

    dialogue = "\n".join([
        "Менеджер: [0:10] депозитний бонус від 300 гривень, діє три дні, вейджера немає",
        "Клієнт: [0:20] Добре, заберу сьогодні",
    ])
    raw = {
        "first_deposit_bonus_quote": "депозитний бонус від 300 гривень, діє три дні, вейджера немає",
        "first_deposit_bonus_time": "0:10",
        "first_no_deposit_bonus_quote": "",
        "terms_stated": {
            "min_deposit": "від 300 гривень",
            "validity": "діє три дні",
            "wager": "вейджера немає",
            "fs_count_and_bet": "n/a",
        },
        "benefits_quote": "",
        "no_deposit_bonus_applicable": False,
        "betking_x2_applicable": False,
        "fs_applicable": False,
    }
    grounded = BonusOfferFacts.model_validate(ground_bonus_offer(raw, dialogue))
    assert grounded.deposit_bonus_offered_first is True
    assert grounded.benefits_explained is False
    assert grounded.client_hesitates is False
    assert grounded.fs_applicable is False
    assert grounded.all_terms_stated is True
    assert score_bonus_offer(grounded, dialogue).points == 5.0

    hesitant = dialogue + "\nКлієнт: [0:24] Не знаю, чи заберу"
    hesitant_facts = BonusOfferFacts.model_validate(ground_bonus_offer(raw, hesitant))
    assert hesitant_facts.client_hesitates is True
    assert score_bonus_offer(hesitant_facts, hesitant).points == 2.5
    with_benefits = dict(raw, benefits_quote="перевага в тому, що відіграш швидший")
    hesitant_benefits = hesitant + "\nМенеджер: [0:28] перевага в тому, що відіграш швидший"
    explained = BonusOfferFacts.model_validate(ground_bonus_offer(with_benefits, hesitant_benefits))
    assert explained.benefits_explained is True
    assert score_bonus_offer(explained, hesitant_benefits).points == 5.0

    applicable = dict(raw, no_deposit_bonus_applicable=True)
    missed = BonusOfferFacts.model_validate(ground_bonus_offer(applicable, dialogue))
    assert missed.no_deposit_bonus_applicable is True
    assert missed.no_deposit_bonus_offered_after is False
    assert score_bonus_offer(missed, dialogue).points == 2.5

    later = dialogue + "\nМенеджер: [0:40] бездепозитний бонус 50 гривень на баланс"
    after = dict(
        applicable,
        first_no_deposit_bonus_quote="бездепозитний бонус 50 гривень на баланс",
        first_no_deposit_bonus_time="0:40",
    )
    ordered = BonusOfferFacts.model_validate(ground_bonus_offer(after, later))
    assert ordered.deposit_bonus_offered_first is True
    assert ordered.no_deposit_bonus_offered_after is True
    assert score_bonus_offer(ordered, later).points == 5.0

    betking_dialogue = dialogue + "\nМенеджер: [0:50] додатково бустер х2"
    without_booster = BonusOfferFacts.model_validate(
        ground_bonus_offer(dict(raw, betking_x2_applicable=True), betking_dialogue)
    )
    assert without_booster.betking_x2_booster_offered is False
    assert score_bonus_offer(without_booster, betking_dialogue).points == 2.5
    with_booster = dict(raw, betking_x2_applicable=True, x2_quote="додатково бустер х2")
    boosted = BonusOfferFacts.model_validate(ground_bonus_offer(with_booster, betking_dialogue))
    assert boosted.betking_x2_booster_offered is True
    assert score_bonus_offer(boosted, betking_dialogue).points == 5.0

    devalued_dialogue = dialogue + "\nМенеджер: [0:55] заберете, якщо захочете"
    devalued = BonusOfferFacts.model_validate(
        ground_bonus_offer(dict(raw, devalue_quote="заберете, якщо захочете"), devalued_dialogue)
    )
    assert devalued.bonus_devalued is True
    assert score_bonus_offer(devalued, devalued_dialogue).points == 0.0

    piped = score_vip_friendly_call({"bonus_offer": raw}, dialogue=dialogue)
    bonus = next(item for item in piped["criteria"] if item["key"] == "bonus_offer")
    assert bonus["points"] == 5.0


def test_missing_benefits_do_not_cut_a_perfect_friendly_call_without_hesitation():
    facts = build_perfect_friendly_facts()
    facts.bonus_offer.benefits_explained = False
    full = score_vip_friendly(facts, SharedCallContext())
    bonus = next(item for item in full.criteria if item.key == "bonus_offer")
    assert bonus.points == 5.0
    assert full.total_score == 57.5

    facts.bonus_offer.client_hesitates = True
    hesitant = score_vip_friendly(facts, SharedCallContext())
    bonus = next(item for item in hesitant.criteria if item.key == "bonus_offer")
    assert bonus.points == 2.5
    assert hesitant.total_score == 55.0
