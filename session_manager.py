# session_manager.py
# User session management

from typing import Dict, Optional


class UserSession:
    """Class to manage user session data"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.server: int = 1
        self.options_settings: Dict = {}
        self.game_client = None
        self.complete: bool = False
        self.step: int = 0

    def to_dict(self) -> Dict:
        """Convert session to dictionary"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "password": self.password,
            "server": self.server,
            "options_settings": self.options_settings,
            "complete": self.complete,
            "step": self.step,
        }

    def is_setup_complete(self) -> bool:
        """Check if setup is complete"""
        return self.complete


class SessionManager:
    """Manages all user sessions"""

    def __init__(self):
        self.sessions: Dict[int, UserSession] = {}

    def create_session(self, user_id: int) -> UserSession:
        """Create a new session for a user"""
        if user_id in self.sessions:
            return self.sessions[user_id]

        session = UserSession(user_id)
        self.sessions[user_id] = session
        return session

    def get_session(self, user_id: int) -> Optional[UserSession]:
        """Get a user's session"""
        return self.sessions.get(user_id)

    def delete_session(self, user_id: int) -> bool:
        """Delete a user's session"""
        if user_id in self.sessions:
            del self.sessions[user_id]
            return True
        return False

    def session_exists(self, user_id: int) -> bool:
        """Check if a session exists for a user"""
        return user_id in self.sessions
