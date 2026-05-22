"""Beautiful Soup Web scraper."""

import logging
from typing import TYPE_CHECKING, List, Literal, Optional, Union
from unstructured.partition.html import partition_html

if TYPE_CHECKING:
    from selenium.webdriver import Chrome, Firefox

from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document

logger = logging.getLogger(__name__)


class SeleniumWebReader(BaseReader):
    """Selenium-driven web page reader."""

    def __init__(
        self,
            continue_on_failure: bool = True,
            browser: Literal["chrome", "firefox"] = "chrome",
            binary_location: Optional[str] = None,
            executable_path: Optional[str] = None,
            headless: bool = True,
            arguments: object = None,
            page_load_timeout: Optional[float] = None,
    ) -> None:

        """Load URLs using Selenium and unstructured.

        page_load_timeout: when set, Selenium's `set_page_load_timeout` is
        applied so a slow/hung page can't pin the agent forever. Default is
        no timeout; callers handling untrusted URLs should pass an explicit value.
        """
        if arguments is None:
            arguments = []
        try:
            import selenium  # noqa:F401
        except ImportError:
            raise ImportError(
                "selenium package not found, please install it with "
                "`pip install selenium`"
            )

        try:
            import unstructured  # noqa:F401
        except ImportError:
            raise ImportError(
                "unstructured package not found, please install it with "
                "`pip install unstructured`"
            )

        self.continue_on_failure = continue_on_failure
        self.browser = browser
        self.binary_location = binary_location
        self.executable_path = executable_path
        self.headless = headless
        self.arguments = arguments
        self.page_load_timeout = page_load_timeout

    def _get_driver(self) -> Union["Chrome", "Firefox"]:
        """Create and return a WebDriver instance."""
        if self.browser.lower() == "chrome":
            from selenium.webdriver import Chrome
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.chrome.service import Service

            chrome_options = ChromeOptions()

            for arg in self.arguments:
                chrome_options.add_argument(arg)

            if self.headless:
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")

            binary = self.binary_location
            exec_path = self.executable_path

            if binary is None and exec_path is None:
                import shutil
                import os
                if shutil.which("chromium-browser") and not shutil.which("google-chrome"):
                    binary = shutil.which("chromium-browser")
                    snap_driver = "/snap/chromium/current/usr/lib/chromium-browser/chromedriver"
                    if os.path.exists(snap_driver):
                        exec_path = snap_driver

            if binary is not None:
                chrome_options.binary_location = binary
            if exec_path is None:
                return Chrome(options=chrome_options)
            return Chrome(
                options=chrome_options,
                service=Service(executable_path=exec_path),
            )
        elif self.browser.lower() == "firefox":
            from selenium.webdriver import Firefox
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
            from selenium.webdriver.firefox.service import Service

            firefox_options = FirefoxOptions()

            for arg in self.arguments:
                firefox_options.add_argument(arg)

            if self.headless:
                firefox_options.add_argument("--headless")
            if self.binary_location is not None:
                firefox_options.binary_location = self.binary_location
            if self.executable_path is None:
                return Firefox(options=firefox_options)
            return Firefox(
                options=firefox_options,
                service=Service(executable_path=self.executable_path),
            )
        else:
            raise ValueError("Invalid browser specified. Use 'chrome' or 'firefox'.")

    @staticmethod
    def _build_metadata(url: str, driver: Union["Chrome", "Firefox"]) -> dict:
        from selenium.common.exceptions import NoSuchElementException
        from selenium.webdriver.common.by import By

        metadata = {
            "source": url,
            "title": "No title found.",
            "description": "No description found.",
            "language": "No language found.",
        }
        if title := driver.title:
            metadata["title"] = title
        try:
            if description := driver.find_element(
                By.XPATH, '//meta[@name="description"]'
            ):
                metadata["description"] = (
                    description.get_attribute("content") or "No description found."
                )
        except NoSuchElementException:
            pass
        try:
            if html_tag := driver.find_element(By.TAG_NAME, "html"):
                metadata["language"] = (
                    html_tag.get_attribute("lang") or "No language found."
                )
        except NoSuchElementException:
            pass
        return metadata

    # Scheme allowlist applied at the loader (not router) so headless Chrome
    # can't render `file:///etc/passwd` into the vector store via any caller.
    _ALLOWED_SCHEMES = ("http://", "https://")

    def load_data(
        self,
        urls: list[str],
    ) -> List[Document]:
        """Load URLs with Selenium and return Document instances."""

        docs: List[Document] = list()
        driver = self._get_driver()
        if self.page_load_timeout is not None:
            try:
                driver.set_page_load_timeout(self.page_load_timeout)
            except Exception:
                # Older drivers don't support it; lose the bound rather than fail the call.
                pass

        for url in urls:
            try:
                lo = (url or "").strip().lower()
            except Exception:
                lo = ""
            if not any(lo.startswith(s) for s in self._ALLOWED_SCHEMES):
                logger.warning(
                    "SeleniumWebReader refused non-http(s) URL: %r", url
                )
                if self.continue_on_failure:
                    continue
                raise ValueError(
                    f"only http(s) URLs are allowed (got: {url!r})"
                )

            try:
                driver.get(url)
                page_content = driver.page_source
                elements = partition_html(text=page_content)
                text = "\n\n".join([str(el) for el in elements])
                metadata = self._build_metadata(url, driver)
                docs.append(Document(text=text, metadata=metadata))
            except Exception as e:
                if self.continue_on_failure:
                    logger.error(f"Error fetching or processing {url}, exception: {e}")
                else:
                    raise e

        driver.quit()
        return docs