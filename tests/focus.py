"""The one browser check every screen reuses: the page never steals focus (#59).

`keeps_focus` clicks something real, lets live updates land while it holds focus,
confirms focus is still on it, and presses a key there, as a person clicks and then
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
    delivered = page.evaluate("window.__wayfarerUpdates")
    assert isinstance(delivered, int), "the page was not opened through `counting`"
    target.click()
    page.wait_for_function(f"window.__wayfarerUpdates >= {delivered + updates}")
    assert _holds_focus(target), f"after a click and live updates, focus is on {_focused(page)}"
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
    """Whatever has focus, as a person reading the failure would find it."""
    described: str = page.evaluate(
        "(() => { const el = document.activeElement;"
        " if (el === null || el === document.body) return 'the page';"
        " const text = el.textContent.trim().slice(0, 40);"
        " return el.dataset.piece ?? `${el.tagName.toLowerCase()} ${text}`; })()"
    )
    return described
