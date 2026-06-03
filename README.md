# mcp-rss-feeds

An MCP server to manage and explore your RSS feeds through any MCP-compatible AI client.

Add sources, browse articles, get daily briefings and discover new content — all through a conversation, without leaving your AI assistant.

---

## What is this

`mcp-rss-feeds` is a **local MCP server** that runs on your machine and connects to any AI client that supports the Model Context Protocol — including Claude Desktop, Claude Code, and compatible agents.

### What is MCP

[Model Context Protocol](https://modelcontextprotocol.io) (MCP) is an open standard introduced by Anthropic that defines how AI assistants communicate with external tools and data sources. It works like a USB-C port for AI: any MCP-compatible client can plug into any MCP server using the same protocol, regardless of who built either side.

### How it works locally

This server uses the **stdio transport**: when you configure it in Claude Desktop, the app launches the Python script as a subprocess on your machine. Communication happens through standard input/output — no HTTP server, no open ports, no network exposure.

```
Claude Desktop  ──stdio──▶  mcp-rss-feeds (your machine)  ──▶  SQLite (your machine)
   (MCP host)                   (MCP server)                      (local db)
```

Everything stays on your machine. The AI assistant calls tools in the server, the server reads and writes a local SQLite database, and results flow back through the same stdio channel.

### Privacy & security

- **No data leaves your machine.** The SQLite database is stored in your OS user data directory and is never transmitted anywhere.
- **No ports are opened.** The stdio transport does not expose any network interface.
- **No files outside the data directory are touched.** The server only reads/writes its own SQLite database and temporary HTML files in your system temp folder.
- **Read-only filesystem access.** The server has no mechanism to access, modify or delete files on your machine outside its own data directory.
- **Data directory locations:**
  - macOS: `~/Library/Application Support/mcp-rss-feeds/`
  - Linux: `~/.local/share/mcp-rss-feeds/`
  - Windows: `%LOCALAPPDATA%\mcp-rss-feeds\`

---

## Setup & installation

### Requirements

- Python 3.11 or higher
- [Claude Desktop](https://claude.ai/download) (or any MCP-compatible client)
- Git

### 1. Clone the repository

```bash
git clone https://github.com/Christian-Braga/mcp-rss-feeds.git
cd mcp-rss-feeds
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -e .
```

### 4. Find your Python path

You will need the absolute path to the Python executable inside your virtual environment for the Claude Desktop configuration.

```bash
# macOS / Linux
which python

# Windows
where python
```

Copy the output — it will look something like:
- macOS/Linux: `/Users/yourname/projects/mcp-rss-feeds/.venv/bin/python`
- Windows: `C:\Users\yourname\projects\mcp-rss-feeds\.venv\Scripts\python.exe`

### 5. Configure Claude Desktop

You have two ways to do this — via the Claude Desktop UI (recommended) or by editing the config file manually.


#### Method A — Claude Desktop UI (recommended)

1. Open Claude Desktop
2. Go to **Settings** → **Developer** → **Edit Config**

This opens `claude_desktop_config.json` directly in your default text editor. You can also reach it from the **Claude menu** (top-left on macOS) → **Settings** → **Developer** tab.

3. Add the `mcp-rss-feeds` block inside `"mcpServers"`, replacing the paths with your own:

```json
{
  "mcpServers": {
    "mcp-rss-feeds": {
      "command": "/absolute/path/to/mcp-rss-feeds/.venv/bin/python",
      "args": [
        "/absolute/path/to/mcp-rss-feeds/src/mcp_server.py"
      ]
    }
  }
}
```

4. Save the file and restart Claude Desktop.


#### Method B — Edit the config file manually

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

**macOS example:**

```json
{
  "mcpServers": {
    "mcp-rss-feeds": {
      "command": "/Users/yourname/projects/mcp-rss-feeds/.venv/bin/python",
      "args": [
        "/Users/yourname/projects/mcp-rss-feeds/src/mcp_rss_feeds/server.py"
      ]
    }
  }
}
```

**Windows example:**

```json
{
  "mcpServers": {
    "mcp-rss-feeds": {
      "command": "C:\\Users\\yourname\\projects\\mcp-rss-feeds\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\yourname\\projects\\mcp-rss-feeds\\src\\mcp_rss_feeds\\server.py"
      ]
    }
  }
}
```

> **Note:** if you already have other MCP servers configured, only add the `"mcp-rss-feeds"` block inside the existing `"mcpServers"` object — do not overwrite the entire file.

### 6. Restart Claude Desktop

Fully quit and relaunch Claude Desktop. You should see a hammer icon (🔨) in the chat input bar indicating that MCP tools are available.

### Verifying the connection

Type this in Claude Desktop to confirm everything is working:

```
List my RSS sources
```

Claude will call `list_sources()` and reply that no sources have been added yet — that is the expected first response.

---

## Usage

Once connected, interact with your RSS feeds entirely through conversation. Some examples to get started:

```
Add https://simonwillison.net to my feeds with tags "ai" and "python"

