import base64
from datetime import datetime, timezone

import httpx
import requests
from feedsearch import search

from rss_feeds.utils.logger import get_logger

from rss_feeds.core.services.rss_finder.base import RssCrawler


class RssWebPage(RssCrawler):
    """
    RSS link finder for standard web pages.
    
    This class provides functionality to discover RSS feeds from web URLs using
    a primary API service with a fallback mechanism for cases where the API fails.
    """

    FIELDS_TO_REMOVE = [
        "bozo",
        "content_length",
        "content_type",
        "hubs",
        "self_url",
        "is_podcast",
        "is_push",
        "item_count",
        "score",
        "velocity",
        "version"
        ]

    def __init__(self, api_address: str):
        self.api_url = api_address
        self.logger = get_logger("RSSF")
    
    # Main Method

    def find(self, web_url: str):
        """
        Find RSS feeds for a given web URL.
        
        Attempts to retrieve RSS feed information using the configured API service.
        If the API call fails for any reason (timeout, HTTP error, network issues),
        falls back to an alternative RSS discovery method.
        
        Args:
            web_url: The URL of the website to search for RSS feeds.
        """
        parameters = { 'url' : web_url}
        self.logger.info(f"[RSSF] Retrieving RSS feed from: {self.api_url}")

        try:
            rss_links = requests.get(self.api_url, params=parameters, timeout=40)
            rss_links.raise_for_status()

            try:
                data = rss_links.json()
            except requests.exceptions.JSONDecodeError:
                self.logger.error("[RSSF] Invalid Json Response from API for %s", web_url)
                return self._fallback_rss_finder(web_url)
            
            if not data:
                return self._fallback_rss_finder(web_url)
            
            favicon = self._get_favicon(web_url)
            formatted_output = self._format_api_output(result= data)
            for result in formatted_output:
                result['favicon'] = favicon

            return formatted_output
        
        except requests.exceptions.Timeout:
            self.logger.error("[RSSF] Timeout while calling RSS API for %s", web_url)
        except requests.exceptions.HTTPError as err:
            self.logger.error(
                "[RSSF] HTTP error %s while retrieving RSS for %s",
                err.response.status_code,
                web_url
            )
        except requests.exceptions.RequestException:
            self.logger.error("[RSSF] Network error while retrieving RSS for %s", web_url)
        except Exception:
            self.logger.error("[RSSF] Unexpected error while retrieving RSS for %s", web_url)
        
        return self._fallback_rss_finder(web_url)
            

    # Support Functions

    def _fallback_rss_finder(self, web_url: str):
        """
        Fallback RSS feed discovery method.
        
        Uses the feedsearch library to discover RSS feeds when the primary
        API service is unavailable or fails. Converts feedsearch results
        to the standardized output format.
        
        Args:
            web_url: The URL of the website to search for RSS feeds.
        """
        try:
            feeds = search(web_url)
            if not feeds:
                self.logger.error("[RSSF] No RSS Feed found with Fallback Method for %s", web_url)
                return []
            
            output = [vars(f) for f in feeds]
            return self._format_fallback_output(result= output, web_url= web_url)

        except Exception as exc:
            self.logger.error(
                "[RSSF] Fallback RSS finder failed for %s: %s", 
                web_url, 
                str(exc)
            )
            return []

    def _format_api_output(self, result):
        """
        Standardize the output format from the feedsearch.dev API: https://feedsearch.dev/api/v1/search.
        
        Removes unnecessary fields from the API response to create a cleaner
        output focused on essential RSS feed information.
        
        Args:
            result: List of dictionaries containing raw API response data.
        """
        for item in result:
            for k in self.FIELDS_TO_REMOVE:
                item.pop(k, None)
        return result
        
    def _format_fallback_output(self, result, web_url):
        """
        Format fallback RSS discovery results to match the standard output structure.
        
        Transforms feedsearch library output into the same format as the API
        output, ensuring consistency regardless of which discovery method was used.
        Adds current timestamps and handles missing favicon values.
        
        Args:
            result: List of dictionaries containing feedsearch library results.
            web_url: The original URL that was searched.
        """
        output = []
        for item in result:
            favicon = item.get("favicon")
            if favicon == "":
                favicon = None 
            info = {
                "description" : "",
                "favicon" : favicon,
                "last_seen" : datetime.now(timezone.utc).isoformat(),
                "last_updated" : datetime.now(timezone.utc).isoformat(),
                "site_name" : item.get("site_name", ""),
                "site_url" : web_url,
                "title" : "",
                "url" : item.get("url", "")
            }
            output.append(info)
        return output
    
    def _get_favicon(self, site_url: str) -> str:
        """
        Fetch and encode the favicon of a website as a base64 string.

        Retrieves the favicon using Google's favicon service and returns
        it as a base64-encoded string suitable for embedding in HTML or
        storing in the database.

        Returns
        -------
        str
            A base64-encoded string representation of the favicon image.
        """
        domain = site_url.replace("https://", "").replace("http://", "").rstrip("/")
        favicon_url = f"https://www.google.com/s2/favicons?domain={domain}&sz=32"
        response = httpx.get(favicon_url, follow_redirects=True)
        favicon_bytes = response.content
        return base64.b64encode(favicon_bytes).decode("utf-8")




        
