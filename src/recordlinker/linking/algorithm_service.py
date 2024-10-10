"""
recordlinker.linking.algorithm_service
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module provides the data access functions to the algorithm config tables
"""
import typing

from sqlalchemy import orm
from sqlalchemy import select

from recordlinker import models


def get_all_algorithm_labels(session: orm.Session) -> typing.Sequence[str]:
    """
    Gets a list of algorithms from the MPI database.
    returns: list of all labels column from algorithms table
    """
    return session.scalars(select(models.Algorithm.label)).all()

def get_algorithm_by_label(session: orm.Session, label: str | None) -> models.Algorithm | None:
    """
    Gets a single algorithm by searching for the unique label
    returns: algorithm object
    """
    if not label:
        algorithm = session.scalar(select(models.Algorithm).where(models.Algorithm.is_default == True)) # noqa: E712
    else:
        algorithm = session.scalar(select(models.Algorithm).where(models.Algorithm.label == label))

    return algorithm
    
