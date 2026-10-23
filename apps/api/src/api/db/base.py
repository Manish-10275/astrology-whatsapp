"""SQLAlchemy 2.x declarative base class."""

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs


class Base(AsyncAttrs, DeclarativeBase):
    """Base declarative class with async attributes support."""
    pass
