"""
unit.linking.test_mpi_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains the unit tests for the recordlinker.linking.mpi_service module.
"""

import pytest

from recordlinker import models
from recordlinker.linking import mpi_service


@pytest.fixture(scope="function")
def new_patient(session):
    patient = models.Patient(person=models.Person(), data={})
    session.add(patient)
    session.flush()
    return patient


class TestInsertBlockingKeys:
    def test_patient_no_blocking_keys(self, session, new_patient):
        new_patient.data = {"name": []}
        assert mpi_service.insert_blocking_keys(session, new_patient) == []

    def test_patient_with_blocking_keys(self, session, new_patient):
        new_patient.data = {"name": [{"given": ["Johnathon", "Bill",], "family": "Smith"}], "birthdate": "1980-01-01"}
        keys = mpi_service.insert_blocking_keys(session, new_patient)
        assert len(keys) == 4
        for key in keys:
            assert keys[0].patient_id == new_patient.id
            if key.blockingkey == models.BlockingKey.BIRTHDATE.id:
                assert key.value == "1980-01-01"
            elif key.blockingkey == models.BlockingKey.FIRST_NAME.id:
                assert key.value in ["John", "Bill"]
            elif key.blockingkey == models.BlockingKey.LAST_NAME.id:
                assert key.value == "Smit"
            else:
                assert False, f"Unexpected blocking key: {key.blockingkey}"


class TestInsertPatient:
    def test_no_person(self, session):
        data = {"name": [{"given": ["Johnathon", "Bill",], "family": "Smith"}], "birthdate": "01/01/1980"}
        record = models.PIIRecord(**data)
        patient = mpi_service.insert_patient(session, record)
        assert patient.person_id is not None
        assert patient.data["birth_date"] == "1980-01-01"
        assert patient.data["name"] == [{"given": ["Johnathon", "Bill",], "family": "Smith"}]
        assert patient.external_person_id is None
        assert patient.external_person_source is None
        assert patient.person.internal_id is not None
        assert patient.person.id == patient.person_id
        assert len(patient.blocking_values) == 4

    def test_no_person_with_external_id(self, session):
        data = {"name": [{"given": ["Johnathon",], "family": "Smith"}], "birthdate": "01/01/1980"}
        record = models.PIIRecord(**data)
        patient = mpi_service.insert_patient(session, record, external_person_id="123456")
        assert patient.person_id is not None
        assert patient.data["birth_date"] == "1980-01-01"
        assert patient.data["name"] == [{"given": ["Johnathon",], "family": "Smith"}]
        assert patient.external_person_id == "123456"
        assert patient.external_person_source == "IRIS"
        assert patient.person.internal_id is not None
        assert patient.person.id is not None
        assert patient.person.id == patient.person_id
        assert len(patient.blocking_values) == 3

    def test_with_person(self, session):
        person = models.Person()
        session.add(person)
        session.flush()
        data = {"name": [{"given": ["George",], "family": "Harrison"}], "birthdate": "1943-2-25"}
        record = models.PIIRecord(**data)
        patient = mpi_service.insert_patient(session, record, person=person)
        assert patient.person_id == person.id
        assert patient.data["birth_date"] == "1943-02-25"
        assert patient.data["name"] == [{"given": ["George",], "family": "Harrison"}]
        assert patient.external_person_id is None
        assert patient.external_person_source is None
        assert len(patient.blocking_values) == 3

    def test_with_person_and_external_patient_id(self, session):
        person = models.Person()
        session.add(person)
        session.flush()
        data = {"name": [{"given": ["George",], "family": "Harrison"}]}
        record = models.PIIRecord(**data)
        patient = mpi_service.insert_patient(session, record, person=person, external_patient_id="abc")
        assert patient.person_id == person.id
        assert patient.data == data
        assert patient.external_patient_id == "abc"
        assert patient.external_person_id is None
        assert patient.external_person_source is None
        assert len(patient.blocking_values) == 2


