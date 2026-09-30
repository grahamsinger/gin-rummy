"""Plain-text report of a deep analysis result."""

from __future__ import annotations

from typing import Any

from gin_rummy.models import Card

ENDING_LABELS = {
    "my_gin": "you gin",
    "my_knock": "you knock and win",
    "my_knock_undercut": "you knock, undercut",
    "opp_gin": "opponent gins",
    "opp_knock": "opponent knocks and wins",
    "opp_knock_undercut": "you undercut",
    "deck_out": "deck runs out",
}


def pretty(option: str) -> str:
    """A card code as a card ('7C' -> '7♣'); other options unchanged."""
    try:
        return str(Card.parse(option))
    except ValueError:
        return option


def _cards(codes: list[str]) -> str:
    return " ".join(pretty(c) for c in codes) or "-"


def _meld(name: str) -> str:
    return _cards(name.split())


def format_report(result: dict[str, Any]) -> str:
    position = result["position"]
    lines = []
    title = f"Deep analysis: {position['decision']} decision"
    if position.get("seed") is not None:
        title += f", seed {position['seed']}"
    lines += [title, "=" * len(title)]
    lines.append(f"Hand:            {_cards(position['hand'])}")
    if position.get("discard_top"):
        lines.append(f"Card on offer:   {pretty(position['discard_top'])}")
    if position.get("pending_discard"):
        lines.append(f"Discarding:      {pretty(position['pending_discard'])}")
    lines.append(f"Seen face up:    {_cards(position['public'])}")
    lines.append(f"Opponent holds:  {_cards(position['opponent_known'])}")
    lines.append(f"Deck:            {position['deck_size']} cards")
    lines.append("")

    best = f"Best: {pretty(result['best'])}"
    if result.get("level_with"):
        best += f", level with {_cards(result['level_with'])}"
    lines.append(best)
    for style in result["styles"][1:]:
        standing = style.get("main_best")
        if standing == "best":
            lines.append(f"  also best when playing on '{style['style']}'")
        elif standing == "level":
            lines.append(f"  level with {pretty(style['best'])} when playing on '{style['style']}'")
        else:
            lines.append(f"  BEHIND {pretty(style['best'])} when playing on '{style['style']}'")
    lines.append(f"{result['samples']} deals of the hidden cards, {result['seconds']:.0f}s")

    notes = result.get("option_notes") or {}
    for style in result["styles"]:
        lines.append("")
        holds = f"holds near melds for {style['patience']} draws" if style["patience"] else "lowest deadwood first"
        knock = f"knocks at {style['knock_at']} or less" if style["knock_at"] else "only goes out with gin"
        lines.append(
            f"Style '{style['style']}' ({holds}, {knock}): best {pretty(style['best'])}, {style['confidence']}"
        )
        lines.append(
            f"  {'option':<9}{'points':>8}{'+/-':>6}{'behind':>9}{'+/-':>6}{'win %':>8}{'deals':>8}   real deal"
        )
        for row in style["options"]:
            actual = (style.get("actual_deal") or {}).get(row["option"])
            real = f"{actual['points']:+d} ({ENDING_LABELS[actual['ending']]})" if actual else ""
            lines.append(
                f"  {pretty(row['option']):<9}{row['points']:>+8.2f}{1.96 * row['points_se']:>6.2f}"
                f"{-row['behind_leader']:>+9.2f}{1.96 * row['behind_leader_se']:>6.2f}"
                f"{100 * row['win_rate']:>8.1f}{row['samples']:>8}   {real}"
            )
        top = style["options"][:3]
        lines.append("  Why (leading options):")
        for row in top:
            note = notes.get(row["option"])
            if note:
                outs = ", ".join(f"{pretty(o['card'])} (-{o['saves']})" for o in note["outs"]) or "none"
                lines.append(
                    f"    {pretty(row['option'])}: deadwood {note['deadwood_after']} now; cards that meld: {outs}"
                )
            else:
                lines.append(f"    {pretty(row['option'])}:")
            melds = ", ".join(f"{_meld(m['meld'])} {100 * m['rate']:.0f}%" for m in row["new_melds"])
            if melds:
                lines.append(f"      new melds made by the end: {melds}")
            endings = ", ".join(f"{ENDING_LABELS[e]} {100 * r:.0f}%" for e, r in row["endings"].items() if r >= 0.005)
            lines.append(f"      endings: {endings}")
            if position["decision"] != "knock":
                lines.append(
                    f"      opponent takes your discard {100 * row['discard_taken']:.0f}% of the time; "
                    f"hand lasts {row['turns']} more turns"
                )
    lines.append("")
    lines.append("points: average for the hand, + is good for you. +/- is the 95% range.")
    lines.append("behind: gap to the best option on the same deals, which is more precise than comparing points.")
    lines.append("real deal: the same play-out against the cards that were actually hidden (one game, so mostly luck).")
    return "\n".join(lines)
