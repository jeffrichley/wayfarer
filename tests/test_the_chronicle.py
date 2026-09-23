"""The chronicle's lines, as the gallery shows them (#51).

The snapshot check in `test_the_gallery.py` holds how each line looks. These hold
what it says: the sentence each kind of line is written from, the names in it,
and how its lines fall into days, earlier ones loading a day at a time.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Locator, Page

pytestmark = [pytest.mark.git, pytest.mark.browser]

MINUS = "\N{MINUS SIGN}"

# The gallery's sample tickets and effort, each named as a line reads it: its
# name, then its id.
ANALYSIS = "Extract the audio analysis pass from the render worker #125"
LOUDNESS = f"Flag loudness outside {MINUS}23 to {MINUS}18 dB RMS #126"
PEAKS = f"Flag peaks above {MINUS}3 dB #127"
NOISE_FLOOR = f"Flag a noise floor above {MINUS}60 dB #128"
LONG_CHAPTERS = "Flag chapters longer than 120 minutes #129"
CREDITS = "Require opening and closing credits #130"
ROOM_TONE = "Check room tone at the head and tail of each chapter #131"
MY_BOOKS = "Show compliance status on My Books #132"
EFFORT = "Pre-delivery compliance checks #124"

# Every kind of line with the sentence its template writes (#22): tickets moving,
# never stages, and who acted read from the kind of event.
SENTENCES = {
    "line-taken": f"{NOISE_FLOOR} was taken.",
    "line-taken-you": f"You took {CREDITS}.",
    "line-taken-someone": f"mira took {CREDITS}.",
    "line-asked": f"{CREDITS} stopped to ask: “Should DOCX books without credits fail or warn?”",
    "line-answered": f"You answered {CREDITS}, and its session resumed.",
    "line-answered-someone": f"mira answered {CREDITS}, and its session resumed.",
    "line-held": f"{LONG_CHAPTERS} was held. Its tests were still red when the session ended.",
    "line-retried": f"You retried {LONG_CHAPTERS}, continuing where its session stopped.",
    "line-retried-over": f"You retried {LONG_CHAPTERS}, starting over from the effort branch.",
    "line-landed": f"{PEAKS} landed.",
    "line-landed-freed": f"{ANALYSIS} landed. {LOUDNESS} and {PEAKS} reached the frontier.",
    "line-landed-folded": f"{LOUDNESS} landed. {NOISE_FLOOR}, {LONG_CHAPTERS}, and {CREDITS} "
    f"reached the frontier, and agents took {NOISE_FLOOR} and {LONG_CHAPTERS}.",
    "line-landed-all": f"{PEAKS} landed. {MY_BOOKS} reached the frontier, and an agent took it.",
    "line-landed-by-hand": f"You landed {PEAKS} by hand, not re-tested.",
    "line-landed-by-someone": f"mira landed {PEAKS} by hand, not re-tested.",
    "line-closed": f"You closed {ROOM_TONE} without landing it.",
    "line-closed-someone": f"mira closed {ROOM_TONE} without landing it.",
    "line-armed": f"You armed the cascade on {EFFORT}. "
    f"Agents took {NOISE_FLOOR} and {LONG_CHAPTERS}.",
    "line-armed-idle": f"You armed the cascade on {EFFORT}.",
    "line-published": f"{EFFORT} was sliced into nine tickets. "
    f"{ANALYSIS} reached the frontier, and an agent took it.",
    "line-ready": f"{EFFORT} became ready to ship: its last ticket landed.",
    "line-shipped": f"{EFFORT} shipped.",
}


def _specimen(page: Page, name: str) -> Locator:
    return page.locator(f'[data-specimen="{name}"]')


def _sentence(line: Locator) -> str:
    """The line's sentence as it reads: an id rides after its name, set apart by
    its margin rather than a space."""
    text: str = line.locator("p").evaluate(
        """p => {
            const read = p.cloneNode(true);
            read.querySelectorAll(".id").forEach(id => id.before(" "));
            return read.textContent;
        }"""
    )
    return " ".join(text.split())


def test_every_kind_of_line_is_written_from_its_template(gallery: Page) -> None:
    names = gallery.locator('[data-specimen^="line-"]').evaluate_all(
        "lines => lines.map(line => line.dataset.specimen)"
    )

    assert sorted(names) == sorted(SENTENCES)
    assert {name: _sentence(_specimen(gallery, name)) for name in SENTENCES} == SENTENCES


def test_a_line_carries_its_time_and_its_efforts_name(gallery: Page) -> None:
    line = _specimen(gallery, "line-landed").get_by_role("listitem")

    assert line.locator("time").inner_text() == "07:48"
    assert line.locator("time").get_attribute("datetime") == "2026-09-15T07:48"
    assert line.locator("p + *").inner_text() == "Pre-delivery compliance checks"
    # The effort, never the skill that acted (#22).
    assert "/" not in line.inner_text()


def test_things_are_named_by_name_as_links_with_their_ids_after(gallery: Page) -> None:
    sentence = _specimen(gallery, "line-landed-folded").locator("p")
    links = sentence.get_by_role("link")

    named = [
        f"{link.inner_text()} {link.evaluate('a => a.nextElementSibling.textContent')}"
        for link in (links.nth(i) for i in range(links.count()))
    ]
    assert named == [LOUDNESS, NOISE_FLOOR, LONG_CHAPTERS, CREDITS, NOISE_FLOOR, LONG_CHAPTERS]
    # No link's text is an id.
    assert not any(re.fullmatch(r"#\d+", text) for text in links.all_inner_texts())

    effort = _specimen(gallery, "line-shipped").locator("p").get_by_role("link")
    assert effort.inner_text() == "Pre-delivery compliance checks"
    assert effort.evaluate("a => a.nextElementSibling.textContent") == "#124"


def test_a_folded_line_is_one_event_with_what_it_caused(gallery: Page) -> None:
    line = _specimen(gallery, "line-landed-folded")

    assert line.get_by_role("listitem").count() == 1
    assert line.locator("time").count() == 1
    sentences = re.findall(r"[^.]+\.", _sentence(line))
    assert len(sentences) == 2
    assert sentences[0].endswith("landed.")
    assert "reached the frontier, and agents took" in sentences[1]


def test_lines_group_under_their_days_newest_first(gallery: Page) -> None:
    chronicle = _specimen(gallery, "chronicle")
    days = chronicle.locator("[data-day]")

    assert days.locator(".kicker").all_text_contents() == [
        "Today",
        "Yesterday · Monday 14 September",
    ]
    assert days.nth(0).locator("time").all_inner_texts() == ["09:41", "09:18", "07:48"]
    assert days.nth(1).locator("time").all_inner_texts() == ["22:14", "16:40", "10:20"]


def test_earlier_days_load_one_day_at_a_time(gallery: Page) -> None:
    chronicle = _specimen(gallery, "chronicle")
    earlier = chronicle.get_by_role("button", name="Earlier")

    earlier.click()
    assert chronicle.locator("[data-day] .kicker").all_text_contents() == [
        "Today",
        "Yesterday · Monday 14 September",
        "Sunday 13 September",
    ]

    earlier.click()
    assert chronicle.locator("[data-day] .kicker").all_text_contents()[-1] == "Friday 11 September"
    # There is nothing earlier than the first line, so nothing more to load.
    assert earlier.count() == 0
