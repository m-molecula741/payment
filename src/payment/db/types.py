import enum

from sqlalchemy import Enum


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Postgres-enum, в колонке лежат значения, а не имена членов."""

    def values(source: type[enum.Enum]) -> list[str]:
        return [member.value for member in source]

    return Enum(enum_cls, name=name, native_enum=True, values_callable=values)
