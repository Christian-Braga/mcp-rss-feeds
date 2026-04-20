import sqlite3
from pathlib import Path
from typing import Optional
from platformdirs import user_data_dir

APP_NAME = "mcp-rss-feeds"

# ── Database ───────────────────────────────────────────────────────────────────
# SQLite database managed automatically by the MCP server.
#
# Location (platform-specific, created on first run):
#   macOS   → ~/Library/Application Support/mcp-rss-feeds/db.sqlite3
#   Linux   → ~/.local/share/mcp-rss-feeds/db.sqlite3
#   Windows → %LOCALAPPDATA%\mcp-rss-feeds\db.sqlite3
#
# Schema (4 tables):
#   tags         → unique tag names used to categorise sources
#   sources      → RSS sources (url, metadata, active flag)
#   source_tags  → M2M join between sources and tags
#   feed_items   → articles fetched from sources (read/saved state)
#
# Initialisation:
#   init_db() is called once at server startup — creates the file and
#   applies the schema with IF NOT EXISTS. Safe to call on every restart.
# ──────────────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    rss_url      TEXT    NOT NULL UNIQUE,
    site_url     TEXT    NOT NULL DEFAULT '',
    site_name    TEXT    NOT NULL DEFAULT '',
    description  TEXT,
    favicon      TEXT,
    is_active    INTEGER NOT NULL DEFAULT 1,
    last_updated TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Join table for the M2M between sources and tags
CREATE TABLE IF NOT EXISTS source_tags (
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    tag_id    INTEGER NOT NULL REFERENCES tags(id)    ON DELETE CASCADE,
    PRIMARY KEY (source_id, tag_id)
);

CREATE TABLE IF NOT EXISTS feed_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id        INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    title            TEXT    NOT NULL DEFAULT '',
    url_article      TEXT    NOT NULL UNIQUE,
    published_date   TEXT,
    author           TEXT,
    media_thumbnail  TEXT,
    summary          TEXT,
    content          TEXT,
    is_saved         INTEGER NOT NULL DEFAULT 0,
    is_read          INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_feed_items_source        ON feed_items(source_id);
CREATE INDEX IF NOT EXISTS idx_feed_items_is_read       ON feed_items(is_read);
CREATE INDEX IF NOT EXISTS idx_feed_items_is_saved      ON feed_items(is_saved);
CREATE INDEX IF NOT EXISTS idx_feed_items_published     ON feed_items(published_date DESC);
CREATE INDEX IF NOT EXISTS idx_source_tags_source       ON source_tags(source_id);
CREATE INDEX IF NOT EXISTS idx_source_tags_tag          ON source_tags(tag_id);
"""

# Path & connection


def get_db_path() -> Path:
    """
    Returns the platform-appropriate path for db.sqlite3.
      macOS   → ~/Library/Application Support/mcp-rss-feeds/db.sqlite3
      Linux   → ~/.local/share/mcp-rss-feeds/db.sqlite3
      Windows → C:\\Users\\<you>\\AppData\\Local\\mcp-rss-feeds\\db.sqlite3
    """
    data_dir = Path(user_data_dir(APP_NAME))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "db.sqlite3"


def get_connection() -> sqlite3.Connection:
    """Opens a connection with row_factory so rows behave like dicts."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """
    Called once at server startup.
    Creates the db file and all tables/indexes if they don't exist.
    Idempotent — safe to call every time thanks to IF NOT EXISTS.
    """
    with get_connection() as conn:
        conn.executescript(SCHEMA)


# Tags


def get_or_create_tag(name: str) -> dict:
    """Returns existing tag or creates it. Always returns the tag dict."""
    name = name.strip().lower()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tags WHERE name = ?", (name,)).fetchone()
        if row:
            return dict(row)
        cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        return {"id": cursor.lastrowid, "name": name}


def get_all_tags() -> list[dict]:
    """
    Returns all tags with a count of how many active sources use each one.
    Ordered alphabetically.
    """
    query = """
        SELECT
            t.id,
            t.name,
            COUNT(st.source_id) AS source_count
        FROM tags t
        LEFT JOIN source_tags st ON st.tag_id = t.id
        GROUP BY t.id
        ORDER BY t.name ASC
    """
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
    return [dict(r) for r in rows]


def delete_tag(tag_id: int) -> bool:
    """Deletes a tag and removes it from all sources. Returns True if found."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    return cursor.rowcount > 0


