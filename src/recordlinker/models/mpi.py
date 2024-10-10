import enum
import json
import uuid

from sqlalchemy import orm
from sqlalchemy import schema
from sqlalchemy import types as sqltypes

from .base import Base
from .base import get_bigint_pk
from .pii import Feature
from .pii import PIIRecord

# The maximum length of a blocking value, we want to optimize this to be as small
# as possible to reduce the amount of data stored in the database.  However, it needs
# to be long enough to store the longest possible value for a blocking key.
BLOCKING_VALUE_MAX_LENGTH = 20


class Person(Base):
    __tablename__ = "mpi_person"

    id: orm.Mapped[int] = orm.mapped_column(get_bigint_pk(), autoincrement=True, primary_key=True)
    internal_id: orm.Mapped[uuid.UUID] = orm.mapped_column(default=uuid.uuid4)
    patients: orm.Mapped[list["Patient"]] = orm.relationship(back_populates="person")

    def __hash__(self):
        """
        Hash the Person object based on the primary key.
        """
        return hash(self.id)

    def __eq__(self, other):
        """
        Compare two Person objects based on the primary key.
        """
        return self.id == other.id if isinstance(other, Person) else False


class Patient(Base):
    __tablename__ = "mpi_patient"

    id: orm.Mapped[int] = orm.mapped_column(get_bigint_pk(), autoincrement=True, primary_key=True)
    person_id: orm.Mapped[int] = orm.mapped_column(schema.ForeignKey("mpi_person.id"))
    person: orm.Mapped["Person"] = orm.relationship(back_populates="patients")
    # NOTE: We're using a protected attribute here to store the data string, as we
    # want getter/setter access to the data dictionary to trigger updating the 
    # calculated record property.  Mainly this is to ensure that the cached record
    # property, self._record, is cleared when the data is updated.
    _data: orm.Mapped[dict] = orm.mapped_column("data", sqltypes.JSON, default=dict)
    external_patient_id: orm.Mapped[str] = orm.mapped_column(sqltypes.String(255), nullable=True)
    external_person_id: orm.Mapped[str] = orm.mapped_column(sqltypes.String(255), nullable=True)
    external_person_source: orm.Mapped[str] = orm.mapped_column(sqltypes.String(100), nullable=True)
    blocking_values: orm.Mapped[list["BlockingValue"]] = orm.relationship(back_populates="patient")

    @classmethod
    def _scrub_empty(cls, data: dict) -> dict:
        """
        Recursively remove all None, empty lists and empty dicts from the data.
        """

        def is_empty(value):
            return value is None or value == [] or value == {}

        if isinstance(data, dict):
            # Recursively process nested dictionaries
            return {k: cls._scrub_empty(v) for k, v in data.items() if not is_empty(v)}
        elif isinstance(data, list):
            # Recursively process lists, removing None elements
            return [cls._scrub_empty(v) for v in data if not is_empty(v)]
        # Base case: return the value if it's not a dict or list
        return data

    @property
    def data(self) -> dict:
        """
        Return the data dictionary for this patient record.
        """
        return self._data

    @data.setter  # type: ignore
    def data(self, value: dict):
        """
        Set the Patient data from a dictionary.

        """
        self._data = value
        if hasattr(self, "_record"):
            # if the record property is cached, delete it
            del self._record

    @property
    def record(self) -> PIIRecord:
        """
        Return a PIIRecord object with the data from this patient record.
        """
        if not hasattr(self, "_record"):
            # caching the result of the record property for performance
            self._record = PIIRecord.model_construct(**(self._data or {}))
        return self._record

    @record.setter  # type: ignore
    def record(self, value: PIIRecord):
        """
        Set the Patient data from a PIIRecord object.
        """
        assert isinstance(value, PIIRecord), "Expected a PIIRecord object"
        # convert the data to a JSON string, then load it back as a dictionary
        # this is necessary to ensure all data elements are JSON serializable
        data = json.loads(value.model_dump_json())
        # recursively remove all None, empty lists and empty dicts from the data
        # this is an optimization to reduce the amount of data stored in the
        # database, if a value is empty, no need to store it
        self._data = self._scrub_empty(data)
        if hasattr(self, "_record"):
            # if the record property is cached, delete it
            del self._record


