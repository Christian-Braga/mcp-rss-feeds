from rss_feeds.utils.logger import get_logger
from rss_feeds.core.services.rss_finder.manager import RssFinder
from rss_feeds.core.services.rss_parser.feed_parser import FeedParser


class RssApplication:
    """
    Main Orchestrator that coordinates the RSS discovery and parsing pipeline.
    Parameters
    ----------
    settings : dict
        Configuration dictionary containing 'RSS_API_ENDPOINT' and other settings.
    """

    def __init__(self, settings):
        self.logger = get_logger("P-ORC")
        self.settings = settings

        if not self.settings.get("RSS_API_ENDPOINT"):
            msg = "Missing RSS_API_ENDPOINT in settings. Cannot initialize pipeline."
            self.logger.critical(f"[P-ORC] {msg}")
            raise ValueError(msg)

        self.rss_finder = RssFinder(api_address=self.settings["RSS_API_ENDPOINT"])
        self.feed_parser = FeedParser()

    # Main Methods

    def discover_rss_links(self, source_url: str) -> list[str]:
        """
        Discover RSS feed URLs from a source website.
        Parameters
        ----------
        source_url : str
            The original website URL to inspect.
        Returns
        -------
        list of str
            A list of discovered RSS feed URLs.
        """
        self.logger.info(f"[P-ORC] Discovering RSS for: {source_url}")

        rss_data = self.rss_finder.get_rss_feed(source_url)
        if not rss_data:
            self.logger.error("[P-ORC] No RSS links found.")
            raise ValueError("No RSS feeds discovered")

        return rss_data

    def parse_feed(self, rss_link: str) -> dict:
        """
        Parse a single RSS feed URL.
        Parameters
        ----------
        rss_link : str
            The RSS feed URL to parse.
        Returns
        -------
        dict
            Parsed RSS feed data.
        """
        self.logger.info(f"[P-ORC] Parsing RSS: {rss_link}")

        parsed_feed = self.feed_parser.parse(rss_link)
        if not parsed_feed:
            self.logger.warning(f"[P-ORC] Empty feed returned for: {rss_link}")
            raise ValueError(f"Empty feed for {rss_link}")

        return parsed_feed
