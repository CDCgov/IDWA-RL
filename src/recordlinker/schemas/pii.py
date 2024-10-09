import datetime
import enum
import typing

import dateutil.parser
import pydantic

from recordlinker import models


class Feature(enum.Enum):
    """
    Enum for the different Patient attributes that can be used for comparison.
    """

    BIRTHDATE = "birthdate"
    MRN = "mrn"
    SEX = "sex"
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    ADDRESS = "address"
    CITY = "city"
    STATE = "state"
    ZIPCODE = "zip"

    def __str__(self):
        """
        Return the value of the enum as a string.
        """
        return self.value


class Sex(enum.Enum):
    """
    Enum for the Patient.sex field.
    """

    MALE = "M"
    FEMALE = "F"
    UNKNOWN = "U"

    def __str__(self):
        """
        Return the value of the enum as a string.
        """
        return self.value


class Name(pydantic.BaseModel):
    """
    The schema for a name record.
    """

    model_config = pydantic.ConfigDict(extra="allow")

    family: str
    given: typing.List[str] = []
    use: typing.Optional[str] = None
    prefix: typing.List[str] = []  # future use
    suffix: typing.List[str] = []  # future use


class Address(pydantic.BaseModel):
    """
    The schema for an address record.
    """

    model_config = pydantic.ConfigDict(extra="allow")

    line: typing.List[str] = []
    city: typing.Optional[str] = None
    state: typing.Optional[str] = None
    postal_code: typing.Optional[str] = pydantic.Field(
        default=None,
        validation_alias=pydantic.AliasChoices(
            "postal_code", "postalcode", "postalCode", "zip_code", "zipcode", "zipCode", "zip"
        ),
    )
    county: typing.Optional[str] = None  # future use
    country: typing.Optional[str] = None
    latitude: typing.Optional[float] = None
    longitude: typing.Optional[float] = None


class Telecom(pydantic.BaseModel):
    """
    The schema for a telecom record.
    """

    model_config = pydantic.ConfigDict(extra="allow")

    value: str  # future use
    system: typing.Optional[str] = None
    use: typing.Optional[str] = None


class PIIRecord(pydantic.BaseModel):
    """
    The schema for a PII record.
    """

    model_config = pydantic.ConfigDict(extra="allow")

    external_id: typing.Optional[str] = None
    birth_date: typing.Optional[datetime.date] = pydantic.Field(
        default=None, validation_alias=pydantic.AliasChoices("birth_date", "birthdate", "birthDate")
    )
    sex: typing.Optional[Sex] = None
    mrn: typing.Optional[str] = None
    address: typing.List[Address] = []
    name: typing.List[Name] = []
    telecom: typing.List[Telecom] = []

    @classmethod
    def model_construct(cls, _fields_set: set[str] | None = None, **values: typing.Any) -> typing.Self:
        """
        Construct a PIIRecord object from a dictionary. This is similar to the
        `pydantic.BaseModel.models_construct` method, but allows for additional parsing
        of nested objects.  The key difference between this and the __init__ constructor
        is this method will not parse and validate the data, thus should only be used
        when the data is already cleaned and validated.
        """
        obj = super(PIIRecord, cls).model_construct(_fields_set=_fields_set, **values)
        obj.address = [Address.model_construct(**a) for a in values.get("address", [])]
        obj.name = [Name.model_construct(**n) for n in values.get("name", [])]
        obj.telecom = [Telecom.model_construct(**t) for t in values.get("telecom", [])]
        return obj

    @pydantic.field_validator("external_id", mode="before")
    def parse_external_id(cls, value):
        """
        Parse the external_id object into a string
        """
        if value:
            return str(value)

    @pydantic.field_validator("birth_date", mode="before")
    def parse_birth_date(cls, value):
        """
        Parse the birthdate string into a datetime object.
        """
        if value:
            return dateutil.parser.parse(str(value))

    @pydantic.field_validator("sex", mode="before")
    def parse_sex(cls, value):
        """
        Parse the
        """
        if value:
            val = str(value).lower().strip()
            if val in ["m", "male"]:
                return Sex.MALE
            elif val in ["f", "female"]:
                return Sex.FEMALE
            return Sex.UNKNOWN

    def field_iter(self, feature: Feature) -> typing.Iterator[str]:
        """
        Given a field name, return an iterator of all string values for that field.
        Empty strings are not included in the iterator.
        """
        if not isinstance(feature, Feature):
            raise ValueError(f"Invalid feature: {feature}")

        if feature == Feature.BIRTHDATE:
            if self.birth_date:
                yield str(self.birth_date)
        elif feature == Feature.MRN:
            if self.mrn:
                yield self.mrn
        elif feature == Feature.SEX:
            if self.sex:
                yield str(self.sex)
        elif feature == Feature.ADDRESS:
            for address in self.address:
                # The 2nd, 3rd, etc lines of an address are not as important as
                # the first line, so we only include the first line in the comparison.
                if address.line and address.line[0]:
                    yield address.line[0]
        elif feature == Feature.CITY:
            for address in self.address:
                if address.city:
                    yield address.city
        elif feature == Feature.STATE:
            for address in self.address:
                if address.state:
                    yield address.state
        elif feature == Feature.ZIPCODE:
            for address in self.address:
                if address.postal_code:
                    # only use the first 5 digits for comparison
                    yield address.postal_code[:5]
        elif feature == Feature.FIRST_NAME:
            for name in self.name:
                for given in name.given:
                    if given:
                        yield given
        elif feature == Feature.LAST_NAME:
            for name in self.name:
                if name.family:
                    yield name.family

    def blocking_keys(self, key: models.BlockingKey) -> set[str]:
        """
        For a particular Feature, return a set of all possible Blocking Key values
        for this record.  Many keys will only have 1 possible value, but some (like
        first name) could have multiple values.
        """
        vals: set[str] = set()

        if not isinstance(key, models.BlockingKey):
            raise ValueError(f"Invalid BlockingKey: {key}")

        if key == models.BlockingKey.BIRTHDATE:
            # NOTE: we could optimize here and remove the dashes from the date
            vals.update(self.field_iter(Feature.BIRTHDATE))
        elif key == models.BlockingKey.MRN:
            vals.update({x[-4:] for x in self.field_iter(Feature.MRN)})
        elif key == models.BlockingKey.SEX:
            vals.update(self.field_iter(Feature.SEX))
        elif key == models.BlockingKey.ZIP:
            vals.update(self.field_iter(Feature.ZIPCODE))
        elif key == models.BlockingKey.FIRST_NAME:
            vals.update({x[:4] for x in self.field_iter(Feature.FIRST_NAME)})
        elif key == models.BlockingKey.LAST_NAME:
            vals.update({x[:4] for x in self.field_iter(Feature.LAST_NAME)})
        elif key == models.BlockingKey.ADDRESS:
            vals.update({x[:4] for x in self.field_iter(Feature.ADDRESS)})

        # if any vals are longer than the BLOCKING_KEY_MAX_LENGTH, raise an error
        if any(len(x) > models.BLOCKING_VALUE_MAX_LENGTH for x in vals):
            raise RuntimeError(f"{self} has a value longer than {models.BLOCKING_VALUE_MAX_LENGTH}")
        return vals
