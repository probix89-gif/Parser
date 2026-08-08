"""Telegram bot handlers — commands, file upload, result delivery."""

from __future__ import annotations

import asyncio
import re
from loguru import logger

from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.bot.batch_manager import BatchManager
from src.bot.formatter import format_results
from src.core.fetch_engine import FetchEngine
from src.core.filters import URLFilter
from src.core.parser import YahooSerpsParser
from src.core.proxy_pool import ProxyPool
from src.core.query_builder import YahooQueryBuilder
from src.models.config import BotConfig
from src.utils.tls_rotation import TLSRotator
from src.utils.ua_rotation import UserAgentRotator


class DorkBot:
    """Telegram bot for mass dork parsing with high-throughput scraping."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.proxy_pool = ProxyPool(
            config.proxy_list_path,
            max_failures=config.proxy_max_failures,
            recheck_interval=config.proxy_health_check_interval,
        )
        self.tls = TLSRotator()
        self.ua = UserAgentRotator(config.user_agents_path)
        self.url_filter = URLFilter(config.blocklist_path)
        self.query_builder = YahooQueryBuilder()
        self.batch_manager = BatchManager(
            config, self.proxy_pool, self.tls, self.ua, self.url_filter
        )

    async def start(self) -> None:
        """Start the bot — health check proxies, register handlers, begin polling."""
        await self.proxy_pool.health_check()
        self.proxy_pool.start_background_probing()

        app = Application.builder().token(self.config.token).build()

        # Commands
        app.add_handler(CommandHandler("dork", self._dork))
        app.add_handler(CommandHandler("mass", self._mass_info))
        app.add_handler(CommandHandler("status", self._status))
        app.add_handler(CommandHandler("help", self._help))

        # File upload handler (.txt files only)
        app.add_handler(
            MessageHandler(
                filters.Document.FileExtension("txt") & ~filters.COMMAND,
                self._handle_dork_file,
            )
        )

        logger.info("Bot started — ready for mass dork processing")

        # python-telegram-bot's run_polling() manages its own event loop.
        # Since main.py already calls asyncio.run(bot.start()), use the
        # asynchronous application lifecycle instead.
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

        try:
            # Keep the existing asyncio event loop alive while polling.
            await asyncio.Event().wait()
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

    # ── Single Dork ──────────────────────────────────────────────

    async def _dork(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Single dork query mode. Supports --pages N option."""
        if not ctx.args:
            await update.message.reply_text(
                "Usage: /dork <yahoo dork query> [--pages N]\n"
                "  --pages N: results pages to scrape (1-60, default: 10)\n\n"
                "For mass mode: upload a .txt file with one dork per line\n"
                "  Add caption: --pages N to override page count"
            )
            return

        dork, pages = self.parse_args(ctx.args)
        await update.message.reply_text(f"🔍 Searching ({pages} pages): {dork}")

        urls = self.query_builder.build(dork, pages=pages)
        engine = FetchEngine(
            self.proxy_pool,
            self.tls,
            self.ua,
            max_concurrency=self.config.max_concurrency,
            timeout=self.config.request_timeout,
            rate_limit_per_sec=self.config.rate_limit_per_sec,
        )
        pages_html = await engine.fetch_all(urls)
        all_urls: list[str] = []
        for html in pages_html:
            if html:
                all_urls.extend(YahooSerpsParser.parse(html))
        clean_urls = self.url_filter.filter(all_urls)

        if not clean_urls:
            await update.message.reply_text("No results found.")
            return

        await self._send_results(update, clean_urls, dork)

    # ── Mass Dork (File Upload) ──────────────────────────────────

    async def _handle_dork_file(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle .txt file upload — mass dork processing."""
        doc = update.message.document
        if not doc:
            return

        file_name = doc.file_name or "unknown.txt"
        if not file_name.endswith(".txt"):
            await update.message.reply_text("⚠️ Please upload a .txt file.")
            return

        await update.message.reply_text(
            f"📥 Received: {file_name}\n⏳ Downloading dork list..."
        )

        # Download file
        telegram_file = await doc.get_file()
        content_bytes = await telegram_file.download_as_bytearray()
        content_str = content_bytes.decode("utf-8", errors="replace")

        # Parse --pages from caption
        caption = update.message.caption or ""
        pages = self.parse_pages_from_caption(caption)

        # Parse dorks
        dorks = self.batch_manager.parse_dork_file(content_str)
        if not dorks:
            await update.message.reply_text("⚠️ No valid dorks found in file.")
            return

        await update.message.reply_text(
            f"📋 Parsed {len(dorks)} dork queries\n"
            f"🚀 Starting mass processing...\n"
            f"📄 Pages per dork: {pages}\n"
            f"⚙️ Concurrency: {self.config.max_dork_concurrency} parallel dorks\n"
            f"🔒 TLS rotation + proxy rotation active"
        )

        # Progress callback — shows throughput metrics
        async def send_progress(progress, metrics):
            await update.message.reply_text(
                f"📊 Progress: {progress.completed}/{progress.total} "
                f"({progress.pct:.0f}%)\n"
                f"⚡ {metrics.urls_per_sec:.0f} URLs/sec | "
                f"🔄 {metrics.req_per_sec:.0f} req/sec\n"
                f"✅ Success: {metrics.success_rate:.0%}\n"
                f"🔗 Total URLs: {progress.total_urls}"
            )

        # Process batch — FULL THROTTLE with user-selected pages
        clean_urls, progress = await self.batch_manager.process_batch(
            dorks, send_progress=send_progress, pages_override=pages
        )

        # Final summary with throughput stats
        elapsed = progress.elapsed_sec
        await update.message.reply_text(
            f"✅ Batch complete!\n"
            f"📊 Dorks: {progress.completed}/{progress.total}\n"
            f"❌ Failed: {progress.failed}\n"
            f"🔗 Unique URLs: {len(clean_urls)}\n"
            f"⚡ Avg: {progress.urls_per_sec:.0f} URLs/sec\n"
            f"⏱️ Time: {elapsed:.1f}s"
        )

        if not clean_urls:
            await update.message.reply_text("No results found.")
            return

        # Send results as .txt file + summary message
        await self._send_results(
            update, clean_urls, f"Mass batch ({len(dorks)} dorks)"
        )

    # ── Result Delivery ──────────────────────────────────────────

    async def _send_results(
        self, update: Update, urls: list[str], label: str
    ) -> None:
        """Send results both as Telegram messages and a downloadable .txt file."""
        # 1. Send summary messages (first 200 URLs, paginated, max 4 messages)
        messages = format_results(
            urls, label, per_page=self.config.results_per_page
        )
        for msg in messages[:4]:
            await update.message.reply_text(
                msg, disable_web_page_preview=True
            )

        if len(urls) > 200:
            await update.message.reply_text(
                "📄 Showing first 200 URLs. Full results in the .txt file below 👇"
            )

        # 2. Export to .txt and send as document
        output_path = self.batch_manager.export_to_file(urls)
        with open(output_path, "rb") as f:
            await update.message.reply_document(
                document=InputFile(
                    f, filename=f"dork_results_{len(urls)}_urls.txt"
                ),
                caption=f"🎯 {len(urls)} unique URLs from: {label}",
            )

    # ── Info Commands ───────────────────────────────────────────

    async def _mass_info(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show mass dork mode instructions."""
        await update.message.reply_text(
            "📋 Mass Dork Mode — HIGH THROUGHPUT:\n\n"
            "1. Create a .txt file with one dork query per line\n"
            "2. Upload it to this chat\n"
            "   • Add caption: --pages N to set pages per dork (1-60, default: 10)\n"
            "3. Bot processes all dorks at MAX SPEED (no rate limit)\n"
            f"4. Target: {self.config.target_urls_per_sec} URLs/sec\n"
            "5. Get results as messages + downloadable .txt file\n\n"
            "Throughput config:\n"
            f"• {self.config.max_concurrency} concurrent HTTP requests\n"
            f"• {self.config.max_dork_concurrency} dorks processed in parallel\n"
            "• Pages per dork: 1-60 (user selectable)\n"
            "• Rate limiter: DISABLED\n"
            f"• Proxies: {self.proxy_pool.count} healthy "
            f"({self.proxy_pool.total} total)\n\n"
            f"Limit: {BatchManager.MAX_DORKS} dorks per batch\n\n"
            "Usage examples:\n"
            '  /dork site:example.com "gift card" --pages 30\n'
            "  /dork inurl:login --pages 60\n"
            "  Upload .txt with caption: --pages 45\n\n"
            "Dork format in .txt file:\n"
            'site:example.com "gift card"\n'
            "inurl:login site:*.com\n"
            'intitle:"index of" "parent directory"'
        )

    async def _status(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show bot status, proxy health, and throughput config."""
        rate_status = (
            "ON" if self.config.rate_limit_per_sec > 0 else "OFF 🚀"
        )
        await update.message.reply_text(
            f"🟢 Status:\n"
            f"Proxies: {self.proxy_pool.count} healthy / "
            f"{self.proxy_pool.total} total\n"
            f"Blocklist: {self.url_filter.blocklist_count} domains\n"
            f"─── Throughput ───\n"
            f"Concurrency: {self.config.max_concurrency} requests\n"
            f"Dork concurrency: {self.config.max_dork_concurrency} dorks\n"
            f"Pages per dork: {self.config.max_pages} (max 60)\n"
            f"Rate limiter: {rate_status}\n"
            f"Target: {self.config.target_urls_per_sec} URLs/sec\n"
            f"Max dorks per batch: {BatchManager.MAX_DORKS}"
        )

    async def _help(
        self, update: Update, ctx: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show help message."""
        await update.message.reply_text(
            "📋 Commands:\n"
            "/dork <query> [--pages N] — Single dork search "
            "(N=1-60, default 10)\n"
            "/mass — Info on mass dork mode (file upload)\n"
            "/status — Check bot + proxy health\n"
            "/help — This message\n\n"
            "📁 Upload a .txt file (one dork per line) for mass processing\n"
            "   Add caption: --pages N to set pages per dork"
        )

    # ── Argument Parsing ────────────────────────────────────────

    @staticmethod
    def parse_args(args: list[str]) -> tuple[str, int]:
        """Parse /dork command args. Extracts --pages N if present.

        Returns (dork_query, pages). Pages clamped to 1-60.
        """
        pages = 10  # default
        dork_parts: list[str] = []
        i = 0
        while i < len(args):
            if args[i] == "--pages" and i + 1 < len(args):
                try:
                    pages = max(1, min(60, int(args[i + 1])))
                    i += 2
                    continue
                except ValueError:
                    pass
            dork_parts.append(args[i])
            i += 1
        return " ".join(dork_parts), pages

    @staticmethod
    def parse_pages_from_caption(caption: str) -> int:
        """Extract --pages N from file upload caption. Defaults to 10."""
        m = re.search(r"--pages\s+(\d+)", caption)
        if m:
            return max(1, min(60, int(m.group(1))))
        return 10
