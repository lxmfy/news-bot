import os
from datetime import datetime, timezone

import pytz
from lxmfy import LXMFBot
from lxmfy.scheduler import TaskScheduler

from .feed import FeedManager


class NewsBot:
    VERSION = "0.3.0"
    DESCRIPTION = "LXMFy News Bot\nUsing RSS and trafilatura to fetch full-text"

    def __init__(self):
        # Get configuration from environment variables with platform-specific defaults
        home = os.path.expanduser("~")

        # Platform-specific reticulum paths
        if os.name == "nt":  # Windows
            reticulum_dir = os.path.join(os.getenv("APPDATA"), "reticulum")
        elif os.name == "darwin":  # macOS
            reticulum_dir = os.path.join(
                home, "Library", "Application Support", "reticulum"
            )
        else:  # Linux and others
            reticulum_dir = os.path.join(home, ".reticulum")

        os.makedirs(reticulum_dir, exist_ok=True)

        # Initialize LXMFBot with environment variables
        self.bot = LXMFBot(
            name=os.getenv("BOT_NAME", f"LXMFy News Bot v{self.VERSION}"),
            announce=int(os.getenv("BOT_ANNOUNCE", "600")),
            announce_immediately=os.getenv("BOT_ANNOUNCE_IMMEDIATE", "false").lower()
            == "true",
            admins=set(os.getenv("BOT_ADMINS", "").split(","))
            if os.getenv("BOT_ADMINS")
            else set(),
            command_prefix=os.getenv("BOT_PREFIX", ""),
            hot_reloading=os.getenv("BOT_HOT_RELOAD", "false").lower() == "true",
            rate_limit=int(os.getenv("BOT_RATE_LIMIT", "8")),
            cooldown=int(os.getenv("BOT_COOLDOWN", "1")),
            max_warnings=int(os.getenv("BOT_MAX_WARNINGS", "3")),
            warning_timeout=int(os.getenv("BOT_WARNING_TIMEOUT", "300")),
            permissions_enabled=os.getenv("BOT_PERMISSIONS_ENABLED", "false").lower()
            == "true",
            storage_type=os.getenv("BOT_STORAGE_TYPE", "sqlite"),
            storage_path=os.getenv(
                "BOT_STORAGE_PATH", f"{os.getenv('DATA_DIR', './app/data')}/bot.db"
            ),
            first_message_enabled=os.getenv("BOT_FIRST_MESSAGE_ENABLED", "true").lower()
            == "true",
            event_logging_enabled=os.getenv(
                "BOT_EVENT_LOGGING_ENABLED", "false"
            ).lower()
            == "true",
            max_logged_events=int(os.getenv("BOT_MAX_LOGGED_EVENTS", "1000")),
            event_middleware_enabled=os.getenv(
                "BOT_EVENT_MIDDLEWARE_ENABLED", "false"
            ).lower()
            == "true",
            announce_enabled=os.getenv("BOT_ANNOUNCE_ENABLED", "true").lower()
            == "true",
        )

        self.feed_manager = FeedManager()
        self.setup_commands()

        # Initialize and start the task scheduler for periodic feed checking
        self.scheduler = TaskScheduler(self.bot)

        @self.scheduler.schedule(name="feed_check", cron_expr="*/5 * * * *")
        def scheduled_feed_check():
            self._run_feed_cycle()

        self.scheduler.start()

    def setup_commands(self):
        # Admin commands
        @self.bot.command(
            name="backup",
            description="Backup the database",
            category="Admin",
            admin_only=True,
        )
        def backup_db(ctx):
            if not ctx.is_admin:
                ctx.reply("This command is only available to administrators")
                return

            backup_path = self.feed_manager.backup_database()
            if backup_path:
                ctx.reply(f"Database backed up to: {backup_path}")
            else:
                ctx.reply("Backup failed")

        @self.bot.command(
            name="restore",
            description="Restore database from backup",
            usage="restore <backup_file>",
            category="Admin",
            admin_only=True,
        )
        def restore_db(ctx):
            if not ctx.is_admin:
                ctx.reply("This command is only available to administrators")
                return

            if not ctx.args:
                ctx.reply("Please specify backup file")
                return

            backup_path = ctx.args[0]
            if self.feed_manager.restore_database(backup_path):
                ctx.reply("Database restored successfully")
            else:
                ctx.reply("Restore failed")

        @self.bot.command(
            name="dbversion",
            description="Show database schema version",
            category="Admin",
            admin_only=True,
        )
        def db_version(ctx):
            version = self.feed_manager.get_db_version()
            ctx.reply(f"Database schema version: {version}")

        @self.bot.command(
            name="stats",
            description="Show bot statistics",
            category="Admin",
            admin_only=True,
        )
        def show_stats(ctx):
            stats = self.feed_manager.get_stats()
            ctx.reply(f"""Bot Statistics:
Total users: {stats["users"]}
Total feeds: {stats["feeds"]}
Total articles: {stats["articles"]}
Database size: {stats["db_size"]}MB""")

        # Regular user commands remain unchanged
        @self.bot.command(
            name="version",
            description="Show bot version and information",
            category="System",
        )
        def version(ctx):
            ctx.reply(f"""Version {self.VERSION} - {self.DESCRIPTION}

Type 'help' for available commands
Type 'feeds' to see available feed categories""")

        @self.bot.command(
            name="feed",
            description="Preview a feed (shows latest 5 entries)",
            usage="feed <feed_url>",
        )
        def preview_feed(ctx):
            if not ctx.args:
                ctx.reply("Usage: feed <feed_url>")
                return

            feed_url = ctx.args[0]
            feed_info, error = self.feed_manager.preview_feed(feed_url)

            if error:
                ctx.reply(f"Error: {error}")
                return

            ctx.reply(f"""Feed Preview: {feed_info["title"]}

Description: {feed_info["description"]}
URL: {feed_info["link"]}

Showing latest 5 entries:""")

            for entry in feed_info["entries"]:
                message = f"""
{entry["title"]}
Published: {entry["published"]}

{entry["description"]}

Link: {entry["link"]}"""

                ctx.reply(message, title=f"Preview: {feed_info['title']}")

        @self.bot.command(
            name="subscribe",
            description="Subscribe to one or more RSS feeds",
            usage="subscribe <feed_url> [name] [feed_url2] [name2] ...",
            examples=[
                "subscribe https://example.com/feed",
                "subscribe https://example.com/feed My Feed",
                "subscribe https://site1.com/feed Blog1 https://site2.com/feed Blog2",
            ],
        )
        def subscribe(ctx):
            if len(ctx.args) < 1:
                ctx.reply("Usage: subscribe <feed_url> [name] [feed_url2] [name2] ...")
                return

            # If first argument isn't a URL, treat as category or named feeds
            first_arg = ctx.args[0]
            if not first_arg.startswith(("http://", "https://", "feed://")):
                category = " ".join(ctx.args).lower()
                feeds = self.feed_manager.parse_feed_input(category)
                if not feeds:
                    categories = list(
                        self.feed_manager.feed_config.get("groups", {}).keys()
                    )
                    ctx.reply(
                        f"Category '{category}' not found. Available categories: {', '.join(categories)}"
                    )
                    return
                success, results = self.feed_manager.add_subscription(
                    ctx.sender,
                    [f["url"] for f in feeds],
                    [f["name"] for f in feeds],
                )
                response = []
                for url, ok, msg in results:
                    if ok:
                        response.append(f"✓ Subscribed to: {msg}")
                    else:
                        response.append(f"✗ Failed to subscribe to {url}: {msg}")
                ctx.reply("\n".join(response))
                return

            urls = []
            names = []
            current_url = None

            for arg in ctx.args:
                if arg.startswith(("http://", "https://", "feed://")):
                    if current_url:
                        urls.append(current_url)
                        names.append(" ".join(names))
                        names = []
                    current_url = arg
                elif current_url:
                    names.append(arg)

            if current_url:
                urls.append(current_url)
                names.append(" ".join(names) if names else current_url)

            success, results = self.feed_manager.add_subscription(
                ctx.sender, urls, names
            )

            response = []
            for url, success, message in results:
                if success:
                    response.append(f"✓ Subscribed to: {message}")
                else:
                    response.append(f"✗ Failed to subscribe to {url}: {message}")

            ctx.reply("\n".join(response))

        @self.bot.command(
            name="unsubscribe",
            description="Unsubscribe from a feed",
            usage="unsubscribe <feed_name>",
        )
        def unsubscribe(ctx):
            if not ctx.args:
                ctx.reply("Usage: unsubscribe <feed_name>")
                return

            name = " ".join(ctx.args)
            if self.feed_manager.remove_subscription(ctx.sender, name):
                ctx.reply(f"Unsubscribed from: {name}")
            else:
                ctx.reply(f"You're not subscribed to: {name}")

        @self.bot.command(
            name="list", description="List your subscribed feeds and next update times"
        )
        def list_feeds(ctx):
            feeds = self.feed_manager.get_user_subscriptions_with_time(ctx.sender)
            if feeds:
                response = "Your subscriptions:\n"
                now = datetime.now(timezone.utc)

                for name, url, last_update, schedule_hours in feeds:
                    if last_update:
                        hours_since = (now - last_update).total_seconds() / 3600
                        hours_remaining = schedule_hours - hours_since

                        if hours_remaining <= 0:
                            time_info = "Update pending..."
                        else:
                            if hours_remaining > 24:
                                days = hours_remaining / 24
                                time_info = f"Next update in {days:.1f} days"
                            elif hours_remaining < 1:
                                mins = hours_remaining * 60
                                time_info = f"Next update in {mins:.0f} minutes"
                            else:
                                time_info = (
                                    f"Next update in {hours_remaining:.1f} hours"
                                )
                    else:
                        time_info = "First update pending"

                    response += f"- {name}\n  └─ {time_info}\n"
            else:
                response = "You have no subscriptions"

            ctx.reply(response)

        @self.bot.command(
            name="timezone",
            description="Set your timezone",
            usage="timezone <timezone>",
            examples=["timezone UTC", "timezone America/New_York"],
        )
        def set_timezone(ctx):
            if not ctx.args:
                ctx.reply("Usage: timezone <timezone>")
                return

            tz = " ".join(ctx.args)
            try:
                pytz.timezone(tz)
                self.feed_manager.update_user_timezone(ctx.sender, tz)
                ctx.reply(f"Timezone set to: {tz}")
            except Exception:
                ctx.reply(
                    "Invalid timezone. Use format like 'UTC' or 'America/New_York'"
                )

        @self.bot.command(
            name="time",
            description="Set daily update time",
            usage="time <HH:MM>",
            examples=["time 09:00"],
        )
        def set_time(ctx):
            if not ctx.args or not ctx.args[0]:
                ctx.reply("Usage: time HH:MM")
                return

            try:
                # Validate time format to HH:MM. The underlying update_user_time
                # function uses parameterized queries, preventing SQL injection.
                time = datetime.strptime(ctx.args[0], "%H:%M").strftime("%H:%M")
                self.feed_manager.update_user_time(ctx.sender, time)
                ctx.reply(f"Update time set to: {time}")
            except ValueError:
                ctx.reply("Invalid time format. Use HH:MM (24-hour format)")

        @self.bot.command(
            name="default",
            description="Subscribe to default feeds or a specific category",
            usage="default [category]",
            examples=[
                "default",
                "default news",
                "default military",
                "default cybersecurity",
                "default science",
            ],
        )
        def default_feeds(ctx):
            category = " ".join(ctx.args).lower() if ctx.args else "default"
            feeds = self.feed_manager.parse_feed_input(category)

            if not feeds:
                categories = list(self.feed_manager.feed_config["groups"].keys())
                ctx.reply(
                    f"Available categories: {', '.join(categories)}\nUse: default <category>"
                )
                return

            success, results = self.feed_manager.add_subscription(
                ctx.sender, [f["url"] for f in feeds], [f["name"] for f in feeds]
            )

            response = []
            for url, success, message in results:
                if success:
                    response.append(f"✓ Subscribed to: {message}")
                else:
                    response.append(f"✗ Failed to subscribe to {url}: {message}")

            ctx.reply("\n".join(response))

        @self.bot.command(
            name="feeds",
            description="List available feeds and categories",
            usage="feeds [category]",
        )
        def list_available_feeds(ctx):
            if not ctx.args:
                # List all categories
                categories = list(self.feed_manager.feed_config["groups"].keys())
                named_feeds = list(self.feed_manager.feed_config["feeds"].keys())

                response = "Available categories:\n"
                response += "\n".join(f"- {cat}" for cat in categories)
                response += "\n\nNamed feeds:\n"
                response += "\n".join(f"- {feed}" for feed in named_feeds)
                response += "\n\nUse: feeds <category> to see feeds in a category"

            else:
                category = " ".join(ctx.args).lower()
                feeds = self.feed_manager.parse_feed_input(category)

                if not feeds:
                    ctx.reply(f"Category or feed '{category}' not found")
                    return

                response = f"Feeds in {category}:\n"
                response += "\n".join(f"- {f['name']}" for f in feeds)

            ctx.reply(response)

        @self.bot.command(
            name="schedule",
            description="Set update schedule in hours (1-72)",
            usage="schedule <hours>",
            examples=["schedule 6", "schedule 12", "schedule 24"],
        )
        def set_schedule(ctx):
            if not ctx.args or not ctx.args[0].isdigit():
                ctx.reply("Usage: schedule <hours> (1-72)")
                return

            hours = int(ctx.args[0])
            if hours < 1 or hours > 72:
                ctx.reply("Schedule must be between 1 and 72 hours")
                return

            self.feed_manager.update_user_schedule(ctx.sender, hours)
            ctx.reply(f"Updates scheduled every {hours} hours")

    def _run_feed_cycle(self):
        try:
            now = datetime.now(timezone.utc)
            for (
                user_hash,
                tz,
                update_time,
                feed_id,
                feed_url,
                feed_name,
                schedule_hours,
                last_update,
            ) in self.feed_manager.get_active_subscriptions():
                # Skip if no last update (new user)
                if not last_update:
                    self.send_feed_updates(user_hash, feed_id, feed_url, feed_name)
                    continue

                # last_update should already be timezone-aware
                if not last_update.tzinfo:
                    last_update = last_update.replace(tzinfo=timezone.utc)

                # Calculate hours since last update
                hours_since_update = (now - last_update).total_seconds() / 3600

                # Check if it's time for an update
                if hours_since_update >= (schedule_hours or 24):
                    self.send_feed_updates(user_hash, feed_id, feed_url, feed_name)
        except Exception as e:
            print(f"Scheduled feed check error: {str(e)}")

    def send_feed_updates(self, user_hash, feed_id, feed_url, feed_name):
        try:
            entries = self.feed_manager.process_feed(feed_url)

            updates_sent = False
            for entry in entries:
                if not self.feed_manager.is_sent(feed_id, entry["id"]):
                    message = f"""
{feed_name}

{entry["title"]}

{entry["description"]}

Link: {entry["link"]}
"""
                    self.bot.send(user_hash, message, title=f"News: {feed_name}")
                    self.feed_manager.mark_sent(feed_id, entry["id"])
                    updates_sent = True

            if updates_sent:
                cursor = self.feed_manager.get_db().cursor()
                cursor.execute(
                    """
                    UPDATE users
                    SET last_update = ?
                    WHERE hash = ?
                """,
                    (datetime.now(timezone.utc), user_hash),
                )
                self.feed_manager.get_db().commit()

        except Exception as e:
            print(f"Error sending feed updates: {str(e)}")

    def run(self):
        self.bot.run()


def main():
    bot = NewsBot()
    bot.run()


if __name__ == "__main__":
    main()
