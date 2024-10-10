"""
unit.models.test_mpi.py
~~~~~~~~~~~~~~~~~~~~~~~

This module contains the unit tests for the recordlinker.models.mpi module.
"""

import datetime

import pytest

from recordlinker import models


class TestPatient:
    def test_record_setter(self):
        patient = models.Patient()
        with pytest.raises(AssertionError):
            patient.record = "invalid"
        patient.record = models.PIIRecord()
        assert patient.data == {}
        patient.record = models.PIIRecord(birthDate="1980-01-01", sex="male")
        assert patient.data == {"birth_date": "1980-01-01", "sex": "M"}
        patient.record = models.PIIRecord(birthDate="1980-01-01", sex="male", mrn="", name=[])
        assert patient.data == {"birth_date": "1980-01-01", "sex": "M", "mrn": ""}


class TestBlockingKey:
    def test_extract_birthdate(self):
        rec = models.PIIRecord(**{"dob": "01/01/1980"})
        assert models.BlockingKey.BIRTHDATE.to_value(rec) == set()
        rec = models.PIIRecord(**{"birth_date": "1980-01-01"})
        assert models.BlockingKey.BIRTHDATE.to_value(rec) == {"1980-01-01"}
        rec = models.PIIRecord(**{"birthdate": datetime.date(1980, 1, 1)})
        assert models.BlockingKey.BIRTHDATE.to_value(rec) == {"1980-01-01"}
        rec = models.PIIRecord(**{"birthDate": "01/01/1980"})
        assert models.BlockingKey.BIRTHDATE.to_value(rec) == {"1980-01-01"}
        rec = models.PIIRecord(**{"birthDate": ""})
        assert models.BlockingKey.BIRTHDATE.to_value(rec) == set()

    def test_extract_mrn_last_four(self):
        rec = models.PIIRecord(**{"ssn": "123456789"})
        assert models.BlockingKey.MRN.to_value(rec) == set()
        rec = models.PIIRecord(**{"mrn": None})
        assert models.BlockingKey.MRN.to_value(rec) == set()
        rec = models.PIIRecord(**{"mrn": "123456789"})
        assert models.BlockingKey.MRN.to_value(rec) == {"6789"}
        rec = models.PIIRecord(**{"mrn": "89"})
        assert models.BlockingKey.MRN.to_value(rec) == {"89"}

    def test_extract_sex(self):
        rec = models.PIIRecord(**{"gender": "M"})
        assert models.BlockingKey.SEX.to_value(rec) == set()
        rec = models.PIIRecord(**{"sex": ""})
        assert models.BlockingKey.SEX.to_value(rec) == set()
        rec = models.PIIRecord(**{"sex": "M"})
        assert models.BlockingKey.SEX.to_value(rec) == {"M"}
        rec = models.PIIRecord(**{"sex": "Male"})
        assert models.BlockingKey.SEX.to_value(rec) == {"M"}
        rec = models.PIIRecord(**{"sex": "f"})
        assert models.BlockingKey.SEX.to_value(rec) == {"F"}
        rec = models.PIIRecord(**{"sex": "FEMALE"})
        assert models.BlockingKey.SEX.to_value(rec) == {"F"}
        rec = models.PIIRecord(**{"sex": "other"})
        assert models.BlockingKey.SEX.to_value(rec) == {"U"}
        rec = models.PIIRecord(**{"sex": "unknown"})
        assert models.BlockingKey.SEX.to_value(rec) == {"U"}
        rec = models.PIIRecord(**{"sex": "?"})
        assert models.BlockingKey.SEX.to_value(rec) == {"U"}

    def test_extract_zipcode(self):
        rec = models.PIIRecord(**{"zip_code": "12345"})
        assert models.BlockingKey.ZIP.to_value(rec) == set()
        rec = models.PIIRecord(**{"address": [{"postalCode": None}]})
        assert models.BlockingKey.ZIP.to_value(rec) == set()
        rec = models.PIIRecord(**{"address": [{"zipcode": "12345"}]})
        assert models.BlockingKey.ZIP.to_value(rec) == {"12345"}
        rec = models.PIIRecord(**{"address": [{"postal_code": "12345-6789"}]})
        assert models.BlockingKey.ZIP.to_value(rec) == {"12345"}
        rec = models.PIIRecord(**{"address": [{"zipCode": "12345-6789"}, {"zip": "54321"}]})
        assert models.BlockingKey.ZIP.to_value(rec) == {"12345", "54321"}

    def test_extract_first_name_first_four(self):
        rec = models.PIIRecord(**{"first_name": "John"})
        assert models.BlockingKey.FIRST_NAME.to_value(rec) == set()
        rec = models.PIIRecord(**{"name": [{"given": [""], "family": "Doe"}]})
        assert models.BlockingKey.FIRST_NAME.to_value(rec) == set()
        rec = models.PIIRecord(**{"name": [{"given": ["John", "Jane"], "family": "Doe"}]})
        assert models.BlockingKey.FIRST_NAME.to_value(rec) == {"John", "Jane"}
        rec = models.PIIRecord(**{
            "name": [
                {"given": ["Janet", "Johnathon"], "family": "Doe"},
                {"given": ["Jane"], "family": "Smith"},
            ]
        })
        assert models.BlockingKey.FIRST_NAME.to_value(rec) == {"Jane", "John"}

    def test_extract_last_name_first_four(self):
        rec = models.PIIRecord(**{"last_name": "Doe"})
        assert models.BlockingKey.LAST_NAME.to_value(rec) == set()
        rec = models.PIIRecord(**{"name": [{"family": ""}]})
        assert models.BlockingKey.LAST_NAME.to_value(rec) == set()
        rec = models.PIIRecord(**{"name": [{"family": "Doe"}]})
        assert models.BlockingKey.LAST_NAME.to_value(rec) == {"Doe"}
        rec = models.PIIRecord(**{"name": [{"family": "Smith"}, {"family": "Doe"}]})
        assert models.BlockingKey.LAST_NAME.to_value(rec) == {"Smit", "Doe"}

    def test_extract_address_first_four(self):
        rec = models.PIIRecord(**{"line": "123 Main St"})
        assert models.BlockingKey.ADDRESS.to_value(rec) == set()
        rec = models.PIIRecord(**{"address": [{"line": ["123 Main St"]}]})
        assert models.BlockingKey.ADDRESS.to_value(rec) == {"123 "}
        rec = models.PIIRecord(**{"address": [{"line": ["123 Main St", "Apt 2"]}]})
        assert models.BlockingKey.ADDRESS.to_value(rec) == {"123 "}
        rec = models.PIIRecord(**{"address": [{"line": ["123 Main St"]}, {"line": ["456 Elm St"]}]})
        assert models.BlockingKey.ADDRESS.to_value(rec) == {"123 ", "456 "}