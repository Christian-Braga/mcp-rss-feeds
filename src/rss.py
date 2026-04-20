from datetime import datetime, timezone
from urllib.parse import urlparse

import tldextract

import db
from rss_feeds.core.orchestrator import RssApplication
from rss_feeds.utils.logger import get_logger

logger = get_logger(__name__)

# RssApplication setup

_rss_app = RssApplication(
    {"RSS_API_ENDPOINT": "https://feedsearch.dev/api/v1/search"}
)


# Sources


def find_and_save_source(site_url: str, tags: list[str] = None) -> dict:
    """
    Discovers the RSS feed for a website URL, saves it to the db, and returns
    the new source dict.

    Raises ValueError if discovery fails or no feeds are found.
    """
    logger.info(f"[Rss] Searching rss link for {site_url}")

    data = _rss_app.discover_rss_links(site_url)

    selected = _select_best_feed(data, site_url)
    logger.debug(f"[Rss] Feed selected: {selected.get('url')}")

    source = db.save_source(
        rss_url=selected["url"],
        site_url=site_url,
        site_name=selected.get("title"),
        description=selected.get("description") or "",
        favicon=selected.get("favicon") or "",
        tags=tags or [],
    )

    logger.info(f"[Rss] Source saved: {source['site_name']} (id={source['id']})")
    return source


def update_source_data(source_id: int, data_to_update: dict) -> dict | None:
    """
    Updates metadata fields on an existing source.
    Accepts: site_name, description, is_active, tags.
    Returns the updated source dict or None if not found.
    """
    allowed = {"site_name", "description", "is_active", "tags"}
    fields = {k: v for k, v in data_to_update.items() if k in allowed}

    if not fields:
        logger.warning("[Rss] update_source_data called with no valid fields")
        return db.get_source_by_id(source_id)

    updated = db.update_source(source_id, **fields)
    if updated:
        logger.info(f"[Rss] Source {source_id} updated: {list(fields.keys())}")
    return updated


#  Feed fetching


def refresh_single_source(source: dict) -> dict:
    """
    Fetches the latest feed items for one source and persists new ones to db.

    Returns a result dict:
        success       bool
        items_created int
        items_skipped int
        error         str | None
    """
    try:
        logger.info(
            f"[Rss] Updating feed: {source['site_url']} from {source['rss_url']}"
        )

        feed = _rss_app.parse_feed(source["rss_url"])
        if not feed:
            raise ValueError(f"Empty feed returned for {source['rss_url']}")

        result = _save_feed_items(source["id"], feed["resources"])

        # Stamp last_updated on success
        db.update_source(
            source["id"],
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            f"[Rss] {source['site_name']}: "
            f"{result['created']} new, {result['skipped']} skipped"
        )
        return {"success": True, "error": None, **result}

    except Exception as exc:
        logger.error(f"[Rss] Update failed for {source.get('site_name')}: {exc}")
        return {"success": False, "items_created": 0, "items_skipped": 0, "error": str(exc)}


def refresh_all_sources() -> list[dict]:
    """
    Fetches and persists new feed items for every active source.
    Returns a list of per-source result dicts (same shape as refresh_single_source).
    """
    sources = db.get_all_sources(active_only=True)
    if not sources:
        logger.info("[Rss] No active sources to refresh")
        return []

    results = []
    for source in sources:
        result = refresh_single_source(source)
        result["source_id"] = source["id"]
        result["source_name"] = source["site_name"]
        results.append(result)

    total_created = sum(r["items_created"] for r in results)
    logger.info(f"[Rss] Refresh complete — {total_created} new items across {len(sources)} sources")
    return results


# Feed items


def update_feed_item(item_id: int, data_to_update: dict) -> dict | None:
    """
    Updates is_read and/or is_saved on a feed item.
    Returns the updated item dict or None if not found.
    """
    allowed = {"is_read", "is_saved"}
    fields = {k: v for k, v in data_to_update.items() if k in allowed}

    if not fields:
        logger.warning("[Rss] update_feed_item called with no valid fields")
        return db.get_feed_item_by_id(item_id)

    updated = db.update_feed_item(item_id, **fields)
    if updated:
        logger.debug(f"[Rss] Item {item_id} updated: {fields}")
    return updated


# Private helpers


def _save_feed_items(source_id: int, items: list) -> dict:
    """
    Normalises raw feed items from RssApplication into the shape db.save_feed_items
    expects, then persists them.

    Stops early when it hits an already-existing URL (items assumed newest-first),
    mirroring the original service behaviour.

    Returns {"created": int, "skipped": int}.
    """
    created = 0
    skipped = 0
    normalised = []

    for item in items:
        url = item.get("link")
        if not url:
            logger.warning(f"[Rss] Skipping item without URL: {item.get('title', 'Unknown')}")
            skipped += 1
            continue

        # Stop as soon as we hit something already in the db
        if db.get_feed_items(source_id=source_id, limit=1):
            existing_urls = {
                i["url_article"]
                for i in db.get_feed_items(source_id=source_id, limit=1000)
            }
            if url in existing_urls:
                logger.info("[Rss] Reached already-stored item — stopping early")
                break

        normalised.append(
            {
                "title": item.get("title") or "Untitled",
                "url_article": url,
                "published_date": _parse_date(item.get("published")),
                "author": item.get("author") or None,
                "media_thumbnail": item.get("media_thumbnail") or None,
                "summary": item.get("summary") or "",
                "content": item.get("content") or "",
            }
        )

    if normalised:
        created = db.save_feed_items(source_id, normalised)
        skipped += len(normalised) - created  # INSERT OR IGNORE silently skipped some

    return {"created": created, "skipped": skipped}


def _parse_date(value: str | None) -> str | None:
    """
    Attempts to parse a date string into ISO 8601 format.
    Returns the original string unchanged if parsing fails, or None if empty.
    Mirrors Django's parse_datetime behaviour but without the Django dependency.
    """
    if not value:
        return None
    try:
        from dateutil.parser import parse as dateutil_parse
        return dateutil_parse(value).isoformat()
    except Exception:
        logger.warning(f"[Rss] Could not parse date: {value!r} — storing as-is")
        return value


def _select_best_feed(feeds: list, site_url: str) -> dict:
    """
    Returns the most domain-relevant feed from a list of candidates.
    Falls back to the first feed if no URL contains a domain component match.
    """
    domain, subdomain = _extract_domain_parts(site_url)
    domain_parts = [domain]
    if subdomain:
        domain_parts.extend(subdomain.split("."))

    for feed in feeds:
        feed_url = feed.get("url", "")
        if any(part in feed_url for part in domain_parts):
            return feed

    logger.warning(
        f"[Rss] No domain match in feed URLs for {site_url} — falling back to first result"
    )
    return feeds[0]


def _extract_domain_parts(url: str) -> tuple[str, str]:
    """
    Extracts (domain, subdomain) from a URL, both lowercase, ignoring the TLD.
    Returns empty strings if not present.
    """
    ext = tldextract.extract(url)
    return (
        ext.domain.lower() if ext.domain else "",
        ext.subdomain.lower() if ext.subdomain else "",
    )