"""Deep analysis: playing styles, play-outs, the analysis itself and its storage."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from gin_rummy.analysis.cli import scenario_position
from gin_rummy.analysis.deep import Position, analyse, draw_samples, play_option
from gin_rummy.analysis.playout import Rules, play_out
from gin_rummy.analysis.report import format_report
from gin_rummy.analysis.style import GREEDY, PATIENT, choose_discard, live_outs, potential, takes_discard
from gin_rummy.db.deep_analyses import find_deep_analysis, get_deep_analysis, list_deep_analyses, save_deep_analysis
from gin_rummy.models import Card


def cards(codes: str) -> list[Card]:
    return [Card.parse(code) for code in codes.split()]


# The discard from quiz seed 20587: four queens, and a choice between a pair of 7s and 5-7 of spades
HAND = "QC QD QH QS AH AD 2C 3C 5S 7S 7C"
PUBLIC = "JS JD 9S 9H KS"


def position(**changes) -> Position:
    base = Position(
        decision="discard",
        hand=tuple(cards(HAND)),
        public=frozenset(cards(PUBLIC)),
        opponent_known=tuple(cards("KS")),
    )
    return replace(base, **changes)


class TestStyle:
    def test_pair_has_two_outs_and_gapped_run_has_one(self):
        keep_pair = {c.code for c, _ in live_outs(cards("QC QD QH QS AH AD 2C 3C 7S 7C"), set(cards(PUBLIC)))}
        keep_gap = {c.code for c, _ in live_outs(cards("QC QD QH QS AH AD 2C 3C 5S 7S"), set(cards(PUBLIC)))}
        assert {"7H", "7D"} <= keep_pair and "6S" not in keep_pair
        assert "6S" in keep_gap and not {"7H", "7D"} & keep_gap

    def test_a_card_already_seen_is_not_an_out(self):
        outs = {c.code for c, _ in live_outs(cards("QC QD QH QS AH AD 2C 3C 7S 7C"), set(cards(PUBLIC + " 7H")))}
        assert "7H" not in outs and "7D" in outs

    def test_greedy_ignores_near_melds(self):
        assert potential(cards("7S 7C"), set(), patience=0) == 0
        assert choose_discard(cards(HAND), set(cards(PUBLIC)), GREEDY, blocked=None).rank.value == 7

    def test_patience_values_a_pair(self):
        assert potential(cards("7S 7C KD"), set(), patience=3) > potential(cards("7S 2C KD"), set(), patience=3)

    def test_blocked_card_is_never_discarded(self):
        hand = cards("QC QD QH 2S 3S 4S AH AD AC 5D KD")
        assert choose_discard(hand, set(), GREEDY, blocked=None).code == "KD"
        assert choose_discard(hand, set(), GREEDY, blocked=Card.parse("KD")).code == "5D"

    def test_takes_the_discard_only_for_a_meld(self):
        hand = cards("7S 7C 2D 3H 9C JD KH 4S 5D AC")
        assert takes_discard(hand, Card.parse("7H"), PATIENT)
        assert not takes_discard(hand, Card.parse("AD"), PATIENT)  # lower deadwood, but no meld


class TestPlayOut:
    def test_gin_on_the_first_draw(self):
        my_hand = cards("QC QD QH 2S 3S 4S AH AD AC 5D")
        opp_hand = cards("KC KD 9C 8D 2H 4H 6H 8S 10S JC")
        deck = cards("3C 7D 9D AS")  # the AS is drawn first
        outcome = play_out(my_hand, opp_hand, deck, [], set(), True, GREEDY, GREEDY, Rules())
        assert outcome.ending == "my_gin"
        assert outcome.points == 25 + 77  # gin bonus plus the opponent's deadwood
        assert outcome.turns == 1

    def test_arguments_are_left_untouched(self):
        my_hand = cards("QC QD 9H 2S 3S 7S AH AD 8C 5D")
        opp_hand = cards("KC KD 9C 8D 2H 4H 6H 8S 10S JC")
        deck = cards("3C 7D 9D AS 4C 4D JH 10D")
        before = (list(my_hand), list(opp_hand), list(deck))
        play_out(my_hand, opp_hand, deck, [], set(), True, PATIENT, PATIENT, Rules())
        assert (my_hand, opp_hand, deck) == before

    def test_deck_running_out_scores_nothing(self):
        my_hand = cards("KC QD 9H 2S 4S 7S AH 3D 8C 5D")
        opp_hand = cards("KD 9C 8D 2H 4H 6H 8S 10S JC QH")
        outcome = play_out(my_hand, opp_hand, cards("3C 7D"), [], set(), True, GREEDY, GREEDY, Rules())
        assert outcome.ending == "deck_out" and outcome.points == 0


class TestPosition:
    def test_unknown_cards_exclude_hand_and_seen_cards(self):
        pos = position()
        assert len(pos.unknown) == 52 - 11 - 5
        assert pos.to_dict()["deck_size"] == 27

    def test_samples_give_the_opponent_their_known_cards(self):
        import random

        pos = position()
        for opp_hand, deck in draw_samples(pos, 20, random.Random(1)):
            assert Card.parse("KS") in opp_hand
            assert len(opp_hand) == 10 and len(deck) == 27
            assert not set(opp_hand) & set(deck)
            assert not (set(opp_hand) | set(deck)) & set(pos.hand)

    def test_options(self):
        assert len(position().options()) == 11
        assert "7C" not in position(blocked=Card.parse("7C")).options()
        assert position(decision="draw", hand=tuple(cards(HAND)[:10])).options() == ["deck", "pile"]

    def test_scenario_position_matches_the_quiz(self):
        pos = scenario_position(20587, "discard", draw="deck")
        assert sorted(c.code for c in pos.hand) == sorted(HAND.split())
        assert pos.actual is not None and len(pos.actual[0]) == 10
        assert pos.key == position().key

    def test_knock_position_needs_the_discard(self):
        with pytest.raises(ValueError):
            scenario_position(20587, "knock")


class TestAnalyse:
    def run(self, pos: Position, **kwargs) -> dict:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return analyse(pos, max_samples=40, batch=20, workers=1, pool=pool, **kwargs)

    def test_every_option_is_reported_under_every_style(self):
        result = self.run(position())
        assert [s["style"] for s in result["styles"]] == ["patient", "greedy", "gin hunter"]
        for style in result["styles"]:
            assert {row["option"] for row in style["options"]} == set(position().options())
            assert style["options"][0]["option"] == style["best"]
            assert style["options"][0]["behind_leader"] == 0
        assert result["best"] == result["styles"][0]["best"]
        assert result["samples"] <= 40

    def test_same_sample_seed_gives_the_same_result(self):
        first, second = self.run(position(), sample_seed=5), self.run(position(), sample_seed=5)
        first.pop("seconds"), second.pop("seconds")
        assert first == second

    def test_notes_list_the_outs_each_discard_keeps(self):
        notes = self.run(position())["option_notes"]
        assert {"7H", "7D"} <= {o["card"] for o in notes["5S"]["outs"]}
        assert notes["5S"]["deadwood_after"] == 21 and notes["7C"]["deadwood_after"] == 19

    def test_real_deal_is_played_when_known(self):
        pos = scenario_position(20587, "discard")
        result = self.run(pos)
        assert set(result["styles"][0]["actual_deal"]) == set(pos.options())

    def test_draw_and_knock_decisions(self):
        draw = self.run(scenario_position(20587, "draw"))
        assert {row["option"] for row in draw["styles"][0]["options"]} == {"deck", "pile"}
        knock_pos = position(
            decision="knock", hand=tuple(cards("QC QD QH QS AH AD AC 2C 3C 4C")), pending_discard=Card.parse("5S")
        )
        knock = self.run(knock_pos)
        assert knock["best"] == "knock"  # gin

    def test_play_option_discards_the_chosen_card(self):
        import random

        pos = position()
        sample = draw_samples(pos, 1, random.Random(2))[0]
        outcome = play_option(pos, "5S", sample, PATIENT)
        assert outcome.ending in {
            "my_gin",
            "my_knock",
            "my_knock_undercut",
            "opp_gin",
            "opp_knock",
            "opp_knock_undercut",
            "deck_out",
        }

    def test_report_mentions_the_best_option(self):
        result = self.run(position())
        assert "Best:" in format_report(result)


class TestStorage:
    def result(self, samples: int = 40) -> dict:
        return {
            "position": {"decision": "discard", "seed": 7},
            "position_key": "discard|key",
            "best": "5S",
            "confidence": "clear",
            "samples": samples,
            "seconds": 1.5,
            "styles": [],
        }

    def test_round_trip(self, tmp_path):
        db = tmp_path / "test.db"
        analysis_id = save_deep_analysis(self.result(), db)
        loaded = get_deep_analysis(analysis_id, db)
        assert loaded is not None and loaded["best"] == "5S" and loaded["id"] == analysis_id
        assert get_deep_analysis(analysis_id + 1, db) is None

    def test_lookup_prefers_the_largest_sample(self, tmp_path):
        db = tmp_path / "test.db"
        save_deep_analysis(self.result(samples=4000), db)
        save_deep_analysis(self.result(samples=200), db)
        found = find_deep_analysis("discard|key", db)
        assert found is not None and found["samples"] == 4000
        assert find_deep_analysis("other", db) is None

    def test_list_by_seed(self, tmp_path):
        db = tmp_path / "test.db"
        save_deep_analysis(self.result(), db)
        assert [row["seed"] for row in list_deep_analyses(db_path=db)] == [7]
        assert list_deep_analyses(seed=8, db_path=db) == []
