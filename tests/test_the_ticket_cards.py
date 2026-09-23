"""The two cards the ticket graph is built from, as the gallery shows them (#48).

The snapshot check in `test_the_gallery.py` holds how each card looks at rest
against the prototype. These hold what it cannot: that every state has both
sizes, what each foot says, that state is told by shape and tone and never by
hue, and that no name is ever cut off.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Locator, Page

from specimens import THEMES, choose, disagreements, set_theme

pytestmark = [pytest.mark.git, pytest.mark.browser]

# Every state a ticket shows a card in, with the foot it carries there
# (docs/screens/ticket-graph.md). Landed has no card: it folds into the start line.
FEET = {
    "landing": "In the merge queue",
    "building": "Working \N{MIDDLE DOT} 12 min",
    "asked": "Asked you a question",
    "held": "Held \N{MIDDLE DOT} a blocking finding",
    "takeable": "Nobody on it yet",
    "takeable-at-cap": "Starts when a slot frees",
    "blocked-on-one": "Waiting on Check room tone",
    "blocked-on-many": "Waiting on 5 tickets",
}
WORDS = {
    "landing": "Landing",
    "building": "Building",
    "asked": "Asked",
    "held": "Held",
    "takeable": "Takeable",
    "takeable-at-cap": "Takeable",
    "blocked-on-one": "Blocked",
    "blocked-on-many": "Blocked",
}
NAMES = {
    "landing": "Flag peaks above \N{MINUS SIGN}3 dB",
    "building": "Flag a noise floor above \N{MINUS SIGN}60 dB",
    "asked": "Check room tone",
    "held": "Warn when no retail sample is chosen",
    "takeable": "Show compliance status on My Books",
    "takeable-at-cap": "Show compliance status on My Books",
    "blocked-on-one": "Explain a failing chapter",
    "blocked-on-many": "Block ACX export",
}
NUMBERS = {
    "landing": 127,
    "building": 128,
    "asked": 130,
    "held": 129,
    "takeable": 132,
    "takeable-at-cap": 132,
    "blocked-on-one": 131,
    "blocked-on-many": 133,
}
SIZES = ["card", "name-only"]


def _card(page: Page, specimen: str) -> Locator:
    return page.locator(f'[data-specimen="{specimen}"]').get_by_role("button")


def _name(card: Locator) -> Locator:
    """The card's name: the middle of a full card's three lines, the last span of
    a name-only card."""
    return card.locator(":scope > span").nth(1)


def _foot(card: Locator) -> Locator:
    return card.locator(":scope > span").nth(2)


def _is_card(name: str) -> bool:
    return name.startswith(("card-", "name-only-"))


def test_both_card_sizes_render_in_every_state(gallery: Page) -> None:
    drawn = gallery.locator("[data-specimen]").evaluate_all(
        "specimens => specimens.map(s => s.dataset.specimen)"
    )

    for size in SIZES:
        for state in FEET:
            assert f"{size}-{state}" in drawn


@pytest.mark.parametrize("state", FEET)
def test_a_full_card_carries_its_state_word_its_name_and_its_foot(
    gallery: Page, state: str
) -> None:
    card = _card(gallery, f"card-{state}")

    parts = card.locator(":scope > span").all_text_contents()

    assert parts == [f"{WORDS[state]}#{NUMBERS[state]}", NAMES[state], FEET[state]]


def test_a_name_only_card_is_its_glyph_name_and_id(gallery: Page) -> None:
    card = _card(gallery, "name-only-takeable")

    assert card.inner_text() == "Show compliance status on My Books #132"
    assert card.locator(":scope > span").count() == 2
    assert card.locator(".st-take").get_attribute("aria-hidden") == "true"


@pytest.mark.parametrize("size", SIZES)
def test_a_card_names_its_ticket_and_its_state_to_a_person_who_cannot_see_it(
    gallery: Page, size: str
) -> None:
    for state, word in WORDS.items():
        name = _card(gallery, f"{size}-{state}").get_attribute("aria-label")
        assert name is not None and name.endswith(f", {word}"), f"{size}-{state}: {name}"


def test_a_selected_card_says_it_is_selected(gallery: Page) -> None:
    for size in SIZES:
        assert _card(gallery, f"{size}-selected").get_attribute("aria-pressed") == "true"
        assert _card(gallery, f"{size}-takeable").get_attribute("aria-pressed") == "false"


# How a card's edge reads, by state: shape (solid or dashed) and tone (ink or
# quiet), never hue (docs/screens/ticket-graph.md).
_EDGE = """card => {
    const probe = document.createElement("i");
    card.append(probe);
    const tone = token => {
        probe.style.color = `var(${token})`;
        return getComputedStyle(probe).color;
    };
    const ink = tone("--fg"), quiet = [tone("--border"), tone("--line")];
    probe.remove();
    const style = getComputedStyle(card);
    const edge = style.borderTopColor;
    return [style.borderTopStyle, edge === ink ? "ink" : quiet.includes(edge) ? "quiet" : edge];
}"""


@pytest.mark.parametrize("size", SIZES)
def test_a_cards_state_is_told_by_the_shape_and_tone_of_its_edge(gallery: Page, size: str) -> None:
    edges = {state: _card(gallery, f"{size}-{state}").evaluate(_EDGE) for state in FEET}

    assert edges == {
        "landing": ["solid", "quiet"],
        "building": ["solid", "quiet"],
        "asked": ["solid", "ink"],
        "held": ["solid", "ink"],
        "takeable": ["solid", "ink"],
        "takeable-at-cap": ["solid", "ink"],
        "blocked-on-one": ["dashed", "quiet"],
        "blocked-on-many": ["dashed", "quiet"],
    }


@pytest.mark.parametrize("theme", THEMES)
def test_no_card_paints_in_a_hue(gallery: Page, theme: str) -> None:
    choose(gallery, theme)

    hued = gallery.locator("[data-specimen]").evaluate_all(
        """specimens => {
            const canvas = document.createElement("canvas")
                .getContext("2d", { willReadFrequently: true });
            // The page's own inks sit a hair off grey; the accent is far from it.
            const chroma = colour => {
                canvas.clearRect(0, 0, 1, 1);
                canvas.fillStyle = colour;
                canvas.fillRect(0, 0, 1, 1);
                const [r, g, b, a] = canvas.getImageData(0, 0, 1, 1).data;
                return a === 0 ? 0 : Math.max(r, g, b) - Math.min(r, g, b);
            };
            return specimens
                .filter(s => /^(card|name-only)-/.test(s.dataset.specimen))
                .flatMap(s => [s, ...s.querySelectorAll("*")].map(e => {
                    const style = getComputedStyle(e);
                    return [s.dataset.specimen,
                            style.color, style.backgroundColor, style.borderTopColor];
                }))
                .filter(([, ...colours]) => colours.some(c => chroma(c) > 24));
        }"""
    )

    assert hued == []


# Whether every line of an element's text is drawn whole: nothing clamps it,
# ends it in an ellipsis or clips it, and each line sits inside its card. A
# fractional height rounds scrollHeight a pixel past the box, which is not a cut.
_UNCUT = """element => {
    const style = getComputedStyle(element);
    const card = element.closest("button").getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(element);
    const clamped = style.display === "-webkit-box";
    const clipped = style.overflowY !== "visible"
        && element.scrollHeight - element.clientHeight > 1;
    return !clamped && !clipped && style.textOverflow !== "ellipsis"
        && [...range.getClientRects()].every(r => r.top >= card.top && r.bottom <= card.bottom
            && r.left >= card.left && r.right <= card.right);
}"""


@pytest.mark.parametrize("size", SIZES)
def test_a_long_ticket_name_wraps_and_is_never_cut_off(gallery: Page, size: str) -> None:
    name = _name(_card(gallery, f"{size}-long-name"))

    assert name.inner_text().startswith("Explain a loudness failure")
    assert name.evaluate(_UNCUT), "the long name is cut off"
    lines = name.evaluate(
        """e => Math.round(
            e.getBoundingClientRect().height / parseFloat(getComputedStyle(e).lineHeight))"""
    )
    assert lines > {"card": 3, "name-only": 2}[size], "the long name no longer overruns its clamp"


def test_a_blocker_named_in_a_foot_is_never_cut_off(gallery: Page) -> None:
    foot = _foot(_card(gallery, "card-long-name"))

    assert foot.inner_text() == "Waiting on Normalise loudness to the ACX range on request"
    assert foot.evaluate(_UNCUT), "the blocker's name is cut off"


@pytest.mark.parametrize("theme", THEMES)
def test_every_card_answers_the_pointer_as_the_prototype_does(
    gallery: Page, reference: Page, theme: str
) -> None:
    choose(gallery, theme)
    set_theme(reference, theme)

    assert disagreements(gallery, reference, _is_card, hover=True) == []