# Sources


def save_source(
    rss_url: str,
    site_url: str = "",
    site_name: str = "",
    description: str = "",
    favicon: str = "",
    tags: list[str] = None,
) -> dict:
    """
    Inserts a new source and attaches tags (created if needed).
    Returns the full source dict including tags list.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sources (rss_url, site_url, site_name, description, favicon)
            VALUES (?, ?, ?, ?, ?)
            """,
            (rss_url, site_url, site_name, description, favicon),
        )
        source_id = cursor.lastrowid

    if tags:
        _set_source_tags(source_id, tags)

    return get_source_by_id(source_id)


def get_source_by_id(source_id: int) -> dict | None:
    """Returns a source dict with its tags list, or None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
    if not row:
        return None
    return _hydrate_source(dict(row))


def get_source_by_url(rss_url: str) -> dict | None:
    """Looks up a source by its RSS URL."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sources WHERE rss_url = ?", (rss_url,)
        ).fetchone()
    if not row:
        return None
    return _hydrate_source(dict(row))


def get_all_sources(active_only: bool = False) -> list[dict]:
    """
    Returns all sources with their tags.
    Pass active_only=True to skip disabled sources.
    """
    query = "SELECT * FROM sources"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY site_name ASC"
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
    return [_hydrate_source(dict(r)) for r in rows]


def update_source(source_id: int, **fields) -> dict | None:
    """
    Updates any subset of source fields.
    Pass tags=[...] as a Python list to replace the tag set entirely.
    Returns the updated source dict or None if not found.
    """
    tags = fields.pop("tags", None)

    if fields:
        allowed = {
            "site_name",
            "site_url",
            "description",
            "favicon",
            "is_active",
            "last_updated",
        }
        fields = {k: v for k, v in fields.items() if k in allowed}

        if "is_active" in fields:
            fields["is_active"] = 1 if fields["is_active"] else 0

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [source_id]
        with get_connection() as conn:
            conn.execute(f"UPDATE sources SET {set_clause} WHERE id = ?", values)

    if tags is not None:
        _set_source_tags(source_id, tags)

    return get_source_by_id(source_id)


def delete_source(source_id: int) -> bool:
    """
    Deletes a source. Cascades to feed_items and source_tags automatically.
    Returns True if a row was deleted.
    """
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    return cursor.rowcount > 0


# Feed Items


def save_feed_items(source_id: int, items: list[dict]) -> int:
    """
    Bulk-inserts feed items for a source.
    Skips duplicates silently (keyed on url_article).
    Returns the count of newly inserted rows.
    """
    inserted = 0
    with get_connection() as conn:
        for item in items:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO feed_items
                    (source_id, title, url_article, published_date,
                     author, media_thumbnail, summary, content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    item.get("title", ""),
                    item.get("url_article", ""),
                    item.get("published_date"),
                    item.get("author"),
                    item.get("media_thumbnail"),
                    item.get("summary"),
                    item.get("content"),
                ),
            )
            inserted += cursor.rowcount
    return inserted


