"""
unit.models.test_mpi.py
~~~~~~~~~~~~~~~~~~~~~~~

This module contains the unit tests for the recordlinker.models.mpi module.
"""

import datetime

import pytest

from recordlinker import models
from recordlinker.schemas import pii


class TestPatient:
    def test_record_setter(self):
        patient = models.Patient()
        with pytest.raises(AssertionError):
            patient.record = "invalid"
        patient.record = pii.PIIRecord()
        assert patient.data == {}
        patient.record = pii.PIIRecord(birthDate="1980-01-01", sex="male")
        assert patient.data == {"birth_date": "1980-01-01", "sex": "M"}
        patient.record = pii.PIIRecord(birthDate="1980-01-01", sex="male", mrn="", name=[])
        assert patient.data == {"birth_date": "1980-01-01", "sex": "M", "mrn": ""}
