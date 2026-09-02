# utils.py
# Helper functions

from typing import Dict, Tuple, List
from config import (
    DEFAULT_OPTIONS,
    DEFAULT_SERVER,
    GAME_SERVERS,
    SERVER_NAMES,
    OPTION_KEY_MAP,
)


def parse_options_input(input_text: str) -> Tuple[Dict[str, bool], List[str]]:
    """
    Parse the options input from user.

    FIX: this now does a case-insensitive key match (old code required an
    exact-case match like "UseCoin" and silently ignored "usecoin"/"USECOIN").
    It also returns the list of keys it couldn't recognize so the caller can
    warn the user instead of quietly dropping their input.

    Args:
        input_text: Raw input string from user

    Returns:
        (options, unknown_keys)
    """
    options = DEFAULT_OPTIONS.copy()
    unknown_keys: List[str] = []

    if not input_text.strip():
        return options, unknown_keys

    items = input_text.split(",")
    for item in items:
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            unknown_keys.append(item)
            continue

        key, value = item.split(":", 1)
        key_normalized = key.strip().lower().replace(" ", "").replace("_", "")
        value = value.strip().lower() == "true"

        if key_normalized in OPTION_KEY_MAP:
            options[OPTION_KEY_MAP[key_normalized]] = value
        else:
            unknown_keys.append(key.strip())

    return options, unknown_keys


def format_options_output(options: Dict[str, bool]) -> str:
    """Format options settings for display"""
    if not options:
        return "All defaults"

    display_names = {
        "use_feathers": "Use Feathers",
        "use_coin": "Use Coin",
        "upgrade_storm_forts": "Upgrade Storm Forts",
        "noble_thieves_castles": "Noble Thieves Castles",
    }

    lines = []
    for key, value in options.items():
        status = "✅" if value else "❌"
        display = display_names.get(key, key.replace("_", " ").title())
        lines.append(f"• `{display}`: {status}")

    return "\n".join(lines)


def get_server_code(server_input: str) -> int:
    """
    Get server code from user input

    Args:
        server_input: Raw server input from user

    Returns:
        int: Server code (1, 2, 3, or 4)
    """
    server_input = server_input.strip()
    if not server_input:
        return DEFAULT_SERVER

    server_lower = server_input.lower()
    for key, value in GAME_SERVERS.items():
        if key.lower() == server_lower:
            return value

    try:
        num = int(server_input)
        if 1 <= num <= 4:
            return num
    except ValueError:
        pass

    return DEFAULT_SERVER


def get_server_name(server_code: int) -> str:
    """Get display name from server code"""
    return SERVER_NAMES.get(server_code, f"Server {server_code}")
