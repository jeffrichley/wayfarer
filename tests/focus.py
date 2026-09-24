"""The one browser check every screen reuses: the page never steals focus (#59).

Principle 12 as a test, as ADR-0004 settles it.

`keeps_focus` clicks something real, lets live updates land while it holds focus,
confirms focus never left it, and presses a key there, as a person clicks and then
types. The updates are counted as the page's own stream delivers them, so the check
waits on the load rather than on a fixed time; a page is made to count them by
opening it through `counting` before it is loaded.
"""

from __future__ import annotations

from playwright.sync_api import Locator, Page

# Enough updates that a screen which moved focus on any one of them would be caught
# mid-check: with recorded sessions streaming, well under a second's worth.
UPDATES = 50

_COUNTING = """
window.__wayfarerUpdates = 0;
const Stream = window.EventSource;
window.EventSource = class extends Stream {
  constructor(...args) {
    super(...args);
    this.addEventListener("message", () => { window.__wayfarerUpdates += 1; });
  }
};
"""


def counting(page: Page) -> Page:
    """`page`, counting each live update its stream delivers from the next load on."""
    page.add_init_script(_COUNTING)
    return page


def keeps_focus(page: Page, target: Locator, key: str, updates: int = UPDATES) -> None:
    """Click `target`, let `updates` live updates land, find focus still on it, press `key`.

    The click and the key are dispatched as the browser's own input, never by calling
    a handler, so the screen sees what it sees from a person.
    """
    assert page.evaluate("typeof window.__wayfarerUpdates") == "number", (
        "the page was not opened through `counting`"
    )
    # Where focus went the first time it left, should it leave and be put back: armed
    # as the click gives it focus, so no update can land before the watch does.
    target.evaluate(
        f"el => {{ const describe = {_DESCRIBE}; window.__wayfarerLeft = null;"
        " el.addEventListener('focus', () => el.addEventListener('blur',"
        " e => { window.__wayfarerLeft ??= describe(e.relatedTarget); }), {once: true}); }"
    )
    target.click()
    delivered: int = page.evaluate("window.__wayfarerUpdates")
    page.wait_for_function(f"window.__wayfarerUpdates >= {delivered + updates}")
    left = page.evaluate("window.__wayfarerLeft")
    assert left is None, f"a live update moved focus to {left}"
    assert _holds_focus(target), f"the click left focus on {_focused(page)}"
    target.evaluate(
        "el => { window.__wayfarerKeys = [];"
        " el.addEventListener('keydown', e => window.__wayfarerKeys.push(e.key), {once: true}); }"
    )
    page.keyboard.press(key)
    assert page.evaluate("window.__wayfarerKeys") == [key], f"{key} reached {_focused(page)}"


def _holds_focus(target: Locator) -> bool:
    held: bool = target.evaluate("el => el === document.activeElement")
    return held


def _focused(page: Page) -> str:
    """Whatever has focus."""
    described: str = page.evaluate(f"({_DESCRIBE})(document.activeElement)")
    return described


# An element as a person reading the failure would find it: its piece, or its tag and text.
_DESCRIBE = """el => {
  if (el === null || el === document.body) return "the page";
  const text = el.textContent.trim().slice(0, 40);
  return el.dataset.piece ?? `${el.tagName.toLowerCase()} ${text}`;
}"""
