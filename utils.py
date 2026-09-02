# utils.py
# Helper functions

from typing import Dict
from config import DEFAULT_OPTIONS, DEFAULT_SERVER, GAME_SERVERS, SERVER_NAMES


def parse_options_input(input_text: str) -> Dict[str, bool]:
    """
    Parse the options input from user

    Args:
        input_text: Raw input string from user

    Returns:
        dict: Parsed options settings
    """
    options = DEFAULT_OPTIONS.copy()

    if not input_text.strip():
        return options

    items = input_text.split(",")
    for item in items:
        item = item.strip()
        if ":" in item:
            key, value = item.split(":", 1)
            key = key.strip()
            value = value.strip().lower() == "true"

            mapping = {
                "UseFeathers": "use_feathers",
                "UseCoin": "use_coin",
                "UpgradeStormForts": "upgrade_storm_forts",
                "NobleThievesCastles": "noble_thieves_castles",
            }

            if key in mapping:
                options[mapping[key]] = value

    return options


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
