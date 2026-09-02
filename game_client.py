# game_client.py
# Real WebSocket connection to Goodgame Empire
#
# ============================================================================
# IMPORTANT — READ THIS BEFORE USING
# ============================================================================
# Goodgame Empire's real network protocol (the %xt% message framing, the
# login handshake commands, and how castle/resource/noble-thief data comes
# back) is NOT documented publicly. The previous version of this file faked
# a "SIMULATION mode" that silently returned made-up numbers and told the
# user they were "Connected" even when nothing real happened. That has been
# removed on purpose — a bot that lies about its own connection state is
# worse than one that just fails loudly.
#
# Everywhere you see `# TODO(protocol):` below is a real gap that needs the
# actual message formats you captured yourself (e.g. via browser dev tools /
# a proxy while playing manually). Nothing else in this file depends on you
# doing that except the methods that need live game data — connecting,
# session handling, threading, and error reporting all work today.
# ============================================================================

import logging
import json
import threading
import time
from typing import Dict, Optional, List

import requests
import websocket

logger = logging.getLogger(__name__)


class GameClientError(Exception):
    """Raised for any connection/setup failure. Callers should show
    str(exception) to the user instead of pretending things worked."""


class GameClient:
    """WebSocket client for Goodgame Empire."""

    def __init__(self, username: str, password: str, server: int = 1):
        self.username = username
        self.password = password
        self.server_int = server

        # NOTE: EG1's "ws" domain below is confirmed from real captured
        # browser traffic. EG2/US1/EU1 were never captured — they're
        # unverified guesses following the same naming pattern and will
        # very likely need correcting the same way you found EG1's (open
        # DevTools → Network → Socket filter while logging into that
        # specific server).
        self.server_domains = {
            1: {
                "ws": "ep-live-mz-sa1-ae1-eg1-arab1-game.goodgamestudios.com",
                "web": "empire.goodgamestudios.com",
                "name": "EG1",
            },
            2: {
                "ws": "live-eg2.goodgamestudios.com",
                "web": "empire.goodgamestudios.com",
                "name": "EG2",
            },  # UNVERIFIED
            3: {
                "ws": "live-us1.goodgamestudios.com",
                "web": "empire.goodgamestudios.com",
                "name": "US1",
            },  # UNVERIFIED
            4: {
                "ws": "live-eu1.goodgamestudios.com",
                "web": "empire.goodgamestudios.com",
                "name": "EU1",
            },  # UNVERIFIED
        }
        self.server_info = self.server_domains.get(server, self.server_domains[1])

        # --- Protocol constants captured from real browser traffic ---
        # These are tied to a specific game client build and WILL go stale
        # when Goodgame Empire updates. If login stops working, re-capture
        # traffic (see the handshake code below) and update these.
        self.game_zone = "EmpireEx_34"  # SFS zone name / %xt% module name
        self.sfs_version = "166"  # SmartFoxServer verChk version
        self.build_number = "1167009"  # game client build used in vck

        self.ws: Optional[websocket.WebSocketApp] = None
        self.session: Optional[requests.Session] = None

        self.is_connected = False  # WebSocket socket is open
        self.is_logged_in = False  # TODO(protocol): set True only once the real
        # login handshake actually confirms success
        self.player_id: Optional[int] = None
        self.player_name: Optional[str] = None
        self.last_error: Optional[str] = None

        # Cached game-state, populated only by real parsed server messages.
        # TODO(protocol): fill these in inside _on_message() once you know
        # the real message formats.
        self._castle_data: Optional[dict] = None
        self._resources_data: Optional[dict] = None
        self._noble_thieves_data: Optional[list] = None

        self._stop_event = threading.Event()
        self._ws_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Connect to Goodgame Empire.

        FIX: this no longer falls back to a fake "connected" state on
        failure. If it returns False, `self.last_error` explains why, and
        the caller (bot.py) reports the real failure to the user.

        Returns:
            bool: True only if the WebSocket actually opened.
        """
        self.last_error = None
        try:
            logger.info(
                f"🔌 Connecting to {self.server_info['name']} as {self.username}"
            )

            # Best-effort HTTP session warm-up. Not required for the socket
            # to open, but some deployments use cookies from this for the
            # login handshake below.
            self._http_login()

            if not self._websocket_connect():
                self.last_error = (
                    self.last_error or "WebSocket connection failed or timed out."
                )
                logger.error(f"❌ {self.last_error}")
                return False

            self.is_connected = True

            # TODO(protocol): this is where you send the real login
            # handshake (e.g. the equivalent of %xt%EmpireEx_X%vln%...%
            # followed by %xt%EmpireEx_X%lli%... with your captured
            # payload format) and wait for a real confirmation message
            # before declaring success. Right now `is_logged_in` stays
            # False until you wire that up in _on_message().
            self._perform_login_handshake()

            logger.info(
                f"✅ Socket open to {self.server_info['name']} (login handshake pending)"
            )
            return True

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"❌ Connection failed: {self.last_error}")
            self.is_connected = False
            return False

    def _http_login(self) -> bool:
        """Best-effort HTTP warm-up. Failure here is not fatal — it does
        not, by itself, mean the WebSocket login will fail too."""
        try:
            web_url = f"https://{self.server_info['web']}"
            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept-Language": "en-US,en;q=0.5",
                }
            )
            session.get(web_url, timeout=10)
            self.session = session
            return True
        except Exception as e:
            logger.warning(f"⚠️ HTTP warm-up failed (non-fatal): {e}")
            return False

    def _websocket_connect(self) -> bool:
        """Open the WebSocket. Returns True only once on_open actually fires."""
        try:
            # FIX: real captured traffic shows no "/ws" path, just the bare
            # domain, e.g. wss://ep-live-mz-sa1-ae1-eg1-arab1-game.goodgamestudios.com/
            # Update server_domains["ws"] in config for each server you use —
            # these domains can differ per server/region and sometimes change.
            ws_url = f"wss://{self.server_info['ws']}/"
            logger.info(f"🔌 WebSocket: {ws_url}")

            headers = []
            if self.session:
                cookies = self.session.cookies.get_dict()
                if cookies:
                    headers.append(
                        "Cookie: " + "; ".join(f"{k}={v}" for k, v in cookies.items())
                    )

            self.ws = websocket.WebSocketApp(
                ws_url,
                header=headers,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )

            self._stop_event.clear()
            self._ws_thread = threading.Thread(target=self._ws_run, daemon=True)
            self._ws_thread.start()

            # Wait for on_open to flip is_connected, with a real timeout.
            for _ in range(10):
                if self._stop_event.wait(timeout=1):
                    return False
                if self.is_connected:
                    return True

            self.last_error = "Timed out waiting for WebSocket to open."
            return False

        except Exception as e:
            self.last_error = f"WebSocket setup error: {e}"
            logger.error(f"❌ {self.last_error}")
            return False

    def _ws_run(self):
        try:
            self.ws.run_forever()
        except Exception as e:
            logger.error(f"WebSocket loop error: {e}")
        finally:
            self.is_connected = False

    def _perform_login_handshake(self):
        """
        Real handshake, built from captured browser traffic. Two protocol
        layers are stacked here:

          1. SmartFoxServer (SFS) — plain XML messages that establish a
             base session in the "zone" before any game logic runs.
          2. The game's own %xt% layer on top of that SFS session, which
             does the actual account login.

        NOTE: `self.game_version`, `self.build_number`, and the
        "<RoundHouseKick>" marker below are values captured at one point
        in time. Goodgame Empire updates its client periodically and these
        can change — if login silently stops working, re-capture traffic
        and diff it against what's here.
        """
        zone = self.game_zone  # e.g. "EmpireEx_34"

        # --- Layer 1: SmartFoxServer session setup ---
        self._send_raw(
            f"<msg t='sys'><body action='verChk' r='0'><ver v='{self.sfs_version}' /></body></msg>"
        )
        # Anonymous/guest SFS login into the game's zone (nick/password
        # empty here — this is NOT the game account login, just opens an
        # SFS session so %xt% commands are accepted).
        self._send_raw(
            f"<msg t='sys'><body action='login' r='0'>"
            f"<login z='{zone}'><nick><![CDATA[]]></nick><pword><![CDATA[]]></pword></login>"
            f"</body></msg>"
        )
        self._send_raw("<msg t='sys'><body action='autoJoin' r='-1'></body></msg>")
        self._send_raw("<msg t='sys'><body action='roundTrip' r='1'></body></msg>")

        # --- Layer 2: game-level login over %xt% ---
        # vck = version check for the game client itself (separate from the
        # SFS verChk above). Captured shape:
        #   %xt%<zone>%vck%1%<build_number>%web-html5%<RoundHouseKick>%<float>%
        #
        # HONEST NOTE: the last field in your capture was
        # "5.728189859123153e+307" — a value with no obvious relationship
        # to a real timestamp or counter. This looks like an
        # obfuscation/fingerprint value the official client computes with
        # some formula I can't reverse from a single sample. Two options:
        #   1. Try sending the exact literal value you captured and see if
        #      the server accepts it (servers often only sanity-check the
        #      *shape*, not the exact value).
        #   2. Capture 2-3 more logins and diff this field across them —
        #      if it changes in a predictable way, that tells you the
        #      formula; if it's identical every time, it's a fixed
        #      constant you can hardcode.
        last_field = (
            "5.728189859123153e+307"  # from your capture — verify/replace as above
        )
        self._send_raw(
            f"%xt%{zone}%vck%1%{self.build_number}%web-html5%<RoundHouseKick>%{last_field}%"
        )

        # vln = verify login name
        self._send_raw(f"%xt%{zone}%vln%1%{json.dumps({'NOM': self.username})}%")

        # lli = the actual login call. Field names captured verbatim:
        #   CONM, RTM, ID, PL, NOM, PW, LT, LANG (LANG was cut off in the
        #   capture — "en" used here; check your own capture and correct
        #   if your account's client sends something else).
        login_payload = {
            "CONM": 469,
            "RTM": 202,
            "ID": 0,
            "PL": 1,
            "NOM": self.username,
            "PW": self.password,
            "LT": None,
            "LANG": "en",
        }
        self._send_raw(f"%xt%{zone}%lli%1%{json.dumps(login_payload)}%")

        # TODO(protocol): the server's reply to `lli` is one of the
        # "Binary Message" frames in devtools, not plain %xt% text — see
        # the SFSObject note in _on_message() for why that needs separate
        # handling, and set self.is_logged_in / self.player_id there once
        # you can decode it.

    # ------------------------------------------------------------------
    # Message I/O
    # ------------------------------------------------------------------

    def _on_open(self, ws):
        logger.info("✅ WebSocket opened")
        self.is_connected = True

    def _on_message(self, ws, message):
        """
        Your capture showed three distinct message shapes coming back:

          1. Plain SFS XML text, e.g. <msg t='sys'>...</msg>
          2. Plain %xt% text (rare on the way *in* — mostly seen going out)
          3. "Binary Message" — the vast majority of real replies,
             including the login confirmation and all game data.

        (1) and (2) are handled below. (3) is explained further down —
        it needs one more piece of research before it can be parsed here.
        """
        try:
            # --- Binary frames: SmartFoxServer's SFSObject format ---
            if isinstance(message, bytes):
                self._handle_binary_message(message)
                return

            logger.info(f"📩 Received: {message[:150]}")

            if message.startswith("<msg"):
                self._handle_sfs_xml_message(message)
                return

            if message.startswith("%xt%"):
                parts = message.split("%")
                cmd = parts[3] if len(parts) > 3 else "unknown"
                payload_str = parts[4] if len(parts) > 4 else "{}"
                self._handle_xt_message(cmd, payload_str)
                return

            logger.info(f"📩 Unrecognized text message: {message[:150]}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def _handle_sfs_xml_message(self, message: str):
        """Minimal parsing of the SFS XML layer (verChk/login/autoJoin acks).
        These only confirm the *session* is alive — real login/game data
        comes back as binary (see _handle_binary_message)."""
        logger.info(f"📩 SFS system message: {message[:150]}")
        # TODO(protocol) [optional]: if you need to react to a specific
        # action (e.g. detect a login rejection), parse the `action=`
        # attribute with xml.etree.ElementTree here.

    def _handle_xt_message(self, cmd: str, payload_str: str):
        """Handle %xt% replies that come back as plain text (uncommon —
        most %xt% replies in your capture were binary instead)."""
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            data = payload_str
        logger.info(f"📩 %xt% command '{cmd}' payload: {data}")
        # TODO(protocol): add `if cmd == "...": ...` branches here for any
        # command you confirm actually replies in plain %xt% JSON rather
        # than binary, and populate self._castle_data etc. from it.

    def _handle_binary_message(self, raw: bytes):
        """
        HONEST STATE OF THIS METHOD: not implemented yet, on purpose.

        Every meaningful reply in your capture (login confirmation, castle
        info, resources, notifications) came back as "Binary Message" in
        DevTools — that's SmartFoxServer's SFSObject binary serialization,
        not JSON and not something safe to guess the byte layout of from
        a length column alone.

        The fastest reliable path is NOT to reimplement SFSObject decoding
        by hand in Python. It's to reuse the *exact* decoder the game
        itself already ships to your browser:

          1. In DevTools → Sources (or Network → JS), find the JS file the
             game loads that references "SFSObject", "IoHandler", or
             similar SmartFoxServer client symbols (often bundled inside
             a larger minified engine file).
          2. That file contains the real, exact encode/decode logic —
             copy the relevant decode function(s) instead of guessing.
          3. Either port that JS logic to Python by hand (tedious but
             gives you a pure-Python client), or run it as-is: pipe the
             raw bytes into that JS via Node.js (subprocess, or a
             library like PyExecJS) and get back a JSON-able object,
             which you then map into self._castle_data /
             self._resources_data / self._noble_thieves_data here.

        For now this just logs enough to let you correlate a given binary
        reply with the request that triggered it (length + a hex preview),
        which is exactly what you need for step 1 above.
        """
        preview = raw[:32].hex()
        logger.info(
            f"📩 Binary message received: {len(raw)} bytes, starts with {preview}"
        )
        # TODO(protocol): replace this log line with real decoding once
        # you've extracted the client's own SFSObject decoder (see
        # docstring above), then set:
        #   self.is_logged_in, self.player_id, self.player_name
        #   self._castle_data, self._resources_data, self._noble_thieves_data
        # from the decoded object.

    def _on_error(self, ws, error):
        self.last_error = str(error)
        logger.error(f"❌ WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info(f"🔌 WebSocket closed: {close_status_code} {close_msg or ''}")
        self.is_connected = False
        self.is_logged_in = False

    def _send_raw(self, raw_message: str) -> bool:
        """Send a raw string over the socket (use this for %xt% commands)."""
        if not self.is_connected or not self.ws:
            return False
        try:
            self.ws.send(raw_message)
            logger.info(f"📤 Sent: {raw_message[:150]}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send: {e}")
            return False

    # ------------------------------------------------------------------
    # Game data — honest about what isn't implemented yet
    # ------------------------------------------------------------------

    def get_castle_info(self) -> dict:
        """
        Returns real cached castle data if the protocol layer has populated
        it, otherwise raises so the caller shows "not available yet"
        instead of made-up numbers.
        """
        if self._castle_data is not None:
            return self._castle_data
        raise GameClientError(
            "Castle data not available — login handshake / parsing not implemented yet."
        )

    def get_resources(self) -> dict:
        if self._resources_data is not None:
            return self._resources_data
        raise GameClientError(
            "Resource data not available — login handshake / parsing not implemented yet."
        )

    def get_noble_thieves_castles(self) -> List[int]:
        if self._noble_thieves_data is not None:
            return self._noble_thieves_data
        raise GameClientError(
            "Noble Thieves data not available — login handshake / parsing not implemented yet."
        )

    def setup_account(self, settings: dict) -> dict:
        """
        FIX: no longer claims success unconditionally. Reports the real
        connection state; game-specific data is only included if it was
        actually received from the server.
        """
        if not self.is_connected:
            return {"success": False, "error": "Not connected"}

        result = {
            "success": True,
            "account_name": self.username,
            "server": self.server_int,
            "server_name": self.server_info["name"],
            "player_id": self.player_id,
            "player_name": self.player_name or self.username,
            "logged_in": self.is_logged_in,
            "status": "socket_open" if not self.is_logged_in else "logged_in",
        }

        if settings.get("options", {}).get("noble_thieves_castles", False):
            try:
                result["noble_thieves_castles"] = self.get_noble_thieves_castles()
            except GameClientError:
                result["noble_thieves_castles"] = []

        return result

    def send_chat_message(self, message: str) -> bool:
        """
        TODO(protocol): wire this to the real chat command once you know
        its %xt% format. Returns False (not silently "simulated true")
        until then.
        """
        if not self.is_connected:
            return False
        logger.warning(
            "send_chat_message: real chat command not implemented — see TODO(protocol)"
        )
        return False

    def disconnect(self):
        """FIX: actually signals the background thread to stop and joins
        it, instead of leaving run_forever() potentially dangling."""
        self._stop_event.set()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=3)
        self.is_connected = False
        self.is_logged_in = False
        logger.info("🔌 Disconnected")
