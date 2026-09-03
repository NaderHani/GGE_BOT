# config.py
# Configuration settings for the bot

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Discord settings
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
COMMAND_PREFIX = "!"
MESSAGE_TIMEOUT = 60  # seconds

# --- FIX: never silently fake a successful connection unless the operator ---
# explicitly opts in. Read from .env so it's not hardcoded / forgotten.
# When False (default), a failed connection is reported as a real failure.
# When True, a failed real connection falls back to a clearly-labeled demo mode.
ALLOW_SIMULATION_FALLBACK = (
    os.getenv("ALLOW_SIMULATION_FALLBACK", "false").lower() == "true"
)

# Game server settings (1 = Egypt 1)
DEFAULT_SERVER = 1

GAME_SERVERS = {
    "egypt 1": 1,
    "egypt1": 1,
    "eg1": 1,
    "egypt 2": 2,
    "egypt2": 2,
    "eg2": 2,
    "usa 1": 3,
    "usa1": 3,
    "us1": 3,
    "europe 1": 4,
    "europe1": 4,
    "eu1": 4,
}
# NOTE (FIX): removed the duplicate uppercase keys ("EG1", "EG2", ...).
# They were dead code — get_server_code() already lowercases input before
# comparing, so the uppercase entries could never be matched anyway.

SERVER_NAMES = {
    1: "Egypt 1 (EG1)",
    2: "Egypt 2 (EG2)",
    3: "USA 1 (US1)",
    4: "Europe 1 (EU1)",
}

# Server string mapping for WebSocket
SERVER_STRINGS = {1: "en1", 2: "en2", 3: "us1", 4: "eu1"}

# Per-server WebSocket URL and SmartFox zone (required for real socket traffic).
# EG1 values are from captured browser traffic; others follow the same naming pattern.
SERVER_CONFIG = {
    1: {
        "game_url": "wss://ep-live-mz-sa1-ae1-eg1-arab1-game.goodgamestudios.com/",
        "zone": "EmpireEx_34",
    },
    2: {
        "game_url": "wss://ep-live-eg2-game.goodgamestudios.com/",
        "zone": "EmpireEx_34",
    },
    3: {
        "game_url": "wss://ep-live-us1-game.goodgamestudios.com/",
        "zone": "EmpireEx_21",
    },
    4: {
        "game_url": "wss://ep-live-eu1-game.goodgamestudios.com/",
        "zone": "EmpireEx_21",
    },
}

# Default settings (Forts removed, replaced with Noble Thieves)
DEFAULT_OPTIONS = {
    "use_feathers": True,
    "use_coin": False,
    "upgrade_storm_forts": False,
    "noble_thieves_castles": True,  # Closest Noble Thieves Castles
}

# --- FIX: case-insensitive option key mapping ---
# Old code matched "UseCoin" exactly, so "usecoin" or "USECOIN" silently
# failed to update anything. Keys here are lowercased once; utils.py
# lowercases user input the same way before lookup.
OPTION_KEY_MAP = {
    "usefeathers": "use_feathers",
    "usecoin": "use_coin",
    "upgradestormforts": "upgrade_storm_forts",
    "noblethievescastles": "noble_thieves_castles",
}