class BlockingKey(enum.Enum):
    """
    Enum for the different types of blocking keys that can be used for patient
    matching. This is the universe of all possible blocking keys that a user can
    choose from when configuring their algorithm.  When data is loaded into the
    MPI, all possible BlockingValues will be created for the defined BlockingKeys.
    However, only a subset will be used in matching, based on the configuration of
    the algorithm.  By defining them all upfront, we give the user flexibility in
    adjusting their algorithm configuration without having to reload the data.

    NOTE: The database schema is designed to allow for blocking values up to 20 characters
    in length.  All blocking keys should be designed to fit within this constraint.

    **HERE BE DRAGONS**: IN A PRODUCTION SYSTEM, THESE ENUMS SHOULD NOT BE CHANGED!!!
    """

    BIRTHDATE = 1, "Date of Birth"
    MRN = 2, "Last 4 chars of MRN"
    SEX = 3, "Sex"
    ZIP = 4, "Zip Code"
    FIRST_NAME = 5, "First 4 chars of First Name"
    LAST_NAME = 6, "First 4 chars of Last Name"
    ADDRESS = 7, "First 4 chars of Address"

    def __init__(self, id: int, description: str):
        self.id = id
        self.description = description

    @classmethod
    def from_id(cls, id: int):
        """
        Given an id, return the BlockingKey
        """
        for member in cls:
            if member.id == id:
                return member
        raise ValueError(f"No BlockingKey with id {id} found.")

    def to_value(self, record: PIIRecord) -> set[str]:
        """
        Given a data dictionary of Patient PII data, return a set of all
        possible values for this Key.  Many Keys will only have 1 possible value,
        but some (like first name) could have multiple values.
        """
        vals: set[str] = set()

        assert isinstance(record, PIIRecord), "Expected a PIIRecord object"

        if self == BlockingKey.BIRTHDATE:
            # NOTE: we could optimize here and remove the dashes from the date
            vals.update(record.field_iter(Feature.BIRTHDATE))
        elif self == BlockingKey.MRN:
            vals.update({x[-4:] for x in record.field_iter(Feature.MRN)})
        elif self == BlockingKey.SEX:
            vals.update(record.field_iter(Feature.SEX))
        elif self == BlockingKey.ZIP:
            vals.update(record.field_iter(Feature.ZIPCODE))
        elif self == BlockingKey.FIRST_NAME:
            vals.update({x[:4] for x in record.field_iter(Feature.FIRST_NAME)})
        elif self == BlockingKey.LAST_NAME:
            vals.update({x[:4] for x in record.field_iter(Feature.LAST_NAME)})
        elif self == BlockingKey.ADDRESS:
            vals.update({x[:4] for x in record.field_iter(Feature.ADDRESS)})

        # if any vals are longer than the BLOCKING_KEY_MAX_LENGTH, raise an error
        if any(len(x) > BLOCKING_VALUE_MAX_LENGTH for x in vals):
            raise RuntimeError(f"{self} has a value longer than {BLOCKING_VALUE_MAX_LENGTH}")
        return vals


class BlockingValue(Base):
    __tablename__ = "mpi_blocking_value"
    # create a composite index on patient_id, blockingkey and value
    __table_args__ = (
        schema.Index("idx_blocking_value_patient_key_value", "patient_id", "blockingkey", "value"),
    )

    id: orm.Mapped[int] = orm.mapped_column(get_bigint_pk(), autoincrement=True, primary_key=True)
    patient_id: orm.Mapped[int] = orm.mapped_column(schema.ForeignKey("mpi_patient.id"))
    patient: orm.Mapped["Patient"] = orm.relationship(back_populates="blocking_values")
    blockingkey: orm.Mapped[int] = orm.mapped_column(sqltypes.SmallInteger)
    value: orm.Mapped[str] = orm.mapped_column(sqltypes.String(BLOCKING_VALUE_MAX_LENGTH))