class TestGetBlockData:
    @pytest.fixture
    def prime_index(self, session):
        data = [
            {"name": [{"given": ["Johnathon", "Bill",], "family": "Smith"}], "birthdate": "01/01/1980"},
            {"name": [{"given": ["George",], "family": "Harrison"}], "birthdate": "1943-2-25"},
            {"name": [{"given": ["John",], "family": "Doe"}, {"given": ["John"], "family": "Lewis"}], "birthdate": "1980-01-01"},
            {"name": [{"given": ["Bill",], "family": "Smith"}], "birthdate": "1980-01-01"},
            {"name": [{"given": ["John",], "family": "Smith"}], "birthdate": "1980-01-01"},
            {"name": [{"given": ["John",], "family": "Smith"}], "birthdate": "1985-11-12"},
            {"name": [{"given": ["Ferris",], "family": "Bueller"}], "birthdate": ""},
        ]
        for datum in data:
            mpi_service.insert_patient(session, models.PIIRecord(**datum))

    def test_block_invalid_key(self, session):
        data = {"name": [{"given": ["Johnathon", "Bill",], "family": "Smith"}]}
        #passing in a invalid id of -1 for a blocking key which should raise a value error
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[-1], evaluators={}, rule="", cluster_ratio=1.0, kwargs={})
        with pytest.raises(ValueError):
            mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)

    def test_block_missing_data(self, session, prime_index):
        data = {"name": [{"given": ["Johnathon", "Bill",], "family": "Smith"}]}
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[1], evaluators={}, rule="", cluster_ratio=1.0, kwargs={})
        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 0

    def test_block_empty_block_key(self, session, prime_index):
        data = {"name": [{"given": ["Ferris",], "family": "Bueller"}], "birthdate": ""}
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[1,5], evaluators={}, rule="", cluster_ratio=1.0, kwargs={})
        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 0

    def test_block_on_birthdate(self, session, prime_index):
        data = {"name": [{"given": ["Johnathon", "Bill",], "family": "Smith"}], "birthdate": "01/01/1980"}
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[1], evaluators={}, rule="", cluster_ratio=1.0, kwargs={})

        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 4
        data = {"name": [{"given": ["Johnathon", "Bill",], "family": "Smith"}], "birthdate": "11/12/1985"}
        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 1

    def test_block_on_first_name(self, session, prime_index):
        data = {"name": [{"given": ["Johnathon", "Bill",], "family": "Smith"}], "birthdate": "01/01/1980"}
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[5], evaluators={}, rule="", cluster_ratio=1.0, kwargs={})
        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 5

    def test_block_on_birthdate_and_first_name(self, session, prime_index):
        data = {"name": [{"given": ["Johnathon", "Bill",], "family": "Smith"}], "birthdate": "01/01/1980"}
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[1,5], evaluators={}, rule="", cluster_ratio=1.0, kwargs={})
        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 4

    def test_block_on_birthdate_first_name_and_last_name(self, session, prime_index):
        data = {"name": [{"given": ["Johnathon", "Bill",], "family": "Smith"}], "birthdate": "01/01/1980"}
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[1,5,6], evaluators={}, rule="", cluster_ratio=1.0, kwargs={})
        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 3
        data = {"name": [{"given": ["Billy",], "family": "Smitty"}], "birthdate": "Jan 1 1980"}
        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 2
        data = {"name": [{"given": ["Johnathon", "Bill",], "family": "Doeherty"}], "birthdate": "Jan 1 1980"}
        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 0

    def test_block_on_multiple_names(self, session, prime_index):
        data = {"name": [{"use": "official", "given": ["John", "Doe"], "family": "Smith"}, {"use": "maiden", "given": ["John"], "family": "Doe"}]}
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[5,6], evaluators={}, rule="", cluster_ratio=1.0, kwargs={})
        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 4

    def test_block_missing_keys(self, session, prime_index):
        data = {"birthdate": "01/01/1980"}
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[1,6], evaluators={}, rule="", cluster_ratio=1.0, kwargs={})
        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 0

    def test_block_on_duplicates(self, session):
        data = {"external_id": "d3ecb447-d05f-4ec1-8ef1-ce4bbda59a25", "birth_date": "1997-12-09", "sex": "F", "mrn": "7bb85f23-044b-1f92-3521-f2cf258601b0", "address": [{"line": ["783 Cronin Stravenue"], "city": "Los Angeles", "state": "CA", "postal_code": "90405", "country": "US", "latitude": 34.12688209447149, "longitude": -118.56442326530481, "extension": [{"url": "http://hl7.org/fhir/StructureDefinition/geolocation", "extension": [{"url": "latitude", "valueDecimal": 34.12688209447149}, {"url": "longitude", "valueDecimal": -118.56442326530481}]}]}], "name": [{"family": "Rodr\u00edguez701", "given": ["Lourdes258", "Blanca837"], "use": "official", "prefix": ["Ms."]}], "phone": [{"system": "phone", "value": "555-401-5073", "use": "home"}]}
        mpi_service.insert_patient(session, models.PIIRecord(**data))
        mpi_service.insert_patient(session, models.PIIRecord(**data))
        mpi_service.insert_patient(session, models.PIIRecord(**data))
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[5,6,4,3], evaluators={}, rule="", cluster_ratio=1.0, kwargs={})

        matches = mpi_service.get_block_data(session, models.PIIRecord(**data), algorithm_pass)
        assert len(matches) == 3
