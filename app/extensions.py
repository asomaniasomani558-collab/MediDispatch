"""Flask extension singletons.

They are created unbound here and attached to the app inside the factory
(``app/__init__.py``) so that tests can build isolated app instances.
"""

from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by every model."""


db = SQLAlchemy(model_class=Base)
socketio = SocketIO()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"
