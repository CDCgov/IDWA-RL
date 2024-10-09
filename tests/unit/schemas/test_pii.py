"""
unit.schemas.test_pii.py
~~~~~~~~~~~~~~~~~~~~~~~~

This module contains the unit tests for the recordlinker.schemas.pii module.
"""

import datetime
import uuid

import pydantic
import pytest

from recordlinker.schemas import pii
from recordlinker.models import BlockingKey


class TestPIIRecord:
    def test_moddel_construct(self):
        data = {
            "mrn": "99",
            "birth_date": "1980-2-1",
            "name": [{"family": "Doe", "given": ["John", "L"]}, {"family": "Smith", "given": ["Jane"]}],
            "address": [
                {
                    "line": ["123 Main St"],
                    "city": "Anytown",
                    "state": "NY",
                    "postalCode": "12345",
                    "country": "US",
                },
                {
                    "line": ["456 Elm St", "Apt 2"],
                    "city": "Somecity",
                    "state": "CA",
                    "postal_code": "98765-4321",
                    "country": "US",
                },
            ],
            "telecom": [{"value": "555-123-4567"}, {"value": "555-987-6543"}],
        }
        record = pii.PIIRecord.model_construct(**data)
        assert record.mrn == "99"
        assert record.birth_date == "1980-2-1"
        assert record.name[0].family == "Doe"
        assert record.name[0].given == ["John", "L"]
        assert record.name[1].family == "Smith"
        assert record.name[1].given == ["Jane"]
        assert record.address[0].line == ["123 Main St"]
        assert record.address[0].city == "Anytown"
        assert record.address[0].state == "NY"
        assert record.address[0].postal_code == "12345"
        assert record.address[1].line == ["456 Elm St", "Apt 2"]
        assert record.address[1].city == "Somecity"
        assert record.address[1].state == "CA"
        assert record.address[1].postal_code == "98765-4321"

    def test_parse_external_id(self):
        record = pii.PIIRecord(
            external_id=uuid.UUID("7ca699d9-1986-4c0c-a0fd-ac4ae0dfa297")
        )
        assert record.external_id == "7ca699d9-1986-4c0c-a0fd-ac4ae0dfa297"
        record = pii.PIIRecord(external_id=12345)
        assert record.external_id == "12345"
        record = pii.PIIRecord(external_id="12345")
        assert record.external_id == "12345"
        record = pii.PIIRecord()
        assert record.external_id is None

    def test_parse_birthdate(self):
        record = pii.PIIRecord(birthDate="1980-01-01")
        assert record.birth_date == datetime.date(1980, 1, 1)
        record = pii.PIIRecord(birthDate="January 1, 1980")
        assert record.birth_date == datetime.date(1980, 1, 1)
        record = pii.PIIRecord(birth_date="Jan 1 1980")
        assert record.birth_date == datetime.date(1980, 1, 1)
        record = pii.PIIRecord(birth_date="1/1/1980")
        assert record.birth_date == datetime.date(1980, 1, 1)
        record = pii.PIIRecord()
        assert record.birth_date is None

    def test_parse_invalid_birthdate(self):
        with pytest.raises(pydantic.ValidationError):
            pii.PIIRecord(birth_date="1 de enero de 1980")

    def test_parse_sex(self):
        record = pii.PIIRecord(sex="M")
        assert record.sex == pii.Sex.MALE
        record = pii.PIIRecord(sex="m")
        assert record.sex == pii.Sex.MALE
        record = pii.PIIRecord(sex="Male")
        assert record.sex == pii.Sex.MALE
        record = pii.PIIRecord(sex="F")
        assert record.sex == pii.Sex.FEMALE
        record = pii.PIIRecord(sex="f")
        assert record.sex == pii.Sex.FEMALE
        record = pii.PIIRecord(sex="FEMALE")
        assert record.sex == pii.Sex.FEMALE
        record = pii.PIIRecord(sex="U")
        assert record.sex == pii.Sex.UNKNOWN
        record = pii.PIIRecord(sex="Unknown")
        assert record.sex == pii.Sex.UNKNOWN
        record = pii.PIIRecord()
        assert record.sex is None

    def test_field_iter(self):
        record = pii.PIIRecord(
            external_id="99",
            birth_date="1980-2-1",
            sex="male",
            mrn="123456",
            address=[
                pii.Address(
                    line=["123 Main St"],
                    city="Anytown",
                    state="NY",
                    postalCode="12345",
                    country="US",
                ),
                pii.Address(
                    line=["456 Elm St", "Apt 2"],
                    city="Somecity",
                    state="CA",
                    postal_code="98765-4321",
                    country="US",
                ),
            ],
            name=[
                pii.Name(family="Doe", given=["John", "L"]),
                pii.Name(family="Smith", given=["Jane"]),
            ],
            telecom=[
                pii.Telecom(value="555-123-4567"),
                pii.Telecom(value="555-987-6543"),
            ],
        )

        with pytest.raises(ValueError):
            list(record.field_iter("external_id"))

        assert list(record.field_iter(pii.Feature.BIRTHDATE)) == ["1980-02-01"]
        assert list(record.field_iter(pii.Feature.MRN)) == ["123456"]
        assert list(record.field_iter(pii.Feature.SEX)) == ["M"]
        assert list(record.field_iter(pii.Feature.ADDRESS)) == ["123 Main St", "456 Elm St"]
        assert list(record.field_iter(pii.Feature.CITY)) == ["Anytown", "Somecity"]
        assert list(record.field_iter(pii.Feature.STATE)) == ["NY", "CA"]
        assert list(record.field_iter(pii.Feature.ZIPCODE)) == ["12345", "98765"]
        assert list(record.field_iter(pii.Feature.FIRST_NAME)) == ["John", "L", "Jane"]
        assert list(record.field_iter(pii.Feature.LAST_NAME)) == ["Doe", "Smith"]
        assert list(record.field_iter(pii.Feature.ADDRESS)) == ["123 Main St", "456 Elm St"]

    def test_blocking_keys_birthdate(self):
        rec = pii.PIIRecord(**{"dob": "01/01/1980"})
        assert rec.blocking_keys(BlockingKey.BIRTHDATE) == set()
        rec = pii.PIIRecord(**{"birth_date": "1980-01-01"})
        assert rec.blocking_keys(BlockingKey.BIRTHDATE) == {"1980-01-01"}
        rec = pii.PIIRecord(**{"birthdate": datetime.date(1980, 1, 1)})
        assert rec.blocking_keys(BlockingKey.BIRTHDATE) == {"1980-01-01"}
        rec = pii.PIIRecord(**{"birthDate": "01/01/1980"})
        assert rec.blocking_keys(BlockingKey.BIRTHDATE) == {"1980-01-01"}
        rec = pii.PIIRecord(**{"birthDate": ""})
        assert rec.blocking_keys(BlockingKey.BIRTHDATE) == set()

    def test_blocking_keys_mrn_last_four(self):
        rec = pii.PIIRecord(**{"ssn": "123456789"})
        assert rec.blocking_keys(BlockingKey.MRN) == set()
        rec = pii.PIIRecord(**{"mrn": None})
        assert rec.blocking_keys(BlockingKey.MRN) == set()
        rec = pii.PIIRecord(**{"mrn": "123456789"})
        assert rec.blocking_keys(BlockingKey.MRN) == {"6789"}
        rec = pii.PIIRecord(**{"mrn": "89"})
        assert rec.blocking_keys(BlockingKey.MRN) == {"89"}

    def test_blocking_keys_sex(self):
        rec = pii.PIIRecord(**{"gender": "M"})
        assert rec.blocking_keys(BlockingKey.SEX) == set()
        rec = pii.PIIRecord(**{"sex": ""})
        assert rec.blocking_keys(BlockingKey.SEX) == set()
        rec = pii.PIIRecord(**{"sex": "M"})
        assert rec.blocking_keys(BlockingKey.SEX) == {"M"}
        rec = pii.PIIRecord(**{"sex": "Male"})
        assert rec.blocking_keys(BlockingKey.SEX) == {"M"}
        rec = pii.PIIRecord(**{"sex": "f"})
        assert rec.blocking_keys(BlockingKey.SEX) == {"F"}
        rec = pii.PIIRecord(**{"sex": "FEMALE"})
        assert rec.blocking_keys(BlockingKey.SEX) == {"F"}
        rec = pii.PIIRecord(**{"sex": "other"})
        assert rec.blocking_keys(BlockingKey.SEX) == {"U"}
        rec = pii.PIIRecord(**{"sex": "unknown"})
        assert rec.blocking_keys(BlockingKey.SEX) == {"U"}
        rec = pii.PIIRecord(**{"sex": "?"})
        assert rec.blocking_keys(BlockingKey.SEX) == {"U"}

    def test_blocking_keys_zipcode(self):
        rec = pii.PIIRecord(**{"zip_code": "12345"})
        assert rec.blocking_keys(BlockingKey.ZIP) == set()
        rec = pii.PIIRecord(**{"address": [{"postalCode": None}]})
        assert rec.blocking_keys(BlockingKey.ZIP) == set()
        rec = pii.PIIRecord(**{"address": [{"zipcode": "12345"}]})
        assert rec.blocking_keys(BlockingKey.ZIP) == {"12345"}
        rec = pii.PIIRecord(**{"address": [{"postal_code": "12345-6789"}]})
        assert rec.blocking_keys(BlockingKey.ZIP) == {"12345"}
        rec = pii.PIIRecord(**{"address": [{"zipCode": "12345-6789"}, {"zip": "54321"}]})
        assert rec.blocking_keys(BlockingKey.ZIP) == {"12345", "54321"}

    def test_blocking_keys_first_name_first_four(self):
        rec = pii.PIIRecord(**{"first_name": "John"})
        assert rec.blocking_keys(BlockingKey.FIRST_NAME) == set()
        rec = pii.PIIRecord(**{"name": [{"given": [""], "family": "Doe"}]})
        assert rec.blocking_keys(BlockingKey.FIRST_NAME) == set()
        rec = pii.PIIRecord(**{"name": [{"given": ["John", "Jane"], "family": "Doe"}]})
        assert rec.blocking_keys(BlockingKey.FIRST_NAME) == {"John", "Jane"}
        rec = pii.PIIRecord(**{
            "name": [
                {"given": ["Janet", "Johnathon"], "family": "Doe"},
                {"given": ["Jane"], "family": "Smith"},
            ]
        })
        assert rec.blocking_keys(BlockingKey.FIRST_NAME) == {"Jane", "John"}

    def test_blocking_keys_last_name_first_four(self):
        rec = pii.PIIRecord(**{"last_name": "Doe"})
        assert rec.blocking_keys(BlockingKey.LAST_NAME) == set()
        rec = pii.PIIRecord(**{"name": [{"family": ""}]})
        assert rec.blocking_keys(BlockingKey.LAST_NAME) == set()
        rec = pii.PIIRecord(**{"name": [{"family": "Doe"}]})
        assert rec.blocking_keys(BlockingKey.LAST_NAME) == {"Doe"}
        rec = pii.PIIRecord(**{"name": [{"family": "Smith"}, {"family": "Doe"}]})
        assert rec.blocking_keys(BlockingKey.LAST_NAME) == {"Smit", "Doe"}

    def test_blocking_keys_address_first_four(self):
        rec = pii.PIIRecord(**{"line": "123 Main St"})
        assert rec.blocking_keys(BlockingKey.ADDRESS) == set()
        rec = pii.PIIRecord(**{"address": [{"line": ["123 Main St"]}]})
        assert rec.blocking_keys(BlockingKey.ADDRESS) == {"123 "}
        rec = pii.PIIRecord(**{"address": [{"line": ["123 Main St", "Apt 2"]}]})
        assert rec.blocking_keys(BlockingKey.ADDRESS) == {"123 "}
        rec = pii.PIIRecord(**{"address": [{"line": ["123 Main St"]}, {"line": ["456 Elm St"]}]})
        assert rec.blocking_keys(BlockingKey.ADDRESS) == {"123 ", "456 "}
