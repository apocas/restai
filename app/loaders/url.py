"""Beautiful Soup Web scraper."""

import logging
from typing import TYPE_CHECKING, List, Literal, Optional, Union

if TYPE_CHECKING:
    from selenium.webdriver import Chrome, Firefox

from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document

logger = logging.getLogger(__name__)


class SeleniumWebReader(BaseReader):
    """BeautifulSoup web page reader.

    Reads pages from the web.
    Requires the `bs4` and `urllib` packages.

    Args:
        website_extractor (Optional[Dict[str, Callable]]): A mapping of website
            hostname (e.g. google.com) to a function that specifies how to
            extract text from the BeautifulSoup obj. See DEFAULT_WEBSITE_EXTRACTOR.
    """

    def __init__(
        self,
        continue_on_failure: bool = True,
        browser: Literal["chrome", "firefox"] = "chrome",
        binary_location: Optional[str] = None,
        executable_path: Optional[str] = None,
        headless: bool = True,
        arguments: List[str] = [],
    ):
        
        """Load a list of URLs using Selenium and unstructured."""
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

    def _get_driver(self) -> Union["Chrome", "Firefox"]:
        """Create and return a WebDriver instance based on the specified browser.

        Raises:
            ValueError: If an invalid browser is specified.

        Returns:
            Union[Chrome, Firefox]: A WebDriver instance for the specified browser.
        """
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
            if self.binary_location is not None:
                chrome_options.binary_location = self.binary_location
            if self.executable_path is None:
                return Chrome(options=chrome_options)
            return Chrome(
                options=chrome_options,
                service=Service(executable_path=self.executable_path),
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

    def _build_metadata(self, url: str, driver: Union["Chrome", "Firefox"]) -> dict:
        from selenium.common.exceptions import NoSuchElementException
        from selenium.webdriver.common.by import By

        """Build metadata based on the contents of the webpage"""
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

    def load_data(
        self,
        urls: List[str],
    ) -> List[Document]:
        """Load the specified URLs using Selenium and create Document instances.

        Returns:
            List[Document]: A list of Document instances with loaded content.
        """
        from unstructured.partition.html import partition_html

        docs: List[Document] = list()
        driver = self._get_driver()

        for url in urls:
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