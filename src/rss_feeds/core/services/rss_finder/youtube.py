from rss_feeds.core.services.rss_finder.base import RssCrawler
from rss_feeds.utils.logger import get_logger
from rss_feeds.core.services.rss_finder.favicons.favicons_b64 import YOUTUBE_FAVICON_B64
import requests
import re
from datetime import datetime, timezone

class RssYoutube(RssCrawler):
    """
    RSS crawler specialized for YouTube channels.
    
    This class extracts channel information from YouTube URLs and generates
    the corresponding RSS feed URL for monitoring channel updates.
    
    Attributes:
        YOUTUBE_RSS_URL_ENDPOINT (str): Base URL for YouTube RSS feeds.
        logger: Logger instance for tracking operations.
    """

    YOUTUBE_RSS_URL_ENDPOINT = "https://www.youtube.com/feeds/videos.xml?channel_id="

    def __init__(self):
        self.logger = get_logger("RSSF")

    # Main Method

    def find(self, web_url : str):
        """
        Extract RSS feed information from a YouTube channel URL.
        
        Args:
            web_url (str): The YouTube channel URL (e.g., https://www.youtube.com/@channelname).
        
        Returns:
            dict: A dictionary containing RSS feed metadata.
        """
        try:
            channel_id, channel_name = self._get_channel_info(web_url)
            if not channel_id:
                self.logger.error(f"[RSSF] Could not resolve Channel ID for {web_url}")
                return []
            
            return [{
                "description": "",
                "favicon" : YOUTUBE_FAVICON_B64,
                "last_seen" : datetime.now(timezone.utc).isoformat(),
                "last_updated" : datetime.now(timezone.utc).isoformat(),
                "site_name" : channel_name if channel_name else "",
                "site_url" : web_url,
                "title" : "",
                "url" : f"{self.YOUTUBE_RSS_URL_ENDPOINT}{channel_id}",            
            }]
        except Exception as exc:
            self.logger.error(f"[RSSF] Error in YouTube finder for {web_url}: {exc}")
            return []

    # Support Functions

    def _get_channel_info(self, web_url):
        """
        Extract channel ID and channel name from a YouTube channel URL.
        
        This method performs two operations:
        1. Extracts the channel handle/name from the URL using regex (e.g., @channelname).
        2. Fetches the channel page HTML and extracts the internal channel ID (externalId).
        
        Args:
            web_url (str): The YouTube channel URL to process.
        
        Returns:
            tuple: A tuple containing:
                - channel_id (str or None): The YouTube channel ID (externalId).
                - channel_name (str or None): The channel handle extracted from the URL.
        """
        match_name = re.search(r'@([^/?]+)', web_url)
        channel_name = match_name.group(1) if match_name else "Unknown Channel"

        try:
            self.logger.info("[RSSF] Searching for channel ID")
            channel_id = requests.get(web_url, timeout=15)
            channel_id.raise_for_status()

            try:
                response = channel_id.text
            except ValueError:
                raise RuntimeError("[RSSF Invalid output format for channel ID")
            
            match_id = re.search(r'"externalId"\s*:\s*"([^"]+)"', response)
            channel_id = match_id.group(1) if match_id else None

            return channel_id, channel_name

        except requests.exceptions.RequestException as exc:
            self.logger.error(f"[RSSF] Network error fetching {web_url}: {exc}")
            return None, channel_name

            
        


    

