"""The question card: what a person answers when a session has asked something (#52).

The snapshot check in `test_the_gallery.py` holds how the card looks at rest.
These hold what a picture at rest cannot: that sending waits for an answer, and
that a sent answer locks the card and says where it went.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Locator, Page, expect

pytestmark = [pytest.mark.git, pytest.mark.browser]

REFUSED = "Choose an option, or write an answer first."
REFUSED_EACH = "Choose an option for each question, or write an answer first."
POSTED = "Posted to #130. The session resumes."


def _card(page: Page, name: str) -> Locator:
    return page.locator(f'[data-specimen="{name}"]')


def _send(card: Locator) -> Locator:
    return card.get_by_role("button", name="Send answer and resume")


def _hint(card: Locator) -> Locator:
    return card.get_by_role("status")


def _expect_checked(where: Locator, checked: list[str]) -> None:
    radios = where.get_by_role("radio")
    expect(radios).to_have_count(len(checked))
    for radio, state in zip(radios.all(), checked, strict=True):
        expect(radio).to_have_attribute("aria-checked", state)


def test_each_option_carries_the_sentence_on_what_picking_it_means(gallery: Page) -> None:
    options = _card(gallery, "question-1").get_by_role("radio")

    assert [option.inner_text().split("\n") for option in options.all()] == [
        [
            "Fail, same as EPUB",
            "Stricter. Some DOCX books with real credits may fail until the author marks them.",
        ],
        [
            "Warn, and ask the author to confirm",
            "Export stays unlocked for this check once they confirm credits are there.",
        ],
    ]
    assert [option.get_attribute("aria-checked") for option in options.all()] == ["false"] * 2


def test_a_card_carries_up_to_four_questions_each_with_its_own_options(gallery: Page) -> None:
    groups = _card(gallery, "question-4").get_by_role("radiogroup")

    assert groups.count() == 4
    assert [group.get_by_role("radio").count() for group in groups.all()] == [2, 3, 2, 4]
    # Each question's options are named by the question they answer.
    assert all(group.get_attribute("aria-label") for group in groups.all())


def test_picking_an_option_picks_only_that_one_in_its_question(gallery: Page) -> None:
    card = _card(gallery, "question-4")
    first, second = card.get_by_role("radiogroup").all()[:2]

    first.get_by_role("radio").nth(1).click()
    second.get_by_role("radio").nth(0).click()
    first.get_by_role("radio").nth(0).click()

    _expect_checked(first, ["true", "false"])
    _expect_checked(second, ["true", "false", "false"])


def test_sending_with_no_choice_and_no_note_is_refused(gallery: Page) -> None:
    card = _card(gallery, "question-1")
    expect(_hint(card)).to_have_text("Pick an option or write your own answer.")

    _send(card).click()

    expect(_hint(card)).to_have_text(REFUSED)
    expect(_send(card)).not_to_have_attribute("aria-disabled", "true")
    expect(card.get_by_role("textbox")).to_be_editable()


def test_a_note_of_only_spaces_is_no_answer(gallery: Page) -> None:
    card = _card(gallery, "question-1")

    card.get_by_role("textbox").fill("   ")
    _send(card).click()

    expect(_hint(card)).to_have_text(REFUSED)


def test_a_choice_alone_is_an_answer(gallery: Page) -> None:
    card = _card(gallery, "question-1")

    card.get_by_role("radio", name="Warn, and ask the author to confirm").click()
    _send(card).click()

    expect(_hint(card)).to_have_text(POSTED)


def test_a_note_alone_is_an_answer(gallery: Page) -> None:
    card = _card(gallery, "question-1")

    card.get_by_role("textbox", name="Anything the agent should know").fill("Warn for now.")
    _send(card).click()

    expect(_hint(card)).to_have_text(POSTED)


def test_several_questions_want_a_choice_each_unless_there_is_a_note(gallery: Page) -> None:
    card = _card(gallery, "question-4")
    groups = card.get_by_role("radiogroup").all()

    for group in groups[:-1]:
        group.get_by_role("radio").first.click()
    _send(card).click()
    expect(_hint(card)).to_have_text(REFUSED_EACH)

    groups[-1].get_by_role("radio").first.click()
    _send(card).click()
    expect(_hint(card)).to_have_text("Posted to #131. The session resumes.")


def test_after_sending_the_controls_lock_and_the_card_says_where_the_answer_went(
    gallery: Page,
) -> None:
    card = _card(gallery, "question-1")
    card.get_by_role("radio", name="Fail, same as EPUB").click()
    card.get_by_role("textbox").fill("Authors can mark credits later.")

    _send(card).click()

    expect(_hint(card)).to_have_text(POSTED)
    sent = card.get_by_role("button", name="Answer sent")
    expect(sent).to_have_attribute("aria-disabled", "true")
    expect(sent).to_have_attribute("data-piece", "send-answer-130")
    expect(card.get_by_role("textbox")).not_to_be_editable()
    radios = card.get_by_role("radio").all()
    for radio in radios:
        expect(radio).to_have_attribute("aria-disabled", "true")

    # A locked card keeps the answer it sent, whatever is clicked or typed after.
    radios[1].click(force=True)
    card.get_by_role("textbox").focus()
    gallery.keyboard.type(" More.")
    sent.click(force=True)
    _expect_checked(card, ["true", "false"])
    expect(card.get_by_role("textbox")).to_have_value("Authors can mark credits later.")
    expect(_hint(card)).to_have_text(POSTED)


def test_a_locked_option_is_not_offered_to_the_keyboard(gallery: Page) -> None:
    card = _card(gallery, "question-1")
    card.get_by_role("textbox").fill("Warn for now.")
    _send(card).click()

    for radio in card.get_by_role("radio").all():
        expect(radio).to_have_attribute("tabindex", "-1")
