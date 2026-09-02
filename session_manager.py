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

    def clear_password(self):
        """
        FIX: the password sat in memory in plain text for the whole
        session lifetime with nothing ever clearing it. Call this right
        after GameClient has consumed it (inside complete_setup), so it
        isn't sitting around longer than needed.
        """
        self.password = None

    def to_dict(self) -> Dict:
        """Convert session to dictionary (password intentionally excluded)"""
        return {
            "user_id": self.user_id,
            "username": self.username,
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
        """Delete a user's session, disconnecting the game client first if present."""
        session = self.sessions.get(user_id)
        if session:
            if session.game_client:
                try:
                    session.game_client.disconnect()
                except Exception:
                    pass
            session.clear_password()
            del self.sessions[user_id]
            return True
        return False

    def session_exists(self, user_id: int) -> bool:
        """Check if a session exists for a user"""
        return user_id in self.sessions
