"""ServerStatus — persistent Discord embed showing live server info."""

from __future__ import annotations

import datetime
import json
import math
from collections import deque
from urllib.parse import quote

import discord

from squadpy.plugin import Plugin, on_event, periodic


class ServerStatus(Plugin):
    name = "Server Status"
    description = "Live server status embed in Discord"
    requires = ["rcon", "discord"]

    async def on_enable(self):
        self._message = None
        self._tick_rate = 0.0
        self._current_map = None
        self._current_layer = None
        self._factions = None
        self._trend_samples: deque[tuple[datetime.datetime, int, float]] = deque()

        channel_id = self._channel_id()
        if channel_id:
            embed = self._build_embed(
                player_count=0,
                squad_count=0,
                level="Loading...",
                layer="Loading...",
                factions="",
                next_map=None,
                tick_rate=self._tick_rate,
                graph_url="",
            )
            self._message = await self.discord.send(channel_id, embed=embed)

    @periodic(seconds=60)
    async def update_status(self):
        channel_id = self._channel_id()
        if not channel_id:
            return

        players = await self.rcon.list_players()
        current_map = await self.rcon.show_current_map()
        next_map = await self.rcon.show_next_map()

        if current_map:
            self._current_map = current_map.level
            self._current_layer = current_map.layer
            if current_map.factions:
                self._factions = current_map.factions

        level = self._current_map or "Unknown"
        layer = self._current_layer or "Unknown"
        factions = self._factions or ""
        squads_in = {player.squad_id for player in players if player.squad_id != 0}
        player_count = len(players)
        squad_count = len(squads_in)
        tick_rate = self._tick_rate

        self._record_trend_sample(
            at=self._now(),
            player_count=player_count,
            tick_rate=tick_rate,
        )
        graph_url = self._build_graph_url()

        embed = self._build_embed(
            player_count=player_count,
            squad_count=squad_count,
            level=level,
            layer=layer,
            factions=factions,
            next_map=next_map,
            tick_rate=tick_rate,
            graph_url=graph_url,
        )

        if self._message:
            try:
                self._message = await self.discord.edit_message(self._message, embed=embed)
                return
            except Exception:
                self.logger.warning("Failed to edit status message, posting new one")
                self._message = None

        self._message = await self.discord.send(channel_id, embed=embed)

    @on_event("server_tick_rate")
    async def cache_tick_rate(self, event):
        self._tick_rate = event.tick_rate

    @on_event("new_game")
    async def cache_map(self, event):
        self._current_map = getattr(event, "map_classname", None)
        self._current_layer = getattr(event, "layer_classname", None)

    async def on_disable(self):
        if self._message:
            try:
                embed = discord.Embed(
                    title="Server Status",
                    description="Offline",
                    color=discord.Color.dark_grey(),
                    timestamp=self._now(),
                )
                await self.discord.edit_message(self._message, embed=embed)
            except Exception:
                pass

    def _build_embed(
        self,
        *,
        player_count: int,
        squad_count: int,
        level: str,
        layer: str,
        factions: str,
        next_map,
        tick_rate: float,
        graph_url: str,
    ):
        embed = discord.Embed(
            title="Server Status",
            color=discord.Color.green(),
            timestamp=self._now(),
        )
        embed.add_field(name="Map", value=level, inline=True)
        embed.add_field(name="Layer", value=layer, inline=True)
        if factions:
            embed.add_field(name="Factions", value=factions, inline=True)
        embed.add_field(name="Players", value=str(player_count), inline=True)
        embed.add_field(name="Squads", value=str(squad_count), inline=True)
        embed.add_field(name="Tick Rate", value=f"{tick_rate:.1f}", inline=True)
        if next_map:
            embed.add_field(name="Next Map", value=f"{next_map.level} / {next_map.layer}", inline=False)
        else:
            embed.add_field(name="Next Map", value="Not set (voting)", inline=False)
        if graph_url:
            embed.set_image(url=graph_url)
        return embed

    def _record_trend_sample(self, *, at: datetime.datetime, player_count: int, tick_rate: float) -> None:
        self._trend_samples.append((at, player_count, tick_rate))
        cutoff = at - datetime.timedelta(minutes=self._graph_window_minutes())
        while self._trend_samples and self._trend_samples[0][0] < cutoff:
            self._trend_samples.popleft()

    def _build_graph_url(self) -> str:
        if not self._graph_enabled() or not self._trend_samples:
            return ""

        samples = self._sampled_trend_points()
        labels = [stamp.strftime("%H:%M") for stamp, _, _ in samples]
        player_series = [player_count for _, player_count, _ in samples]
        tick_rate_series = [round(tick_rate, 2) for _, _, tick_rate in samples]

        chart_config = {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": "Players",
                        "data": player_series,
                        "borderColor": "#10b981",
                        "tension": 0.2,
                        "pointRadius": 1,
                        "yAxisID": "y_players",
                    },
                    {
                        "label": "Tick Rate",
                        "data": tick_rate_series,
                        "borderColor": "#60a5fa",
                        "tension": 0.2,
                        "pointRadius": 1,
                        "yAxisID": "y_tick",
                    },
                ],
            },
            "options": {
                "animation": False,
                "plugins": {
                    "legend": {"display": True, "position": "top"},
                    "title": {
                        "display": True,
                        "text": f"Last {self._graph_window_minutes()} min",
                    },
                },
                "scales": {
                    "y_players": {
                        "type": "linear",
                        "position": "left",
                        "beginAtZero": True,
                    },
                    "y_tick": {
                        "type": "linear",
                        "position": "right",
                        "beginAtZero": True,
                        "grid": {"drawOnChartArea": False},
                    },
                },
            },
        }
        encoded = quote(json.dumps(chart_config, separators=(",", ":")), safe="")
        width = self._positive_int(self.config.get("graph_width", 900), 900)
        height = self._positive_int(self.config.get("graph_height", 340), 340)
        return (
            "https://quickchart.io/chart"
            f"?width={width}&height={height}&devicePixelRatio=2&format=png&c={encoded}"
        )

    def _sampled_trend_points(self) -> list[tuple[datetime.datetime, int, float]]:
        samples = list(self._trend_samples)
        max_points = self._max_graph_points()
        if len(samples) <= max_points:
            return samples

        step = math.ceil(len(samples) / max_points)
        sampled = samples[::step]
        if sampled[-1] != samples[-1]:
            sampled.append(samples[-1])
        return sampled

    def _graph_enabled(self) -> bool:
        return bool(self.config.get("graph_enabled", True))

    def _graph_window_minutes(self) -> int:
        window = self._positive_int(self.config.get("graph_window_minutes", 60), 60)
        if window < 10:
            return 10
        if window > 240:
            return 240
        return window

    def _max_graph_points(self) -> int:
        points = self._positive_int(self.config.get("graph_max_points", 24), 24)
        if points < 8:
            return 8
        if points > 48:
            return 48
        return points

    def _channel_id(self) -> int:
        return self._positive_int(self.config.get("channel_id", 0), 0)

    def _now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)

    @staticmethod
    def _positive_int(value, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default
