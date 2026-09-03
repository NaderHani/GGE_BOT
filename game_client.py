# game_client.py
# Discord-safe wrapper around empire-core for Goodgame Empire socket traffic.

import logging
import math
import threading
import time
from typing import Dict, List, Optional

from empire_core.client.client import EmpireClient as _EmpireClient
from empire_core.config import EmpireConfig, MAP_CHUNK_SIZE
from empire_core.exceptions import LoginCooldownError, LoginError, TimeoutError
from empire_core.network.connection import Connection
from empire_core.protocol.packet import Packet
from empire_core.state.manager import GameState
from empire_core.state.world_models import MapObject
from empire_core.utils.enums import MapObjectType

from config import SERVER_CONFIG, SERVER_NAMES

logger = logging.getLogger(__name__)


class GameClientError(Exception):
    """Raised when game connection or data retrieval fails."""


class ZoneConnection(Connection):
    """Connection that uses the correct game zone for keepalive pings."""

    def __init__(self, url: str, zone: str):
        super().__init__(url)
        self.zone = zone

    def _keepalive_loop(self) -> None:
        logger.debug("Keepalive loop started")
        while self._running:
            time.sleep(30)
            if not self._running:
                break
            try:
                self.send(f"%xt%{self.zone}%pin%1%<RoundHouseKick>%")
                logger.debug("Sent keepalive ping")
            except Exception as e:
                if self._running:
                    logger.error(f"Keepalive failed: {e}")
                break
        logger.debug("Keepalive loop ended")


