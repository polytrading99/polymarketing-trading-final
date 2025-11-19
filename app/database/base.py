import re

from sqlalchemy.orm import DeclarativeBase, declared_attr


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class Base(DeclarativeBase):
    """Declarative base class that automatically derives table names."""

    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore[override]
        return camel_to_snake(cls.__name__)


