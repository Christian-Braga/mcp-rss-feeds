from rss_feeds.utils.logger import get_logger
from rss_feeds.core.services.rss_finder.web_page import RssWebPage
from rss_feeds.core.services.rss_finder.youtube import RssYoutube
import re

class RssFinder:
    """
    Orchestrator that selects the RSS retrieval strategy based on the given URL.

    This class evaluates an input URL against a set of registered patterns 
    (strategies) to determine if it belongs to a specific platform like YouTube 
    or a generic website, then delegates the extraction to the appropriate handler.

    Parameters
    ----------
    api_address : str
        The base API address used by the web page finder for RSS discovery.

    Attributes
    ----------
    api : str
        The stored API address.
    logger : logging.Logger
        Logger instance for the 'RSSF' component.
    strategies : list of dict
        A list containing regex patterns, their corresponding handler instances, 
        and descriptive names.
    """

    def __init__(self, api_address):
        self.api = api_address
        self.logger = get_logger("RSSF")
        self.strategies = [
            {
                "pattern": r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+",
                "handler": RssYoutube(),
                "name": "Youtube"
            },
            {
                "pattern": r".+", 
                "handler": RssWebPage(api_address=self.api),
                "name": "Website"
            }
        ]
    
    # Main Function

    def get_rss_feed(self, source_url: str):
        """
        Identify the source type and retrieve the corresponding RSS feeds.

        Parameters
        ----------
        source_url : str
            The URL of the source to be analyzed for RSS feeds.

        Returns
        -------
        list
            A list of discovered RSS feed objects. 
            Returns an empty list if no handler is found or an error occurs.
        """
        handler = self._resolve_handler(source_url)
        if not handler:
            self.logger.debug("[RSSF] Impossible to retrieve the url source type")
            return []
            
        return handler.find(web_url=source_url)

    # Support Function

    def _resolve_handler(self, source_url: str):
        """
        Match the URL against defined strategies to find the appropriate handler.

        Evaluation is performed sequentially; the first regex to match 
        the source_url determines the handler used.

        Parameters
        ----------
        source_url : str
            The URL to be matched.

        Returns
        -------
        object or None
            The handler instance (e.g., RssYoutube or RssWebPage) if a match 
            is found, otherwise None.
        """
        self.logger.info(f"[RSSF] Resolving source type for: {source_url}")
        
        for strategy in self.strategies:
            if re.match(strategy["pattern"], source_url):
                self.logger.info(f"[RSSF] Detected source: {strategy['name']}")
                return strategy["handler"]
        
        return None

