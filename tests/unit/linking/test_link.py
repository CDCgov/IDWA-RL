"""
unit.linking.test_link.py
~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains the unit tests for the recordlinker.linking.link module.
"""

import collections
import copy
import uuid

import pytest

from recordlinker import models
from recordlinker import utils
from recordlinker.linking import link


class TestAddPersonResource:
    def test_add_person_resource(self):
        bundle = utils.read_json_from_assets("general", "patient_bundle.json")
        raw_bundle = copy.deepcopy(bundle)
        patient_id = "TEST_PATIENT_ID"
        person_id = "TEST_PERSON_ID"

        returned_bundle = link.add_person_resource(
            person_id=person_id, patient_id=patient_id, bundle=raw_bundle
        )

        # Assert returned_bundle has added element in "entry"
        assert len(returned_bundle.get("entry")) == len(bundle.get("entry")) + 1

        # Assert the added element is the person_resource bundle
        assert (
            returned_bundle.get("entry")[-1].get("resource").get("resourceType") == "Person"
        )
        assert (
            returned_bundle.get("entry")[-1].get("request").get("url")
            == "Person/TEST_PERSON_ID"
        )


class TestCompare:
    def test_compare_match(self):
        rec = models.PIIRecord(
            **{
                "name": [
                    {
                        "given": [
                            "John",
                        ],
                        "family": "Doe",
                    }
                ]
            }
        )
        pat = models.Patient(
            data={
                "name": [
                    {
                        "given": [
                            "John",
                        ],
                        "family": "Doey",
                    }
                ]
            }
        )

        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[1], evaluators={"first_name": "func:recordlinker.linking.matchers.feature_match_exact", "last_name": "func:recordlinker.linking.matchers.feature_match_fuzzy_string"}, rule="func:recordlinker.linking.matchers.eval_perfect_match", cluster_ratio=1.0, kwargs={})

        assert link.compare(rec, pat, algorithm_pass) is True

    def test_compare_no_match(self):
        rec = models.PIIRecord(
            **{
                "name": [
                    {
                        "given": [
                            "John",
                        ],
                        "family": "Doe",
                    }
                ]
            }
        )
        pat = models.Patient(
            data={
                "name": [
                    {
                        "given": [
                            "John",
                        ],
                        "family": "Doey",
                    }
                ]
            }
        )
        algorithm_pass = models.AlgorithmPass(id=1, algorithm_id=1, blocking_keys=[1], evaluators={"first_name": "func:recordlinker.linking.matchers.feature_match_exact", "last_name": "func:recordlinker.linking.matchers.feature_match_exact"}, rule="func:recordlinker.linking.matchers.eval_perfect_match", cluster_ratio=1.0, kwargs={})

        assert link.compare(rec, pat, algorithm_pass) is False


class TestLinkRecordAgainstMpi:
    @pytest.fixture
    def patients(self):
        bundle = utils.read_json_from_assets("linking", "patient_bundle_to_link_with_mpi.json")
        patients = []
        for entry in bundle["entry"]:
            if entry.get("resource", {}).get("resourceType", {}) == "Patient":
                patients.append(entry["resource"])
        return patients

    def test_basic_match_one(self, session, basic_algorithm, patients):
        # Test various null data values in incoming record
        matches: list[bool] = []
        mapped_patients: dict[str, int] = collections.defaultdict(int)
        for idx, patient in enumerate(patients[:2]):
            matched, pid = link.link_record_against_mpi(patient, session, basic_algorithm)
            matches.append(matched)
            mapped_patients[pid] += 1

        # First patient inserted into empty MPI, no match
        # Second patient blocks with first patient in first pass, then fuzzy matches name
        assert matches == [False, True]
        assert sorted(list(mapped_patients.values())) == [2]

    def test_basic_match_two(self, session, basic_algorithm, patients):
        matches: list[bool] = []
        mapped_patients: dict[str, int] = collections.defaultdict(int)
        for patient in patients:
            matched, pid = link.link_record_against_mpi(patient, session, basic_algorithm)
            matches.append(matched)
            mapped_patients[pid] += 1

        # First patient inserted into empty MPI, no match
        # Second patient blocks with first patient in first pass, then fuzzy matches name
        # Third patient is entirely new individual, no match
        # Fourth patient fails blocking in first pass, blocks with first patient in second
        # pass, then fuzzy matches on address and exact matches on birthdate, joins cluster
        # with first and second patient
        # Fifth patient: fails blocking in first and second pass, no match
        # Sixth patient: fails blocking in first pass, blocks with fifth patient in second pass,
        # then matches on birthdate but fails on address, no match
        assert matches == [False, True, False, True, False, False]
        assert sorted(list(mapped_patients.values())) == [1, 1, 1, 3]

    def test_enhanced_match_three(self, session, enhanced_algorithm, patients):
        # add an additional patient that will fuzzy match to patient 0
        patient0_copy = copy.deepcopy(patients[0])
        patient0_copy["id"] = str(uuid.uuid4())
        patient0_copy["name"][0]["given"][0] = "Jhon"
        patients.append(patient0_copy)
        matches: list[bool] = []
        mapped_patients: dict[str, int] = collections.defaultdict(int)
        for patient in patients:
            matched, pid = link.link_record_against_mpi(patient, session, enhanced_algorithm)
            matches.append(matched)
            mapped_patients[pid] += 1

        # First patient inserted into empty MPI, no match
        # Second patient blocks with first patient in first pass, then fuzzy matches name
        # Third patient is entirely new individual, no match
        # Fourth patient fails blocking with first pass but catches on second, fuzzy matches
        # Fifth patient: in first pass MRN blocks with one cluster but fails name,
        #  in second pass name blocks with different cluster but fails address, no match
        # Sixth patient: in first pass, MRN blocks with one cluster and name matches in it,
        # in second pass name blocks on different cluster and address matches it,
        #  finds greatest strength match and correctly assigns to larger cluster
        assert matches == [False, True, False, True, False, False, True]
        assert sorted(list(mapped_patients.values())) == [1, 1, 1, 4]