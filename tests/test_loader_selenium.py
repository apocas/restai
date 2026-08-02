"""Unit tests for restai/loaders/url.py — SeleniumWebReader with the
webdriver fully mocked: driver construction, scheme allowlist, page load,
text extraction, metadata, and error paths. No browser is ever started."""

from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import NoSuchElementException

from restai.loaders.url import SeleniumWebReader


class FakeDriver:
    def __init__(self, page_source="<html><body><p>Hello world</p></body></html>",
                 title="Page Title"):
        self.page_source = page_source
        self.title = title
        self.visited = []
        self.quit_called = False
        self.timeout = None
        self._elements = {}

    def get(self, url):
        if isinstance(self.page_source, Exception):
            raise self.page_source
        self.visited.append(url)

    def set_page_load_timeout(self, t):
        self.timeout = t

    def quit(self):
        self.quit_called = True

    def find_element(self, by, value):
        if value in self._elements:
            return self._elements[value]
        raise NoSuchElementException(value)


def _reader(**kw):
    return SeleniumWebReader(**kw)


def _patched(reader, driver):
    return patch.object(SeleniumWebReader, "_get_driver", return_value=driver)


# ─── init ───────────────────────────────────────────────────────────────

def test_init_defaults():
    r = _reader()
    assert r.browser == "chrome"
    assert r.continue_on_failure is True
    assert r.headless is True
    assert r.arguments == []
    assert r.page_load_timeout is None


# ─── load_data happy path ───────────────────────────────────────────────

def test_load_data_extracts_text_and_metadata():
    driver = FakeDriver()
    meta_el = MagicMock()
    meta_el.get_attribute.return_value = "A description"
    html_el = MagicMock()
    html_el.get_attribute.return_value = "en"
    driver._elements = {'//meta[@name="description"]': meta_el, "html": html_el}

    r = _reader()
    with _patched(r, driver):
        docs = r.load_data(["https://example.com/page"])

    assert len(docs) == 1
    assert "Hello world" in docs[0].text
    md = docs[0].metadata
    assert md["source"] == "https://example.com/page"
    assert md["title"] == "Page Title"
    assert md["description"] == "A description"
    assert md["language"] == "en"
    assert driver.visited == ["https://example.com/page"]
    assert driver.quit_called is True


def test_load_data_metadata_defaults_when_missing():
    driver = FakeDriver(title="")  # no title, no meta/html elements
    r = _reader()
    with _patched(r, driver):
        docs = r.load_data(["http://example.com"])
    md = docs[0].metadata
    assert md["title"] == "No title found."
    assert md["description"] == "No description found."
    assert md["language"] == "No language found."


def test_load_data_multiple_urls():
    driver = FakeDriver()
    r = _reader()
    with _patched(r, driver):
        docs = r.load_data(["https://a.example/", "https://b.example/"])
    assert len(docs) == 2
    assert driver.visited == ["https://a.example/", "https://b.example/"]


# ─── scheme allowlist ───────────────────────────────────────────────────

def test_non_http_url_skipped_when_continue_on_failure():
    driver = FakeDriver()
    r = _reader(continue_on_failure=True)
    with _patched(r, driver):
        docs = r.load_data(["file:///etc/passwd", "ftp://x", "https://ok.example/"])
    assert len(docs) == 1
    assert driver.visited == ["https://ok.example/"]


def test_non_http_url_raises_when_strict():
    driver = FakeDriver()
    r = _reader(continue_on_failure=False)
    with _patched(r, driver):
        with pytest.raises(ValueError, match="only http"):
            r.load_data(["file:///etc/passwd"])
    assert driver.visited == []


def test_scheme_check_case_insensitive():
    driver = FakeDriver()
    r = _reader()
    with _patched(r, driver):
        docs = r.load_data(["HTTPS://Example.com/"])
    assert len(docs) == 1


def test_none_url_refused_without_crash():
    driver = FakeDriver()
    r = _reader(continue_on_failure=True)
    with _patched(r, driver):
        docs = r.load_data([None])
    assert docs == []


# ─── error paths ────────────────────────────────────────────────────────

