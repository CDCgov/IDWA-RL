from sqlalchemy import event
from sqlalchemy import orm
from sqlalchemy import schema
from sqlalchemy import types as sqltypes

from .base import Base


class Algorithm(Base):
    __tablename__ = "algorithm"

    id: orm.Mapped[int] = orm.mapped_column(primary_key=True)
    is_default: orm.Mapped[bool] = orm.mapped_column(default=False, index=True)
    label: orm.Mapped[str] = orm.mapped_column(sqltypes.String(255), unique=True)
    description: orm.Mapped[str] = orm.mapped_column(sqltypes.Text())
    passes: orm.Mapped[list["AlgorithmPass"]] = orm.relationship(
        back_populates="algorithm"
    )


def check_only_one_default(mapping, connection, target):
    """
    Check if there is already a default algorithm before inserting or updating.
    If another default algorithm exists, an exception is raised to prevent the operation.

    Parameters:
    connection: The database connection being used for the operation.
    target: The instance of the Algorithm class being inserted or updated.

    Raises:
    ValueError: If another algorithm is already marked as default.
    """

    session = orm.Session.object_session(target)

    if target.is_default:
        # ruff linting rule E712 ignored on this line.
        # ruff wants to enforce using the 'is' operator over '=='.
        # However since we only want to compare the truth value of the SQL query result we need to use '=='.
        existing = session.query(Algorithm).filter(Algorithm.is_default == True).first()  # noqa: E712

        if existing and existing.id != target.id:
            raise ValueError("There can only be one default algorithm")


event.listen(Algorithm, "before_insert", check_only_one_default)
event.listen(Algorithm, "before_update", check_only_one_default)


class AlgorithmPass(Base):
    __tablename__ = "algorithm_pass"

    id: orm.Mapped[int] = orm.mapped_column(primary_key=True)
    algorithm_id: orm.Mapped[int] = orm.mapped_column(schema.ForeignKey("algorithm.id"))
    algorithm: orm.Mapped["Algorithm"] = orm.relationship(back_populates="passes")
    blocking_keys: orm.Mapped[list[str]] = orm.mapped_column(sqltypes.JSON)
    evaluators: orm.Mapped[dict] = orm.mapped_column(sqltypes.JSON)
    rule: orm.Mapped[str] = orm.mapped_column(sqltypes.String(255))
    cluster_ratio: orm.Mapped[float] = orm.mapped_column(sqltypes.Float)
    kwargs: orm.Mapped[dict] = orm.mapped_column(sqltypes.JSON)