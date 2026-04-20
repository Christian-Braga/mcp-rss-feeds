# server.py — MCP RSS Feeds local server
#
# Transport : stdio (launched as subprocess by the MCP host)
# Usage     : python -m mcp_rss_feeds  (or via claude_desktop_config.json)
#
# Exposes:
#   Tools     — add_source, list_sources, update_source, delete_source,
#               refresh_sources, get_feed, get_item, mark_read, mark_saved,
#               mark_all_read, list_tags, delete_tag,
#               search_feed, suggest_sources, explain_article, find_related
#   Resources — rss://sources, rss://tags
#   Prompts   — daily_briefing, summarize_topic, cleanup_feed,
#               weekly_review, discover_sources, reading_list, triage_feed

from typing import Optional

import trafilatura
from mcp.server.fastmcp import FastMCP

import db
import rss

# Server init

mcp = FastMCP(
    name="mcp-rss-feeds",
    instructions=(
        "You are an RSS feed assistant. You help the user manage their RSS sources, "
        "browse articles, and stay informed. Always refresh sources before reporting "
        "on recent content unless the user explicitly asks not to. "
        "When listing articles, include the item id so the user can act on them. "
        "Always render url_article as a clickable Markdown link: [title](url_article). "
        "Be concise — the user wants information, not ceremony."
    ),
)
# Initialise the SQLite database on startup (idempotent)
db.init_db()


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS
# ══════════════════════════════════════════════════════════════════════════════

# Sources


@mcp.tool()
def add_source(site_url: str, tags: Optional[list[str]] = None) -> dict:
    """
    Discover and add an RSS source from any website URL.

    Automatically finds the RSS feed URL, fetches site metadata (name,
    description, favicon) and saves everything to the local database.
    Optionally attach one or more tags for later filtering.

    Args:
        site_url: The website URL to discover the RSS feed from.
        tags:     Optional list of tag names to categorise the source.

    Returns the saved source dict including its assigned id.
    """
    existing = db.get_source_by_url(site_url)
    if existing:
        return {"already_exists": True, "source": existing}

    source = rss.find_and_save_source(site_url, tags=tags or [])
    return {"already_exists": False, "source": source}


@mcp.tool()
def list_sources(active_only: bool = False) -> list[dict]:
    """
    List all RSS sources saved in the database.

    Args:
        active_only: If True, return only sources that are currently active.

    Returns a list of source dicts ordered alphabetically by site name.
    Each source includes: id, site_name, site_url, rss_url, description,
    favicon, is_active, tags, last_updated, created_at.
    """
    return db.get_all_sources(active_only=active_only)