def test_fetch_error_continues_to_next_url():
    driver = FakeDriver()
    calls = []

    def get(url):
        calls.append(url)
        if url == "https://broken.example/":
            raise RuntimeError("timeout")
    driver.get = get
    r = _reader(continue_on_failure=True)
    with _patched(r, driver):
        docs = r.load_data(["https://broken.example/", "https://ok.example/"])
    assert len(docs) == 1
    assert calls == ["https://broken.example/", "https://ok.example/"]
    assert driver.quit_called is True


def test_fetch_error_raises_when_strict():
    driver = FakeDriver()
    driver.get = MagicMock(side_effect=RuntimeError("boom"))
    r = _reader(continue_on_failure=False)
    with _patched(r, driver):
        with pytest.raises(RuntimeError, match="boom"):
            r.load_data(["https://x.example/"])


# ─── page load timeout ──────────────────────────────────────────────────

def test_page_load_timeout_applied():
    driver = FakeDriver()
    r = _reader(page_load_timeout=12.5)
    with _patched(r, driver):
        r.load_data(["https://x.example/"])
    assert driver.timeout == 12.5


def test_page_load_timeout_unsupported_driver_tolerated():
    driver = FakeDriver()

    def bad_timeout(t):
        raise RuntimeError("old driver")
    driver.set_page_load_timeout = bad_timeout
    r = _reader(page_load_timeout=5)
    with _patched(r, driver):
        docs = r.load_data(["https://x.example/"])
    assert len(docs) == 1  # bound lost, call still succeeds


# ─── driver construction ────────────────────────────────────────────────

def test_get_driver_invalid_browser():
    r = _reader()
    r.browser = "safari"
    with pytest.raises(ValueError, match="Invalid browser"):
        r._get_driver()


def test_get_driver_chrome_headless_args():
    r = _reader(browser="chrome", headless=True, arguments=["--lang=en"],
                binary_location="/opt/chrome")
    with patch("selenium.webdriver.Chrome") as chrome:
        r._get_driver()
    chrome.assert_called_once()
    opts = chrome.call_args.kwargs["options"]
    assert "--headless" in opts.arguments
    assert "--no-sandbox" in opts.arguments
    assert "--lang=en" in opts.arguments
    assert opts.binary_location == "/opt/chrome"
    assert "service" not in chrome.call_args.kwargs


def test_get_driver_chrome_with_executable_path():
    r = _reader(browser="chrome", executable_path="/usr/bin/chromedriver")
    with patch("selenium.webdriver.Chrome") as chrome, \
         patch("selenium.webdriver.chrome.service.Service") as service:
        r._get_driver()
    service.assert_called_once_with(executable_path="/usr/bin/chromedriver")
    assert chrome.call_args.kwargs["service"] is service.return_value


def test_get_driver_chrome_snap_chromium_autodetect():
    r = _reader(browser="chrome")
    snap_driver = "/snap/chromium/current/usr/lib/chromium-browser/chromedriver"

    def which(name):
        return "/snap/bin/chromium-browser" if name == "chromium-browser" else None

    with patch("selenium.webdriver.Chrome") as chrome, \
         patch("selenium.webdriver.chrome.service.Service") as service, \
         patch("shutil.which", side_effect=which), \
         patch("os.path.exists", return_value=True):
        r._get_driver()
    opts = chrome.call_args.kwargs["options"]
    assert opts.binary_location == "/snap/bin/chromium-browser"
    service.assert_called_once_with(executable_path=snap_driver)


def test_get_driver_firefox():
    r = _reader(browser="firefox", headless=True, binary_location="/opt/ff")
    with patch("selenium.webdriver.Firefox") as firefox:
        r._get_driver()
    firefox.assert_called_once()
    opts = firefox.call_args.kwargs["options"]
    assert "--headless" in opts.arguments
    assert opts.binary_location == "/opt/ff"


def test_get_driver_firefox_with_executable_path():
    r = _reader(browser="firefox", executable_path="/usr/bin/geckodriver")
    with patch("selenium.webdriver.Firefox") as firefox, \
         patch("selenium.webdriver.firefox.service.Service") as service:
        r._get_driver()
    service.assert_called_once_with(executable_path="/usr/bin/geckodriver")
    assert firefox.call_args.kwargs["service"] is service.return_value