def get_feed_items(
    tag: Optional[str] = None,
    source_id: Optional[int] = None,
    is_read: Optional[bool] = None,
    is_saved: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """
    Returns feed items with optional filters, most recent first.
    Mirrors the Django FeedItem default ordering: -published_date, -created_at.
    """
    conditions = []
    params: list = []

    if source_id is not None:
        conditions.append("fi.source_id = ?")
        params.append(source_id)

    if is_read is not None:
        conditions.append("fi.is_read = ?")
        params.append(1 if is_read else 0)

    if is_saved is not None:
        conditions.append("fi.is_saved = ?")
        params.append(1 if is_saved else 0)

    if tag:
        conditions.append(
            """
            fi.source_id IN (
                SELECT st.source_id FROM source_tags st
                JOIN tags t ON t.id = st.tag_id
                WHERE t.name = ?
            )
            """
        )
        params.append(tag.strip().lower())

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    query = f"""
        SELECT
            fi.id, fi.title, fi.url_article, fi.published_date,
            fi.author, fi.media_thumbnail, fi.summary, fi.content,
            fi.is_read, fi.is_saved, fi.created_at,
            s.site_name AS source_name, s.id AS source_id, s.favicon
        FROM feed_items fi
        JOIN sources s ON s.id = fi.source_id
        {where}
        ORDER BY fi.published_date DESC, fi.created_at DESC
        LIMIT ? OFFSET ?
    """
    params += [limit, offset]

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_hydrate_feed_item(dict(r)) for r in rows]


def get_feed_item_by_id(item_id: int) -> dict | None:
    """Returns a single feed item with its source name, or None."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT fi.*, s.site_name AS source_name, s.favicon
            FROM feed_items fi
            JOIN sources s ON s.id = fi.source_id
            WHERE fi.id = ?
            """,
            (item_id,),
        ).fetchone()
    return _hydrate_feed_item(dict(row)) if row else None


def update_feed_item(item_id: int, **fields) -> dict | None:
    """
    Updates is_read and/or is_saved on a single item.
    Returns the updated item or None if not found.
    """
    allowed = {"is_read", "is_saved"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return get_feed_item_by_id(item_id)

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = [1 if v else 0 for v in fields.values()] + [item_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE feed_items SET {set_clause} WHERE id = ?", values)
    return get_feed_item_by_id(item_id)


def mark_all_read(tag: Optional[str] = None) -> int:
    """
    Marks all unread items as read.
    If tag is provided, only affects items from sources with that tag.
    Returns the count of updated rows.
    """
    if tag:
        query = """
            UPDATE feed_items SET is_read = 1
            WHERE is_read = 0 AND source_id IN (
                SELECT st.source_id FROM source_tags st
                JOIN tags t ON t.id = st.tag_id
                WHERE t.name = ?
            )
        """
        params = [tag.strip().lower()]
    else:
        query = "UPDATE feed_items SET is_read = 1 WHERE is_read = 0"
        params = []

    with get_connection() as conn:
        cursor = conn.execute(query, params)
    return cursor.rowcount


# Private helpers


def _get_tags_for_source(source_id: int) -> list[str]:
    """Returns the list of tag names attached to a source."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT t.name FROM tags t
            JOIN source_tags st ON st.tag_id = t.id
            WHERE st.source_id = ?
            ORDER BY t.name ASC
            """,
            (source_id,),
        ).fetchall()
    return [r["name"] for r in rows]


def _set_source_tags(source_id: int, tag_names: list[str]) -> None:
    """
    Replaces the full tag set for a source.
    Creates tags that don't exist yet.
    """
    with get_connection() as conn:
        conn.execute("DELETE FROM source_tags WHERE source_id = ?", (source_id,))
    for name in tag_names:
        tag = get_or_create_tag(name)
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO source_tags (source_id, tag_id) VALUES (?, ?)",
                (source_id, tag["id"]),
            )


def _hydrate_source(row: dict) -> dict:
    """Attaches the tags list to a source dict and normalises booleans."""
    row["tags"] = _get_tags_for_source(row["id"])
    row["is_active"] = bool(row["is_active"])
    return row


def _hydrate_feed_item(row: dict) -> dict:
    """Normalises boolean fields on a feed item dict."""
    row["is_read"] = bool(row["is_read"])
    row["is_saved"] = bool(row["is_saved"])
    return row
