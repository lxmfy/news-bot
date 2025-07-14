import os
import sqlite3
import threading
from datetime import datetime, timezone

import feedparser
import trafilatura
import yaml


class FeedManager:
    def __init__(self):
        self.thread_local = threading.local()

        # Get paths from environment variables with fallbacks to user directories
        home = os.path.expanduser("~")

        # Platform-specific default paths
        if os.name == "nt":  # Windows
            default_data_dir = os.path.join(os.getenv("APPDATA"), "lxmfy-news-bot")
        elif os.name == "darwin":  # macOS
            default_data_dir = os.path.join(
                home, "Library", "Application Support", "lxmfy-news-bot"
            )
        else:  # Linux and others
            default_data_dir = os.path.join(home, ".local", "share", "lxmfy-news-bot")

        default_backup_dir = os.path.join(default_data_dir, "backups")

        self.data_dir = os.getenv("DATA_DIR", default_data_dir)
        self.backup_dir = os.getenv("BACKUP_DIR", default_backup_dir)
        self.config_dir = os.getenv(
            "CONFIG_DIR", os.path.dirname(os.path.abspath(__file__))
        )

        # Ensure directories exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        self.get_db()
        self.setup_database()
        self.load_feed_config()

    def get_db(self):
        """Get thread-local database connection"""
        if not hasattr(self.thread_local, "db"):
            db_path = os.path.join(self.data_dir, "feed.db")
            self.thread_local.db = sqlite3.connect(db_path)
        return self.thread_local.db

    def setup_database(self):
        cursor = self.get_db().cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Get current version
        cursor.execute("SELECT MAX(version) FROM schema_version")
        current_version = cursor.fetchone()[0] or 0

        # Define migrations
        migrations = [
            # Version 1: Initial schema
            """
            CREATE TABLE IF NOT EXISTS feeds (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                last_check TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS users (
                hash TEXT PRIMARY KEY,
                timezone TEXT DEFAULT 'UTC',
                update_time TEXT DEFAULT '09:00',
                schedule_hours INTEGER DEFAULT 24,
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                user_hash TEXT,
                feed_id INTEGER,
                FOREIGN KEY(user_hash) REFERENCES users(hash),
                FOREIGN KEY(feed_id) REFERENCES feeds(id),
                PRIMARY KEY(user_hash, feed_id)
            );

            CREATE TABLE IF NOT EXISTS sent_items (
                id INTEGER PRIMARY KEY,
                feed_id INTEGER,
                item_id TEXT,
                sent_date TIMESTAMP,
                FOREIGN KEY(feed_id) REFERENCES feeds(id)
            );
            """,
            # Version 2: Add feed statistics
            """
            CREATE TABLE IF NOT EXISTS feed_stats (
                feed_id INTEGER,
                total_articles INTEGER DEFAULT 0,
                last_article_date TIMESTAMP,
                FOREIGN KEY(feed_id) REFERENCES feeds(id)
            );
            """,
        ]

        for version, migration in enumerate(
            migrations[current_version:], current_version + 1
        ):
            try:
                cursor.executescript(migration)
                cursor.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (version,)
                )
                print(f"Applied database migration version {version}")
            except Exception as e:  # noqa: PERF203
                # The try-except block is intentionally inside the loop
                # to ensure transactional integrity for each migration.
                # If a migration fails, the transaction is rolled back,
                # and the error is propagated.
                print(f"Error applying migration {version}: {e}")
                self.get_db().rollback()
                raise

        self.get_db().commit()

    def get_active_subscriptions(self):
        """Get all active user subscriptions"""
        cursor = self.get_db().cursor()
        cursor.execute("""
            SELECT
                u.hash,
                u.timezone,
                u.update_time,
                f.id,
                f.url,
                f.name,
                COALESCE(u.schedule_hours, 24) as schedule_hours,
                COALESCE(u.last_update, datetime('now')) as last_update
            FROM users u
            JOIN subscriptions s ON u.hash = s.user_hash
            JOIN feeds f ON s.feed_id = f.id
            WHERE u.active = 1
        """)
        results = cursor.fetchall()

        processed_results = []
        for row in results:
            last_update = datetime.fromisoformat(row[7].replace(" ", "T")).replace(
                tzinfo=timezone.utc
            )
            processed_results.append(row[:7] + (last_update,))

        return processed_results

    def add_subscription(self, user_hash, feed_urls, feed_names=None):
        """Add new subscriptions with support for multiple URLs"""
        if isinstance(feed_urls, str):
            feed_urls = [feed_urls]

        if feed_names is None:
            feed_names = feed_urls
        elif isinstance(feed_names, str):
            feed_names = [feed_names]

        while len(feed_names) < len(feed_urls):
            feed_names.append(feed_urls[len(feed_names)])

        success_count = 0
        results = []

        for feed_url, feed_name in zip(feed_urls, feed_names):
            cursor = self.get_db().cursor()
            try:
                feed_info, error = self.preview_feed(feed_url)
                if error:
                    results.append((feed_url, False, error))
                    continue

                if feed_name == feed_url and feed_info:
                    feed_name = feed_info["title"]

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO feeds (url, name, last_check)
                    VALUES (?, ?, ?)
                """,
                    (feed_url, feed_name, datetime.now(timezone.utc)),
                )

                feed_id = (
                    cursor.lastrowid
                    or cursor.execute(
                        "SELECT id FROM feeds WHERE url = ?", (feed_url,)
                    ).fetchone()[0]
                )

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO users (hash) VALUES (?)
                """,
                    (user_hash,),
                )

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO subscriptions (user_hash, feed_id)
                    VALUES (?, ?)
                """,
                    (user_hash, feed_id),
                )

                self.get_db().commit()
                success_count += 1
                results.append((feed_url, True, feed_name))
            except Exception as e:
                self.get_db().rollback()
                results.append((feed_url, False, str(e)))

        return success_count > 0, results

    def remove_subscription(self, user_hash, feed_name):
        """Remove a subscription"""
        cursor = self.get_db().cursor()
        cursor.execute(
            """
            DELETE FROM subscriptions
            WHERE user_hash = ? AND feed_id IN
                (SELECT id FROM feeds WHERE name = ?)
        """,
            (user_hash, feed_name),
        )

        affected = cursor.rowcount > 0
        self.get_db().commit()
        return affected

    def get_user_subscriptions(self, user_hash):
        """Get subscriptions for a user"""
        cursor = self.get_db().cursor()
        cursor.execute(
            """
            SELECT f.name, f.url
            FROM feeds f
            JOIN subscriptions s ON f.id = s.feed_id
            WHERE s.user_hash = ?
        """,
            (user_hash,),
        )
        return cursor.fetchall()

    def update_user_timezone(self, user_hash, timezone):
        """Update user's timezone"""
        cursor = self.get_db().cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO users (hash, timezone)
            VALUES (?, ?)
        """,
            (user_hash, timezone),
        )
        self.get_db().commit()

    def update_user_time(self, user_hash, update_time):
        """Update user's update time"""
        cursor = self.get_db().cursor()
        cursor.execute(
            """
            UPDATE users SET update_time = ? WHERE hash = ?
        """,
            (update_time, user_hash),
        )
        self.get_db().commit()

    @staticmethod
    def process_feed(feed_url):
        """Process a feed and return formatted entries"""
        try:
            feed = feedparser.parse(feed_url)

            return [
                {
                    "title": entry.get("title", "No title"),
                    "description": entry.get("description", "No description"),
                    "link": entry.get("link", "No link"),
                    "id": entry.get("id", entry.get("link", entry.get("title", ""))),
                }
                for entry in feed.entries[:5]
            ]

        except Exception as e:
            print(f"Feed processing error for {feed_url}: {str(e)}")
            return []

    def mark_sent(self, feed_id, item_id):
        """Mark an item as sent"""
        cursor = self.get_db().cursor()
        cursor.execute(
            """
            INSERT INTO sent_items (feed_id, item_id, sent_date)
            VALUES (?, ?, ?)
        """,
            (feed_id, item_id, datetime.now(timezone.utc)),
        )
        self.get_db().commit()

    def is_sent(self, feed_id, item_id):  # noqa: PYL-R0201
        """Check if an item was already sent"""
        # This method uses self.get_db() and thus cannot be a static method.
        cursor = self.get_db().cursor()
        cursor.execute(
            """
            SELECT 1 FROM sent_items
            WHERE feed_id = ? AND item_id = ?
        """,
            (feed_id, item_id),
        )
        return cursor.fetchone() is not None

    def preview_feed(self, feed_url):
        """Preview a feed without subscribing"""
        try:
            # Basic URL validation
            if not feed_url.startswith(("http://", "https://", "feed://")):
                return (
                    None,
                    "Invalid URL format. Must start with http://, https://, or feed://",
                )

            # Parse feed
            feed = feedparser.parse(feed_url)

            feed_info = {
                "title": feed.feed.get("title", "Unknown Feed"),
                "description": feed.feed.get("description", "No description"),
                "link": feed.feed.get("link", feed_url),
                "entries": [],
            }

            # Limit to 5 entries
            for entry in feed.entries[:5]:
                # Try to get full text
                full_text = ""
                if entry.get("link"):
                    try:
                        downloaded = trafilatura.fetch_url(entry.link)
                        if downloaded:
                            full_text = trafilatura.extract(downloaded)
                    except Exception as e:
                        print(f"Full text extraction error: {str(e)}")

                feed_info["entries"].append(
                    {
                        "title": entry.get("title", "No title"),
                        "description": full_text
                        or entry.get("description", "No description"),
                        "link": entry.get("link", "No link"),
                        "published": entry.get(
                            "published",
                            entry.get("updated", entry.get("created", "Unknown date")),
                        ),
                    }
                )

            return feed_info, None

        except Exception as e:
            print(f"Feed preview error for {feed_url}: {str(e)}")
            return None, str(e)

    def load_feed_config(self):
        """Load feed configuration from YAML"""
        config_path = os.path.join(self.config_dir, "feeds.yml")
        custom_config = os.getenv("FEEDS_CONFIG")

        if custom_config and os.path.exists(custom_config):
            config_path = custom_config

        try:
            with open(config_path, "r") as f:
                self.feed_config = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading feed config: {str(e)}")
            self.feed_config = {"groups": {}, "feeds": {}, "default": []}

    def get_feed_group(self, group_name):
        """Get feeds from a specific group"""
        group_name = group_name.lower()
        if group_name in self.feed_config["groups"]:
            return self.feed_config["groups"][group_name]
        return None

    def get_named_feed(self, feed_name):
        """Get a specific named feed"""
        feed_name = feed_name.lower()
        if feed_name in self.feed_config["feeds"]:
            return [self.feed_config["feeds"][feed_name]]
        return None

    def get_default_feeds(self):
        """Get the default feed selection"""
        return self.feed_config["default"]

    def parse_feed_input(self, input_str):
        """Parse user input for feeds or categories."""
        # Default if empty or explicit 'default'
        if not input_str or input_str.lower() == "default":
            return self.get_default_feeds()

        cfg = self.feed_config or {}
        key = input_str.lower()

        # Exact group name
        if key in cfg.get("groups", {}):
            return cfg["groups"][key]

        # Exact named feed
        if key in cfg.get("feeds", {}):
            return [cfg["feeds"][key]]

        # Split by commas or whitespace for multiple entries
        tokens = input_str.replace(",", " ").split()
        feeds = []
        for token in tokens:
            k = token.lower()
            if k in cfg.get("groups", {}):
                feeds.extend(cfg["groups"][k])
            elif k in cfg.get("feeds", {}):
                feeds.append(cfg["feeds"][k])

        # Return feeds list or None if nothing found
        return feeds if feeds else None

    def update_user_schedule(self, user_hash, hours):
        """Update user's schedule in hours"""
        cursor = self.get_db().cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO users (hash) VALUES (?)
        """,
            (user_hash,),
        )
        cursor.execute(
            """
            UPDATE users SET
                schedule_hours = ?,
                last_update = ?
            WHERE hash = ?
        """,
            (hours, datetime.now(timezone.utc), user_hash),
        )
        self.get_db().commit()

    def get_user_subscriptions_with_time(self, user_hash):
        """Get user's subscriptions with timing information"""
        cursor = self.get_db().cursor()
        cursor.execute(
            """
            SELECT
                f.name,
                f.url,
                u.last_update,
                COALESCE(u.schedule_hours, 24) as schedule_hours
            FROM feeds f
            JOIN subscriptions s ON f.id = s.feed_id
            JOIN users u ON s.user_hash = u.hash
            WHERE u.hash = ?
            ORDER BY f.name
        """,
            (user_hash,),
        )

        results = []
        for row in cursor.fetchall():
            name, url, last_update_str, schedule_hours = row

            # Convert last_update to timezone-aware datetime
            last_update = None
            if last_update_str:
                try:
                    last_update = datetime.fromisoformat(
                        last_update_str.replace(" ", "T")
                    ).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            results.append((name, url, last_update, schedule_hours))

        return results

    def backup_database(self):
        """Create a backup of the database"""
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            backup_path = os.path.join(
                self.backup_dir,
                f"feed_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.db",
            )
            with sqlite3.connect(backup_path) as backup_db:
                self.get_db().backup(backup_db)
            return backup_path
        except Exception as e:
            print(f"Backup error: {e}")
            return None

    def restore_database(self, backup_path):
        """Restore database from backup"""
        try:
            if not os.path.exists(backup_path):
                print("Backup file does not exist")
                return False

            backup_dir = os.path.abspath("backups")
            backup_path = os.path.abspath(backup_path)

            if not backup_path.startswith(backup_dir):
                print("Invalid backup location")
                return False

            with sqlite3.connect(backup_path):  # backup_db variable is not used
                self.get_db().backup(self.get_db())
            return True
        except Exception as e:
            print(f"Restore error: {e}")
            return False

    def get_stats(self):
        """Get bot statistics"""
        cursor = self.get_db().cursor()
        stats = {}

        # Get user count
        cursor.execute("SELECT COUNT(DISTINCT hash) FROM users WHERE active = 1")
        stats["users"] = cursor.fetchone()[0]

        # Get feed count
        cursor.execute("SELECT COUNT(*) FROM feeds")
        stats["feeds"] = cursor.fetchone()[0]

        # Get article count
        cursor.execute("SELECT COUNT(*) FROM sent_items")
        stats["articles"] = cursor.fetchone()[0]

        # Get database size
        cursor.execute("PRAGMA page_count")
        page_count = cursor.fetchone()[0]
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        stats["db_size"] = round(
            (page_count * page_size) / (1024 * 1024), 2
        )  # Size in MB

        return stats

    def get_db_version(self):
        """Get current database schema version"""
        cursor = self.get_db().cursor()
        cursor.execute("SELECT MAX(version) FROM schema_version")
        version = cursor.fetchone()[0]
        return version or 0
