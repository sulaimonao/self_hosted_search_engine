from urllib.parse import urlsplit
import scrapy
from w3lib.html import remove_tags
from crawler.items import PageItem

class PhonebookSpider(scrapy.Spider):
    """
    Spider that reads a list of domain names and fetches just the
    home page of each site.  This is useful for building a broad
    directory (or "phone book") of websites without crawling deeply
    into each one.  The list of domains should be stored in a text
    file with one domain per line.
    """
    name = "phonebook"

    custom_settings = {
        "DEPTH_LIMIT": 1,
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, domain_file, protocol="https", *args, **kwargs):
        """
        :param domain_file: path to a file containing domain names (one per line).
        :param protocol: scheme to use when constructing URLs (https or http).
        """
        super().__init__(*args, **kwargs)
        self.domain_file = domain_file
        self.protocol = protocol
        self.seen = set()

    def start_requests(self):
        # Read domain list
        try:
            with open(self.domain_file, "r", encoding="utf-8") as fh:
                for line in fh:
                    domain = line.strip()
                    if not domain or domain.startswith("#"):
                        continue
                    # Always lowercase the domain
                    domain = domain.lower()
                    # Avoid duplicates
                    if domain in self.seen:
                        continue
                    self.seen.add(domain)
                    url = f"{self.protocol}://{domain}/"
                    yield scrapy.Request(url, callback=self.parse_domain, dont_filter=True)
        except Exception as exc:
            self.logger.error("Error reading domain file %s: %s", self.domain_file, exc)

    def parse_domain(self, response):
        """
        Parse the home page of a domain.  Extract the title and body
        text.  We do not follow links here; the spider limits itself
        to a single page per domain.
        """
        url = response.url
        # Some domains may redirect from http to https or vice versa; normalize to base netloc
        parsed = urlsplit(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        title = response.xpath("//title/text()").get(default="").strip()
        body_html = response.xpath("//body").get(default="")
        text = remove_tags(body_html).strip()

        yield PageItem(url=base_url, title=title, html=body_html, text=text)