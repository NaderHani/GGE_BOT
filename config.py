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

# Game server settings (1 = Egypt 1)
DEFAULT_SERVER = 1

GAME_SERVERS = {
    "egypt 1": 1,
    "egypt1": 1,
    "eg1": 1,
    "EG1": 1,
    "egypt 2": 2,
    "egypt2": 2,
    "eg2": 2,
    "EG2": 2,
    "usa 1": 3,
    "usa1": 3,
    "us1": 3,
    "US1": 3,
    "europe 1": 4,
    "europe1": 4,
    "eu1": 4,
    "EU1": 4,
}

SERVER_NAMES = {
    1: "Egypt 1 (EG1)",
    2: "Egypt 2 (EG2)",
    3: "USA 1 (US1)",
    4: "Europe 1 (EU1)",
}

# Server string mapping for WebSocket
SERVER_STRINGS = {1: "en1", 2: "en2", 3: "us1", 4: "eu1"}

# Default settings (Forts removed, replaced with Noble Thieves)
DEFAULT_OPTIONS = {
    "use_feathers": False,
    "use_coin": True,
    "upgrade_storm_forts": False,
    "noble_thieves_castles": True,  # Closest Noble Thieves Castles
}
