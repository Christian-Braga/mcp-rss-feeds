import feedparser
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from rss_feeds.utils.logger import get_logger

class FeedParser():
    """
    A RSS feed parser using feedparser.

    This class takes an RSS feed URL, fetches its content, and returns 
    a structured dictionary containing feed metadata and entries.

    Attributes
    ----------
    logger : logging.Logger
        Logger instance for tracking parsing operations and errors.
    """

    def __init__(self):
        self.logger = get_logger("FPRS")
    
    # Main Method

    def parse(self, rss_link: str):
        """
        Parse an RSS feed and extract its entries into a structured format.

        Validates the provided RSS link, fetches the feed using feedparser,
        and extracts relevant fields from each entry including title, link,
        publication date, author, thumbnail, and summary.

        Parameters
        ----------
        rss_link : str
            The URL of the RSS feed to parse.
        """
        self.logger.info(f"[FPRS] Parsin RSS feed: {rss_link}")
        try:
            is_valid_url = self._validate_rss_link(rss_link)
            if not is_valid_url:
                raise ValueError(f"Invalid RSS link: {rss_link}")
        except ValueError:
            self.logger.exception(
                "[FPRS] Invalid RSS link, impossible to retrieve its feed."
            )
            raise
        
        feed = feedparser.parse(rss_link)
        
        if not feed.entries:
            self.logger.error(f"[FPRS] Feed at {rss_link} seems to be empty or not a feed.")
            raise ValueError(f"Impossible to retrieve the feed for {rss_link}")
        
        # Data Extraction
        try:
            feed_content = {
                "rss_link": rss_link,
                "number_of_resources": len(feed.entries),
                "resources": [
                    {
                        "id": entry.get("id", "N/A"),
                        "title": entry.get("title", "No Title"),
                        "link": entry.get("link", "#"),
                        "published": self._normalize_date(entry.get("published")),
                        "author": entry.get("author", "N/A"),
                        "media_thumbnail": self._extract_thumbnail(entry),
                        "summary": self._clean_summary(entry.get("summary", ""))
                    } for entry in feed.entries
                ],
            }
            return feed_content

        except Exception as exc:
            self.logger.error(f"[FPRS] Error structuring feed data: {exc}")
            raise ValueError("Data extraction failed after parsing.")
        
    
    def _extract_thumbnail(self, entry) -> str:
        """Helper to safely extract thumbnail from entry."""
        if hasattr(entry, "media_thumbnail") and len(entry.media_thumbnail) > 0:
            return entry.media_thumbnail[0].get("url", "N/A")
        return "N/A"


    def _clean_summary(self, html_text: str) -> str:
        """Helper to remove HTML tags from summary if needed."""
        clean = re.compile('<.*?>')
        return re.sub(clean, '', html_text).strip()
    

    def _validate_rss_link(self, rss_link):
        """Helper to validate the Rss link as an available url."""
        web_url_pattern = r"^https?:\/\/(?:[\w-]+\.)+[\w-]{2,}(?:\/[^\s]*)?$"
        return re.match(web_url_pattern, rss_link)
    

    def _normalize_date(self, date_string: str) -> str | None:
        """
        Normalize any date format to ISO 8601 UTC.
        Parameters
        ----------
        date_string : str
            Date in various formats (e.g., RFC 2822, ISO 8601, etc.).
        """
        if not date_string or date_string == "N/A":
            return None
        
        try:
            dt = parsedate_to_datetime(date_string.strip())
            return dt.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass
        
        try:
            dt = datetime.fromisoformat(date_string.strip().replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (ValueError, AttributeError):
            pass
        
        self.logger.warning(f"[FPRS] Could not parse date: '{date_string}'")
        return None


 