class _EmpireClientPatched(_EmpireClient):
    """Empire client with full GameState updates and zone-aware connection."""

    def __init__(self, config: EmpireConfig):
        self.config = config
        self.username = config.username
        self.password = config.password
        self.connection = ZoneConnection(config.game_url, config.default_zone)
        self.state = GameState()
        self.is_logged_in = False
        self.connection.on_packet = self._on_packet
        self.connection.on_disconnect = self._on_disconnect

    def _on_packet(self, packet: Packet) -> None:
        if packet.command_id and isinstance(packet.payload, dict):
            self.state.update_from_packet(packet.command_id, packet.payload)
            if packet.command_id == "gaa":
                self._handle_gaa(packet.payload)
        if packet.command_id == "gam" and isinstance(packet.payload, dict):
            self._update_state(packet.command_id, packet.payload)

    def _handle_gaa(self, data: dict) -> None:
        """Parse map chunk data from gaa responses."""
        areas = data.get("AI", data.get("A", []))
        if not isinstance(areas, list):
            return
        for entry in areas:
            if isinstance(entry, dict):
                try:
                    obj = MapObject.model_validate(entry)
                    if obj.area_id >= 0:
                        self.state.map_objects[obj.area_id] = obj
                except Exception:
                    continue
            elif isinstance(entry, list) and len(entry) > 10:
                area_id = entry[3]
                try:
                    obj = MapObject(
                        AID=area_id,
                        OID=entry[4] if len(entry) > 4 else -1,
                        T=entry[5] if len(entry) > 5 else MapObjectType.UNKNOWN,
                        L=entry[6] if len(entry) > 6 else 0,
                        X=entry[0],
                        Y=entry[1],
                        KID=entry[2] if len(entry) > 2 else 0,
                        name=str(entry[10]) if len(entry) > 10 else "",
                    )
                    self.state.map_objects[area_id] = obj
                except Exception:
                    continue

    def _wait_for_game_data(self, timeout: float = 15.0) -> None:
        """Wait until login populates player/castle state (gbd packet)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            player = self.state.local_player
            if player and player.castles:
                return
            try:
                self.connection.wait_for("gbd", timeout=min(2.0, deadline - time.time()))
            except TimeoutError:
                continue
        raise TimeoutError("Timed out waiting for game data after login")

    def request_detailed_castles(self, timeout: float = 10.0) -> None:
        packet = Packet.build_xt(self.config.default_zone, "dcl", {})
        self.connection.send(packet)
        try:
            self.connection.wait_for("dcl", timeout=timeout)
        except TimeoutError:
            logger.warning("dcl request timed out — resources may be incomplete")

    def scan_nearby_npcs(
        self,
        radius_chunks: int = 3,
        timeout_per_chunk: float = 3.0,
    ) -> List[int]:
        """Scan map chunks around the main castle and return nearby NPC area IDs."""
        player = self.state.local_player
        if not player or not player.castles:
            return []

        main_castle = next(iter(player.castles.values()))
        kingdom_id = main_castle.kingdom_id
        cx, cy = main_castle.x, main_castle.y
        chunk_step = 13
        center_chunk_x = cx // chunk_step
        center_chunk_y = cy // chunk_step

        found: Dict[int, float] = {}

        for dx in range(-radius_chunks, radius_chunks + 1):
            for dy in range(-radius_chunks, radius_chunks + 1):
                x = (center_chunk_x + dx) * chunk_step
                y = (center_chunk_y + dy) * chunk_step
                payload = {
                    "KID": kingdom_id,
                    "AX1": x,
                    "AY1": y,
                    "AX2": x + MAP_CHUNK_SIZE,
                    "AY2": y + MAP_CHUNK_SIZE,
                }
                packet = Packet.build_xt(self.config.default_zone, "gaa", payload)
                self.connection.send(packet)
                try:
                    self.connection.wait_for("gaa", timeout=timeout_per_chunk)
                except TimeoutError:
                    continue

                for obj in self.state.map_objects.values():
                    if obj.type not in (
                        MapObjectType.ROBBER_BARON_CASTLE,
                        MapObjectType.DUNGEON,
                        MapObjectType.BOSS_DUNGEON,
                    ):
                        continue
                    dist = math.hypot(obj.x - cx, obj.y - cy)
                    if obj.area_id not in found or dist < found[obj.area_id]:
                        found[obj.area_id] = dist

        return [aid for aid, _ in sorted(found.items(), key=lambda item: item[1])]


class GameClient:
    """WebSocket client for Goodgame Empire, backed by empire-core."""

    def __init__(self, username: str, password: str, server: int = 1):
        self.username = username
        self.password = password
        self.server_int = server

        server_cfg = SERVER_CONFIG.get(server, SERVER_CONFIG[1])
        self.server_info = {
            "name": SERVER_NAMES.get(server, f"Server {server}"),
            **server_cfg,
        }

        self._client: Optional[_EmpireClientPatched] = None
        self.is_connected = False
        self.is_logged_in = False
        self.player_id: Optional[int] = None
        self.player_name: Optional[str] = None
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()

    def connect(self) -> bool:
        """Connect and log in to the game server."""
        self.last_error = None
        try:
            logger.info(
                f"Connecting to {self.server_info['name']} as {self.username}"
            )

            config = EmpireConfig(
                game_url=self.server_info["game_url"],
                default_zone=self.server_info["zone"],
                username=self.username,
                password=self.password,
            )
            client = _EmpireClientPatched(config)

            with self._lock:
                client.login()
                client._wait_for_game_data()
                client.request_detailed_castles()

            self._client = client
            self.is_connected = True
            self.is_logged_in = client.is_logged_in

            player = client.state.local_player
            if player:
                self.player_id = player.id
                self.player_name = player.name

            logger.info(
                f"Logged in to {self.server_info['name']} as {self.player_name or self.username}"
            )
            return True

        except LoginCooldownError as e:
            self.last_error = str(e)
        except LoginError as e:
            self.last_error = f"Login failed: {e}"
        except TimeoutError as e:
            self.last_error = f"Connection timed out: {e}"
        except Exception as e:
            self.last_error = str(e)

        logger.error(f"Connection failed: {self.last_error}")
        self._cleanup_client()
        self.is_connected = False
        self.is_logged_in = False
        return False

    def _cleanup_client(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def get_castle_info(self) -> dict:
        if not self._client or not self.is_logged_in:
            raise GameClientError("Not logged in.")

        player = self._client.state.local_player
        if not player or not player.castles:
            raise GameClientError("Castle data not available yet.")

        castle = next(iter(player.castles.values()))
        return {
            "name": castle.name,
            "level": player.level,
            "points": player.xp,
            "x": castle.x,
            "y": castle.y,
        }

    def get_resources(self) -> dict:
        if not self._client or not self.is_logged_in:
            raise GameClientError("Not logged in.")

        player = self._client.state.local_player
        if not player or not player.castles:
            raise GameClientError("Resource data not available yet.")

        castle = next(iter(player.castles.values()))
        res = castle.resources
        return {
            "wood": res.wood,
            "stone": res.stone,
            "iron": res.iron,
            "gold": player.gold,
            "food": res.food,
        }

    def get_noble_thieves_castles(self) -> List[int]:
        if not self._client or not self.is_logged_in:
            raise GameClientError("Not logged in.")

        with self._lock:
            return self._client.scan_nearby_npcs()

    def setup_account(self, settings: dict) -> dict:
        if not self.is_connected or not self._client:
            return {"success": False, "error": "Not connected"}

        result = {
            "success": True,
            "account_name": self.username,
            "server": self.server_int,
            "server_name": self.server_info["name"],
            "player_id": self.player_id,
            "player_name": self.player_name or self.username,
            "logged_in": self.is_logged_in,
            "status": "logged_in" if self.is_logged_in else "socket_open",
        }

        if settings.get("options", {}).get("noble_thieves_castles", False):
            try:
                result["noble_thieves_castles"] = self.get_noble_thieves_castles()
            except GameClientError:
                result["noble_thieves_castles"] = []

        return result

    def send_chat_message(self, message: str) -> bool:
        if not self._client or not self.is_logged_in:
            return False
        try:
            self._client.send_alliance_chat(message)
            return True
        except Exception as e:
            logger.error(f"Chat send failed: {e}")
            return False

    def disconnect(self) -> None:
        with self._lock:
            self._cleanup_client()
        self.is_connected = False
        self.is_logged_in = False
        logger.info("Disconnected")