Give me my daily briefing

What's been happening in AI this week?

Save article 42 for later

Mark everything older than 7 days as read

Show me my reading list

Find sources about Rust programming and add the ones I like
```

---

## Tools, Resources & Prompts

### 🔧 Tools

Tools are actions Claude can execute on your behalf. All tool calls are explicit and visible in the conversation.

#### Source management

| Tool | Parameters | Description |
|---|---|---|
| `add_source` | `site_url`, `tags?` | Discovers the RSS feed for any website URL and saves it. Automatically fetches metadata (name, description, favicon). |
| `list_sources` | `active_only?` | Lists all saved sources with their tags and last update time. |
| `update_source` | `source_id`, `site_name?`, `description?`, `is_active?`, `tags?` | Updates any metadata field on a source. Pass `is_active=false` to disable without deleting. |
| `delete_source` | `source_id` | Permanently deletes a source and all its articles. |
| `refresh_sources` | `source_id?` | Fetches the latest articles from all active sources (or one specific source). |

#### Feed items

| Tool | Parameters | Description |
|---|---|---|
| `get_feed` | `tag?`, `source_id?`, `is_read?`, `is_saved?`, `limit?`, `offset?` | Retrieves articles with optional filters. All parameters combinable. |
| `get_item` | `item_id` | Returns the full detail of a single article including content and summary. |
| `mark_read` | `item_id` | Marks an article as read. |
| `mark_saved` | `item_id` | Bookmarks an article for later reading. |
| `mark_all_read` | `tag?` | Marks all unread articles as read, optionally filtered by tag. |

#### Tags

| Tool | Parameters | Description |
|---|---|---|
| `list_tags` | — | Lists all tags with the count of sources using each one. |
| `delete_tag` | `tag_id` | Deletes a tag and removes it from all sources. |

#### AI-powered tools

These tools combine database retrieval with Claude's reasoning capabilities.

| Tool | Parameters | Description |
|---|---|---|
| `explain_article` | `item_id`, `fetch_full_content?` | Fetches the full web content of an article using `trafilatura` and returns it for Claude to explain, summarise or analyse. Falls back to stored summary if fetching fails. |
| `search_feed` | `query`, `limit?` | Searches article titles and summaries by keyword. Claude then ranks results by semantic relevance to your actual intent. |
| `suggest_sources` | `topic` | Returns context for Claude to suggest high-quality RSS sources on a topic. Claude presents the list and asks which to add. |
| `find_related` | `item_id`, `limit?` | Finds articles with keyword overlap to a reference article. Claude evaluates the candidates and surfaces only genuinely related ones. |
| `open_youtube_feed` | `limit?` | Generates and opens a local HTML page showing YouTube feed items with their thumbnails. |

---

### 📄 Resources

Resources are read-only data that Claude can load as background context without invoking an action.

| Resource | URI | Description |
|---|---|---|
| Sources | `rss://sources` | All active sources as a formatted text list including tags and last update time. |
| Tags | `rss://tags` | All available tags with source counts, ordered alphabetically. |

---

### 💬 Prompts

Prompts are pre-built conversation workflows. Trigger them by describing what you want — Claude recognises the intent and executes the full workflow automatically.

| Prompt | Trigger example | Description |
|---|---|---|
| `daily_briefing` | *"Give me my morning briefing"* | Refreshes all sources, retrieves today's unread articles, groups them by tag, highlights the 3 most interesting, and ends with a count. |
| `summarize_topic` | *"Summarise what's been happening in AI"* | Deep-dive on a specific tag: identifies themes, contrasting viewpoints across sources, and the single most insightful article. |
| `cleanup_feed` | *"Clean up my backlog"* | Marks articles older than N days as read (default 7). Skips saved articles. Reports what was cleared. |
| `weekly_review` | *"Give me my weekly review"* | Covers reading activity, saved articles, most active sources, and flags dead feeds. Ends with one concrete action suggestion. |
| `discover_sources` | *"Find me sources about Rust"* | Suggests 5-8 quality sources on a topic, presents them for approval, adds confirmed ones and fetches the first batch of articles. |
| `reading_list` | *"Show me my reading list"* | Displays all saved articles grouped by tag, ordered oldest-first, with a recommendation on where to start. |
| `triage_feed` | *"Help me go through my unread articles"* | Interactive session: presents unread articles in batches of 5, accepts natural language decisions (read/save/skip), executes actions and reports a summary. |

---

## License

MIT
