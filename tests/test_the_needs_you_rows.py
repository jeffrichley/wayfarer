"""The Needs you rows, as the gallery shows them (#50).

The snapshot check in `test_the_gallery.py` holds how each row looks. These hold
what each one says: every kind's own sentence, what it holds up, whose effort it
is, and what a resolved one says happened.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Locator, Page

from specimens import THEMES, choose, disagreements, set_theme

pytestmark = [pytest.mark.git, pytest.mark.browser]

KINDS = ["environment", "question", "held", "review", "drafts", "ship", "orphan", "closed"]

# Each kind as the desk's queue says it: kind and effort, the name with its id
# riding after it, the reason or question, and what it holds up.
DESK = {
    "environment": [
        "Environment · Every effort",
        "Every cascade is paused",
        "Docker stopped answering; two tickets went back on the frontier",
    ],
    "question": [
        "Question · ACX compliance",
        "Require opening and closing credits#130",
        "Should DOCX books without credits fail or warn?",
        "Holds up 4 tickets · 2 start the moment it lands",
    ],
    "held": [
        "Held · ACX compliance",
        "Check room tone at the head and tail of each chapter#131",
        "/code-review found a gap against the spec that blocks landing",
        "Holds up 3 tickets · 1 starts the moment it lands",
    ],
    "review": [
        "In review · ACX compliance",
        "Flag peaks above \N{MINUS SIGN}3 dB#127",
        "Clean and green, waiting on your approval",
        "Holds up 1 ticket",
    ],
    "drafts": [
        "Drafts · Retail sample",
        "Retail sample suggestions",
        "6 tickets drafted, waiting on your check",
    ],
    "ship": [
        "Ship the effort · Voice casting",
        "Per-chapter voice casting",
        "Every ticket landed · one review to ship it",
    ],
    "orphan": [
        "Leftover container · ACX compliance",
        "Flag a noise floor above \N{MINUS SIGN}60 dB#128",
        "Its container outlived its session",
    ],
    "closed": [
        "Closed with a live session · ACX compliance",
        "Flag chapters longer than 120 minutes#129",
        "Closed on GitHub while its session runs",
    ],
}

WORDS = {
    "environment": "Paused",
    "question": "Asked",
    "held": "Held",
    "review": "In review",
    "drafts": "Waiting on your check",
    "ship": "Ready to ship",
    "orphan": "Left over",
    "closed": "Still running",
}


def _specimen(page: Page, name: str) -> Locator:
    return page.locator(f'[data-specimen="{name}"]')


def _lines(row: Locator) -> list[str]:
    """What a row says, part by part, as written rather than as styled: the kind
    line is set in capitals, and the words underneath are not. A name and the id
    riding after it are one part."""
    lines: list[str] = row.evaluate(
        """row => {
            const parts = [];
            const whole = e => [...e.children].every(c => c.classList.contains("id"));
            const walk = e => [...e.children].forEach(c =>
                whole(c) ? c.textContent && parts.push(c.textContent) : walk(c));
            walk(row);
            return parts;
        }"""
    )
    return lines


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_of_item_says_its_own_sentence_on_the_desk(gallery: Page, kind: str) -> None:
    item = _specimen(gallery, f"desk-{kind}").get_by_role("button")

    assert _lines(item) == DESK[kind]
    assert item.get_by_role("img").get_attribute("aria-label") == WORDS[kind]
    assert item.get_attribute("aria-pressed") == "false"


def test_the_eight_sentences_are_eight_different_sentences(gallery: Page) -> None:
    asks = [_lines(_specimen(gallery, f"desk-{kind}").get_by_role("button"))[2] for kind in KINDS]

    assert len(set(asks)) == len(KINDS)


def test_what_an_item_holds_up_drops_its_second_half_when_nothing_starts(gallery: Page) -> None:
    holds = {
        kind: _lines(_specimen(gallery, f"desk-{kind}").get_by_role("button"))[3:] for kind in KINDS
    }

    assert holds == {
        "environment": [],
        "question": ["Holds up 4 tickets · 2 start the moment it lands"],
        "held": ["Holds up 3 tickets · 1 starts the moment it lands"],
        "review": ["Holds up 1 ticket"],
        "drafts": [],
        "ship": [],
        "orphan": [],
        "closed": [],
    }


def test_nothing_in_needs_you_says_unblocks(gallery: Page) -> None:
    rows = gallery.locator('[data-specimen^="desk-"], [data-specimen^="need-"]')

    assert rows.count() == 2 * len(KINDS) + 2
    assert [text for text in rows.all_text_contents() if "nblock" in text] == []


@pytest.mark.parametrize("kind", KINDS)
def test_every_row_names_its_effort_so_the_list_reads_across_efforts(
    gallery: Page, kind: str
) -> None:
    effort = DESK[kind][0].split(" · ")[1]
    home = _specimen(gallery, f"need-{kind}").get_by_role("link")

    assert _lines(home)[0].endswith(f" · {effort}")


@pytest.mark.parametrize("kind", KINDS)
def test_home_says_the_same_and_how_many_tickets_it_holds_up_on_the_right(
    gallery: Page, kind: str
) -> None:
    row = _specimen(gallery, f"need-{kind}").get_by_role("link")
    lines = _lines(row)

    assert row.get_attribute("href") == f"#desk-{kind}"
    assert lines[:3] == DESK[kind][:3]
    held_up = DESK[kind][3:]
    assert lines[3:] == [clause.split(" · ")[0] for clause in held_up]
    if held_up:
        # The count sits in its own column, right of the words.
        name = row.get_by_text(DESK[kind][2], exact=True).bounding_box()
        count = row.get_by_text(lines[3], exact=True).bounding_box()
        assert name is not None and count is not None
        assert count["x"] >= name["x"] + name["width"]


def test_a_resolved_item_stays_in_place_dimmed_saying_what_happened(gallery: Page) -> None:
    waiting = _specimen(gallery, "desk-question").get_by_role("button")
    resolved = _specimen(gallery, "desk-resolved").get_by_role("button")

    assert _lines(resolved) == [*DESK["question"][:3], "Answered · the session resumed"]
    assert resolved.get_by_role("img").get_attribute("aria-label") == "Resolved"

    def colour(part: Locator) -> str:
        found: str = part.evaluate("e => getComputedStyle(e).color")
        return found

    def name(item: Locator) -> Locator:
        return item.locator(".id").locator("..")

    ask = waiting.get_by_text(DESK["question"][2], exact=True)
    # The name steps down from ink to the ask's softer ink.
    assert colour(name(resolved)) == colour(ask) != colour(name(waiting))


def test_the_item_open_on_the_desk_says_it_is_pressed(gallery: Page) -> None:
    item = _specimen(gallery, "desk-selected").get_by_role("button")

    assert item.get_attribute("aria-pressed") == "true"
    assert _lines(item) == DESK["review"]


def _row(name: str) -> bool:
    return name.startswith(("desk-", "need-"))


@pytest.mark.parametrize("theme", THEMES)
def test_every_row_answers_the_pointer_as_the_prototype_does(
    gallery: Page, reference: Page, theme: str
) -> None:
    choose(gallery, theme)
    set_theme(reference, theme)

    assert disagreements(gallery, reference, _row, hover=True) == []