@mcp.tool()
def update_source(
    source_id: int,
    site_name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """
    Update the metadata of an existing RSS source.

    Only the fields you pass will be updated — everything else stays unchanged.
    Passing tags replaces the entire tag set for that source.

    Args:
        source_id:   The id of the source to update.
        site_name:   New display name for the source.
        description: New description text.
        is_active:   Set to False to disable without deleting.
        tags:        New full list of tags (replaces existing ones).

    Returns the updated source dict, or an error message if not found.
    """
    fields = {}
    if site_name is not None:
        fields["site_name"] = site_name
    if description is not None:
        fields["description"] = description
    if is_active is not None:
        fields["is_active"] = is_active
    if tags is not None:
        fields["tags"] = tags

    updated = rss.update_source_data(source_id, fields)
    if not updated:
        return {"error": f"Source {source_id} not found"}
    return updated


@mcp.tool()
def delete_source(source_id: int) -> dict:
    """
    Permanently delete an RSS source and all its feed items.

    This action is irreversible. Use update_source with is_active=False
    if you want to disable a source without losing its articles.

    Args:
        source_id: The id of the source to delete.

    Returns a confirmation dict with deleted=True/False.
    """
    deleted = db.delete_source(source_id)
    if not deleted:
        return {"deleted": False, "error": f"Source {source_id} not found"}
    return {"deleted": True, "source_id": source_id}


@mcp.tool()
def refresh_sources(source_id: Optional[int] = None) -> dict:
    """
    Fetch the latest articles from RSS sources and save new items to the db.

    If source_id is provided, refreshes only that source.
    Otherwise refreshes all active sources.

    Args:
        source_id: Optional. If given, refresh only this source.

    Returns a summary with total new items and per-source results.
    """
    if source_id is not None:
        source = db.get_source_by_id(source_id)
        if not source:
            return {"error": f"Source {source_id} not found"}
        result = rss.refresh_single_source(source)
        result["source_id"] = source_id
        result["source_name"] = source["site_name"]
        return result

    results = rss.refresh_all_sources()
    total_created = sum(r["items_created"] for r in results)
    total_failed = sum(1 for r in results if not r["success"])
    return {
        "sources_refreshed": len(results),
        "total_new_items": total_created,
        "failed": total_failed,
        "details": results,
    }


# Feed Items


@mcp.tool()
def get_feed(
    tag: Optional[str] = None,
    source_id: Optional[int] = None,
    is_read: Optional[bool] = None,
    is_saved: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """
    Retrieve feed articles with optional filters. All parameters are optional
    and can be combined freely.

    Args:
        tag:       Filter articles to sources tagged with this name.
        source_id: Filter articles to a specific source.
        is_read:   True = only read items, False = only unread items.
        is_saved:  True = only saved items, False = only unsaved items.
        limit:     Max number of articles to return (default 50).
        offset:    Pagination offset (default 0).

    Returns articles ordered by published_date DESC, created_at DESC.
    Each item includes: id, title, url_article, published_date, author,
    summary, is_read, is_saved, source_name.
    """
    return db.get_feed_items(
        tag=tag,
        source_id=source_id,
        is_read=is_read,
        is_saved=is_saved,
        limit=limit,
        offset=offset,
    )


@mcp.tool()
def get_item(item_id: int) -> dict:
    """
    Retrieve the full detail of a single feed article including its content.

    Use this when you need the full text of an article to summarise,
    explain or quote from it.

    Args:
        item_id: The id of the feed item.

    Returns the full item dict including content, summary, author,
    media_thumbnail and source metadata.
    """
    item = db.get_feed_item_by_id(item_id)
    if not item:
        return {"error": f"Item {item_id} not found"}
    return item


@mcp.tool()
def mark_read(item_id: int) -> dict:
    """
    Mark a single feed article as read.

    Args:
        item_id: The id of the article to mark as read.

    Returns the updated item dict.
    """
    updated = rss.update_feed_item(item_id, {"is_read": True})
    if not updated:
        return {"error": f"Item {item_id} not found"}
    return updated


@mcp.tool()
def mark_saved(item_id: int) -> dict:
    """
    Mark a single feed article as saved (bookmarked for later reading).

    Args:
        item_id: The id of the article to save.

    Returns the updated item dict.
    """
    updated = rss.update_feed_item(item_id, {"is_saved": True})
    if not updated:
        return {"error": f"Item {item_id} not found"}
    return updated


@mcp.tool()
def mark_all_read(tag: Optional[str] = None) -> dict:
    """
    Mark all unread articles as read, optionally filtered by tag.

    Useful for clearing the backlog on a topic you no longer want
    to read through.

    Args:
        tag: If provided, only mark articles from sources with this tag.

    Returns the count of articles marked as read.
    """
    count = db.mark_all_read(tag=tag)
    return {"marked_read": count, "tag": tag}


# Tags


@mcp.tool()
def list_tags() -> list[dict]:
    """
    List all tags with the count of sources using each one.

    Returns tags ordered alphabetically. Each entry has:
    id, name, source_count.
    """
    return db.get_all_tags()


@mcp.tool()
def delete_tag(tag_id: int) -> dict:
    """
    Delete a tag and detach it from all sources.

    The sources themselves are not affected — only the tag association
    is removed.

    Args:
        tag_id: The id of the tag to delete.

    Returns a confirmation dict with deleted=True/False.
    """
    deleted = db.delete_tag(tag_id)
    if not deleted:
        return {"deleted": False, "error": f"Tag {tag_id} not found"}
    return {"deleted": True, "tag_id": tag_id}


# LLM-powered tools


@mcp.tool()
def search_feed(query: str, limit: int = 30) -> list[dict]:
    """
    Search saved articles by keyword across title and summary fields.

    Performs a case-insensitive substring search on the local database.
    The results are returned for you to reason over — you should filter
    and rank them semantically based on the user's actual intent.

    Args:
        query: The search string to look for in titles and summaries.
        limit: Max number of candidates to return (default 30).

    Returns matching articles ordered by published_date DESC.
    """
    with db.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                fi.id, fi.title, fi.url_article, fi.published_date,
                fi.author, fi.summary, fi.is_read, fi.is_saved,
                s.site_name AS source_name
            FROM feed_items fi
            JOIN sources s ON s.id = fi.source_id
            WHERE fi.title LIKE ? OR fi.summary LIKE ?
            ORDER BY fi.published_date DESC
            LIMIT ?
            """,
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
    return [db._hydrate_feed_item(dict(r)) for r in rows]


@mcp.tool()
def suggest_sources(topic: str) -> dict:
    """
    Ask the assistant to suggest relevant RSS sources for a topic.

    This tool returns the topic back to you so you can use your knowledge
    to suggest well-known blogs, news sites and feeds on that subject.
    You should then present the suggestions to the user and offer to call
    add_source() on the ones they approve.

    Args:
        topic: The subject area to find RSS sources for.

    Returns the topic and the list of existing tags for context.
    """
    existing_tags = db.get_all_tags()
    existing_sources = db.get_all_sources()
    existing_urls = [s["site_url"] for s in existing_sources]
    return {
        "topic": topic,
        "existing_tags": existing_tags,
        "already_following": existing_urls,
        "instruction": (
            f"Suggest 5-8 high-quality RSS sources about '{topic}'. "
            "For each one provide: site_url, a one-line description of what it covers, "
            "and suggested tags. Exclude sources the user already follows. "
            "Present the list to the user and ask which ones to add."
        ),
    }


@mcp.tool()
def explain_article(item_id: int, fetch_full_content: bool = True) -> dict:
    """
    Fetch a feed article and optionally retrieve its full web content.

    If fetch_full_content is True (default), fetches the article's webpage
    and extracts the full readable text. Falls back to the stored summary
    if fetching fails.

    Args:
        item_id:           The id of the article.
        fetch_full_content: Whether to fetch full content from the web (default True).
    """
    item = db.get_feed_item_by_id(item_id)
    if not item:
        return {"error": f"Item {item_id} not found"}

    db.update_feed_item(item_id, is_read=True)

    if fetch_full_content and item.get("url_article"):
        try:
            downloaded = trafilatura.fetch_url(item["url_article"])
            full_text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
            if full_text:
                item["full_content"] = full_text
                item["content_source"] = "fetched"
            else:
                item["full_content"] = item.get("content") or item.get("summary") or ""
                item["content_source"] = "stored_fallback"
        except Exception as e:
            item["full_content"] = item.get("content") or item.get("summary") or ""
            item["content_source"] = f"fetch_failed: {e}"
    else:
        item["full_content"] = item.get("content") or item.get("summary") or ""
        item["content_source"] = "stored"

    return item


@mcp.tool()
def find_related(item_id: int, limit: int = 10) -> dict:
    """
    Find articles related to a given article by keyword overlap.

    Extracts significant words from the target article's title and searches
    for them across the rest of the feed. Returns candidates for you to
    evaluate and rank by genuine thematic relevance.

    Args:
        item_id: The id of the reference article.
        limit:   Max number of candidates to return (default 10).

    Returns the reference article and a list of candidate related articles.
    After calling this tool, review the candidates and present only the
    genuinely related ones to the user with a short explanation of the link.
    """
    reference = db.get_feed_item_by_id(item_id)
    if not reference:
        return {"error": f"Item {item_id} not found"}

    # Build a simple keyword query from the title (skip short stop words)
    stop_words = {
        "the",
        "a",
        "an",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "and",
        "or",
        "is",
        "are",
    }
    words = [
        w.strip(".,:-")
        for w in reference["title"].lower().split()
        if len(w) > 3 and w not in stop_words
    ]

    candidates = []
    seen_ids = {item_id}
    for word in words[:4]:  # limit to first 4 keywords to avoid noise
        with db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT fi.id, fi.title, fi.url_article, fi.published_date,
                       fi.summary, fi.is_read, s.site_name AS source_name
                FROM feed_items fi
                JOIN sources s ON s.id = fi.source_id
                WHERE (fi.title LIKE ? OR fi.summary LIKE ?)
                  AND fi.id != ?
                ORDER BY fi.published_date DESC
                LIMIT ?
                """,
                (f"%{word}%", f"%{word}%", item_id, limit),
            ).fetchall()
        for row in rows:
            d = dict(row)
            if d["id"] not in seen_ids:
                seen_ids.add(d["id"])
                candidates.append(d)

    return {
        "reference": reference,
        "candidates": candidates[:limit],
        "instruction": (
            "Review the candidates above and identify which ones are genuinely "
            "related to the reference article by theme or topic — not just by "
            "keyword overlap. Present only the relevant ones to the user."
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# RESOURCES
# ══════════════════════════════════════════════════════════════════════════════


@mcp.resource("rss://sources")
def resource_sources() -> str:
    """
    All active RSS sources as a plain-text list.

    Provides passive context about what the user is currently following,
    useful when answering questions like 'what sources do I have on AI?'
    without needing to invoke a tool.
    """
    sources = db.get_all_sources(active_only=True)
    if not sources:
        return "No active sources."
    lines = ["Active RSS sources:\n"]
    for s in sources:
        tags_str = ", ".join(s["tags"]) if s["tags"] else "no tags"
        lines.append(f"  [{s['id']}] {s['site_name']} — {s['site_url']}")
        lines.append(
            f"       tags: {tags_str} | last updated: {s['last_updated'] or 'never'}\n"
        )
    return "\n".join(lines)


@mcp.resource("rss://tags")
def resource_tags() -> str:
    """
    All tags with source counts as a plain-text list.

    Useful as passive context when the user wants to filter or explore
    by topic without needing to call list_tags() explicitly.
    """
    tags = db.get_all_tags()
    if not tags:
        return "No tags defined yet."
    lines = ["Available tags:\n"]
    for t in tags:
        lines.append(f"  [{t['id']}] {t['name']} — {t['source_count']} source(s)")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# PROMPTS
# ══════════════════════════════════════════════════════════════════════════════


@mcp.prompt()
def daily_briefing() -> str:
    """
    Morning digest of today's unread articles across all sources.
    """
    return """
You are preparing the user's daily RSS briefing.

Steps:
1. Call refresh_sources() to fetch the latest articles from all active feeds.
2. Call get_feed(is_read=False, limit=100) to retrieve all unread articles.
3. Filter to articles published in the last 24 hours where possible.
4. Group articles by tag. For each group write 2-3 sentences summarising
   the key themes you see across those articles.
5. Highlight the 3 most interesting or important articles overall — give
   each one a one-line reason why it's worth reading.
6. End with a scoreboard: X new articles across Y sources, Z tags covered.

Tone: concise and informative. This is a briefing, not an essay.
Do not list every article — synthesise and curate.
"""


@mcp.prompt()
def summarize_topic(tag: str) -> str:
    """
    Deep-dive summary of recent articles on a specific topic tag.

    Args:
        tag: The tag name to summarise (e.g. 'ai', 'python', 'security').
    """
    return f"""
The user wants a deep-dive on the topic: "{tag}".

Steps:
1. Call get_feed(tag="{tag}", is_read=False, limit=50) to get recent articles.
2. If fewer than 5 articles are found, also fetch read ones:
   get_feed(tag="{tag}", limit=50).
3. Identify the 3-5 main themes running across these articles.
4. For each theme: name it, summarise what the articles collectively say,
   and note any contrasting viewpoints between different sources.
5. Call out the single most insightful article and explain why.
6. Suggest 1-2 follow-up questions the user might want to explore next.

Be analytical. The user wants to understand the landscape, not just a list.
"""


@mcp.prompt()
def cleanup_feed(days: int = 7) -> str:
    """
    Clear the reading backlog by marking old unread articles as read.

    Args:
        days: Articles older than this many days will be marked as read (default 7).
    """
    return f"""
The user wants to clean up their unread feed backlog.

Steps:
1. Call get_feed(is_read=False, limit=200) to see all unread articles.
2. Identify articles whose published_date is older than {days} days from today.
3. For each one, call mark_read(item_id).
4. Report back: how many articles were marked read, how many unread remain,
   and which tags had the most backlog.

Do not mark saved articles as read — check is_saved before acting.
"""


@mcp.prompt()
def weekly_review() -> str:
    """
    End-of-week summary: reading activity, saved articles and source stats.
    """
    return """
The user wants a review of their RSS activity over the past week.

Steps:
1. Call get_feed(is_read=True, limit=200) — articles read this week.
2. Call get_feed(is_saved=True, limit=100) — articles saved.
3. Call list_sources() — to check last_updated timestamps.
4. Call list_tags() — for the full tag landscape.

Produce a structured weekly report with these sections:

**Reading activity**
- How many articles were read total, across how many sources and tags.
- Which tag had the most activity.

**Saved for later**
- List saved articles grouped by tag with one-line descriptions.
- Flag any that are more than 7 days old (the user may have forgotten them).

**Source health**
- Which sources were most prolific (most new items).
- Which sources haven't been updated in over a week (may be dead feeds).

**Suggested action**
- One concrete suggestion: a source to add, a tag to clean up, or
  a saved article that deserves to be read now.
"""


@mcp.prompt()
def discover_sources(topic: str) -> str:
    """
    Interactive workflow to find and add new RSS sources on a topic.

    Args:
        topic: The subject area to discover sources for (e.g. 'rust programming').
    """
    return f"""
The user wants to expand their RSS feed with new sources about: "{topic}".

Steps:
1. Call suggest_sources(topic="{topic}") to get context about what they
   already follow and receive your instructions.
2. Use your knowledge to suggest 5-8 high-quality sources — well-known blogs,
   newsletters, official feeds — that cover "{topic}" well.
   For each suggestion provide:
   - site_url
   - What it covers (one sentence)
   - Suggested tags
   - Why it's worth following
3. Present the full list to the user and ask: "Which of these would you like
   to add? You can say 'all', name specific ones, or say 'none'."
4. For each approved source, call add_source(site_url, tags=[...]).
5. After adding, call refresh_sources() to fetch the first batch of articles.
6. Report: X sources added, Y initial articles fetched.
"""


@mcp.prompt()
def reading_list() -> str:
    """
    Curated view of all saved articles, prioritised for reading.
    """
    return """
The user wants to review their reading list (saved articles).

Steps:
1. Call get_feed(is_saved=True, limit=100) to get all saved articles.
2. If empty, tell the user they have no saved articles and suggest using
   mark_saved() while browsing to build their list.
3. Group saved articles by tag.
4. Within each group, order by: oldest first (they've been waiting longest).
5. For each article provide: title, source, published date, url_article,
   and a one-line description of what it's about based on the summary.
6. At the end, suggest the single best article to start with and explain why.

Format this as a clean reading list the user can act on immediately.
"""


@mcp.prompt()
def triage_feed() -> str:
    """
    Interactive session to process unread articles: read, save or dismiss.
    """
    return """
The user wants to triage their unread feed — deciding what to read,
save or dismiss.

Steps:
1. Call get_feed(is_read=False, limit=50) to get unread articles.
2. If there are more than 20, ask the user: "You have X unread articles.
   Want to triage by tag? If so, which one? Or shall I go through all of them?"
3. Present articles in batches of 5. For each article show:
   - Title and source
   - Published date
   - One-sentence summary (from the summary field)
   - URL
4. For each batch, ask the user what to do. Accept natural responses like:
   - "read 1 and 3, save 2, skip the rest"
   - "save all of them"
   - "skip everything from that source"
5. Execute the corresponding mark_read() / mark_saved() calls.
6. Continue until all articles in the batch are processed, then ask
   if they want to continue with the next batch.
7. At the end: summary of actions taken.

Be efficient. Don't repeat article details after the user has decided.
"""


# ══════════════════════════════════════════════════════════════════════════════
# Entrypoint
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run(transport="stdio")
