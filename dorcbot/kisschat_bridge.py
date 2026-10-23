"""Authenticated HTTP bridge for KISSChat messages addressed to DORCbot."""

import hmac
import logging
import re
import sqlite3
from pathlib import Path

from aiohttp import web
import discord

logger = logging.getLogger("dorcbot.kisschat")
CHANNEL_NAME = re.compile(r"^#[A-Za-z0-9_-]{1,31}$")
ORIGIN = re.compile(r"^[0-9a-fA-F]{32}$")


class KissChatBridge:
    def __init__(self, client, db_path, token, host="0.0.0.0", port=8765):
        self.client = client
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.token = token
        self.host = host
        self.port = port
        self.runner = None
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS kisschat_deliveries (
                origin TEXT NOT NULL, seq INTEGER NOT NULL, channel TEXT NOT NULL,
                discord_message_id INTEGER, status TEXT NOT NULL,
                PRIMARY KEY(origin,seq))""")

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=10)

    async def start(self):
        if not self.token:
            logger.info("KISSChat bridge disabled; KISSCHAT_BRIDGE_TOKEN is unset")
            return
        with self._connect() as db:
            db.execute("UPDATE kisschat_deliveries SET status='failed' WHERE status='sending'")
        app = web.Application(client_max_size=16 * 1024)
        app.router.add_post("/kisschat/message", self.handle_message)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info("KISSChat bridge listening on %s:%s", self.host, self.port)

    async def close(self):
        if self.runner:
            await self.runner.cleanup()

    async def handle_message(self, request):
        if not self.client.is_ready():
            raise web.HTTPServiceUnavailable(text="Discord client is not ready")
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, "Bearer " + self.token):
            raise web.HTTPUnauthorized()
        try:
            payload = await request.json()
        except (ValueError, web.HTTPException):
            raise web.HTTPBadRequest(text="Expected JSON")
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest(text="Expected a JSON object")
        origin = payload.get("origin")
        seq = payload.get("seq")
        channel = payload.get("channel")
        nick = payload.get("nick")
        body = payload.get("body")
        if (not isinstance(origin, str) or not ORIGIN.fullmatch(origin) or
                type(seq) is not int or not 1 <= seq <= 0xFFFFFFFF or
                not isinstance(channel, str) or not CHANNEL_NAME.fullmatch(channel) or
                not isinstance(nick, str) or not 1 <= len(nick.encode("utf-8")) <= 16 or
                not isinstance(body, str) or not 1 <= len(body.encode("utf-8")) <= 4096):
            raise web.HTTPBadRequest(text="Invalid KISSChat message")
        origin = origin.lower()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status FROM kisschat_deliveries WHERE origin=? AND seq=?",
                (origin, seq),
            ).fetchone()
            if row and row[0] == "sent":
                return web.json_response({"status": "sent", "duplicate": True})
            if row and row[0] == "sending":
                raise web.HTTPServiceUnavailable(text="Delivery is in progress")
            db.execute(
                "INSERT INTO kisschat_deliveries(origin,seq,channel,status) VALUES(?,?,?,'sending') "
                "ON CONFLICT(origin,seq) DO UPDATE SET channel=excluded.channel,status='sending'",
                (origin, seq, channel),
            )

        discord_channel = self._find_channel(channel[1:])
        if discord_channel is None:
            self._mark_failed(origin, seq)
            raise web.HTTPNotFound(text="No unique Discord text channel matches this KISSChat channel")
        try:
            embed = discord.Embed(title=f"KISSChat · {channel}", description=body)
            embed.set_author(name=nick)
            sent = await discord_channel.send(
                embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            self._mark_failed(origin, seq)
            logger.exception("Could not post KISSChat message %s:%s", origin, seq)
            raise web.HTTPServiceUnavailable(text="Discord delivery failed")
        with self._connect() as db:
            db.execute(
                "UPDATE kisschat_deliveries SET status='sent',discord_message_id=? "
                "WHERE origin=? AND seq=?", (sent.id, origin, seq),
            )
        return web.json_response({"status": "sent", "duplicate": False})

    def _find_channel(self, name):
        matches = [channel for channel in self.client.get_all_channels()
                   if isinstance(channel, discord.TextChannel) and
                   channel.name.casefold() == name.casefold()]
        return matches[0] if len(matches) == 1 else None

    def _mark_failed(self, origin, seq):
        with self._connect() as db:
            db.execute("UPDATE kisschat_deliveries SET status='failed' WHERE origin=? AND seq=?",
                       (origin, seq))
