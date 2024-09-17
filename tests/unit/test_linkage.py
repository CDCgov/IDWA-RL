import copy
import json
import os
import pathlib
import uuid
from json.decoder import JSONDecodeError

import pytest
from sqlalchemy import select
from sqlalchemy import text

from recordlinker.linkage import matchers
from recordlinker.linkage.algorithms import DIBBS_BASIC
from recordlinker.linkage.algorithms import DIBBS_ENHANCED
from recordlinker.linkage.dal import DataAccessLayer
from recordlinker.linkage.link import _compare_address_elements
from recordlinker.linkage.link import _compare_name_elements
from recordlinker.linkage.link import _condense_extract_address_from_resource
from recordlinker.linkage.link import _convert_given_name_to_first_name
from recordlinker.linkage.link import _flatten_patient_resource
from recordlinker.linkage.link import add_person_resource
from recordlinker.linkage.link import extract_blocking_values_from_record
from recordlinker.linkage.link import generate_hash_str
from recordlinker.linkage.link import link_record_against_mpi
from recordlinker.linkage.link import load_json_probs
from recordlinker.linkage.link import read_linkage_config
from recordlinker.linkage.link import score_linkage_vs_truth
from recordlinker.linkage.link import write_linkage_config
from recordlinker.linkage.mpi import DIBBsMPIConnectorClient
from recordlinker.utils import _clean_up


def _init_db() -> DataAccessLayer:
    os.environ = {
        "mpi_dbname": "testdb",
        "mpi_user": "postgres",
        "mpi_password": "pw",
        "mpi_host": "localhost",
        "mpi_port": "5432",
        "mpi_db_type": "postgres",
    }

    dal = DataAccessLayer()
    dal.get_connection(
        engine_url="postgresql+psycopg2://postgres:pw@localhost:5432/testdb"
    )
    _clean_up(dal)

    # load ddl
    schema_ddl = open(
        pathlib.Path(__file__).parent.parent.parent
        / "migrations"
        / "V01_01__flat_schema.sql"
    ).read()

    try:
        with dal.engine.connect() as db_conn:
            db_conn.execute(text(schema_ddl))
            db_conn.commit()
    except Exception as e:
        print(e)
        with dal.engine.connect() as db_conn:
            db_conn.rollback()
    dal.initialize_schema()

    return DIBBsMPIConnectorClient()


def test_extract_blocking_values_from_record():
    bundle = json.load(
        open(
            pathlib.Path(__file__).parent.parent.parent
            / "assets"
            / "general"
            / "patient_bundle.json"
        )
    )
    patient = [
        r.get("resource")
        for r in bundle.get("entry")
        if r.get("resource", {}).get("resourceType") == "Patient"
    ][0]
    patient["name"][0]["family"] = "Shepard"

    with pytest.raises(KeyError) as e:
        extract_blocking_values_from_record(patient, {"invalid"})
    assert "Input dictionary for block" in str(e.value)

    with pytest.raises(ValueError) as e:
        extract_blocking_values_from_record(patient, [{"value": "invalid"}])
    assert "is not a supported extraction field" in str(e.value)

    with pytest.raises(ValueError) as e:
        extract_blocking_values_from_record(
            patient, [{"value": "first_name", "transformation": "invalid_transform"}]
        )
    assert "Transformation invalid_transform is not valid" in str(e.value)

    blocking_fields = [
        {"value": "first_name", "transformation": "first4"},
        {"value": "last_name", "transformation": "first4"},
        {"value": "zip"},
        {"value": "city"},
        {"value": "birthdate"},
        {"value": "sex"},
        {"value": "state"},
        {"value": "address", "transformation": "last4"},
    ]
    blocking_vals = extract_blocking_values_from_record(
        patient,
        blocking_fields,
    )
    assert blocking_vals == {
        "first_name": {"value": "John", "transformation": "first4"},
        "last_name": {"value": "Shep", "transformation": "first4"},
        "zip": {"value": "10001-0001"},
        "city": {"value": "Faketon"},
        "birthdate": {"value": "1983-02-01"},
        "sex": {"value": "female"},
        "state": {"value": "NY"},
        "address": {"value": "e St", "transformation": "last4"},
    }

    patient["birthDate"] = ""
    patient["name"][0]["family"] = None

    blocking_vals = extract_blocking_values_from_record(
        patient,
        blocking_fields,
    )
    assert blocking_vals == {
        "first_name": {"value": "John", "transformation": "first4"},
        "zip": {"value": "10001-0001"},
        "city": {"value": "Faketon"},
        "sex": {"value": "female"},
        "state": {"value": "NY"},
        "address": {"value": "e St", "transformation": "last4"},
    }


def test_generate_hash():
    salt_str = "super-legit-salt"
    patient_1 = (
        "John-Shepard-2153/11/07-1234 Silversun Strip Boston Massachusetts 99999"
    )
    patient_2 = "Tali-Zora-Vas-Normandy-2160/05/14-PO Box 1 Rock Rannoch"

    hash_1 = generate_hash_str(patient_1, salt_str)
    hash_2 = generate_hash_str(patient_2, salt_str)

    assert hash_1 == "b124335071679e95341b8133669f6ab475f211f3e19d3cf69e7b6f13b0df45d6"
    assert hash_2 == "102818c623290c24069beb721c6eb465d281b3b67ecfb6aef924d14affa117b9"



def test_score_linkage_vs_truth():
    num_records = 12
    matches = {
        1: {5, 11, 12, 13},
        5: {11, 12, 13},
        11: {12, 13},
        12: {13},
        23: {24, 31, 32},
        24: {31, 32},
        31: {32},
    }
    true_matches = {
        1: {5, 11, 12},
        5: {11, 12},
        11: {12},
        23: {24, 31, 32},
        24: {31, 32},
        31: {32},
    }
    sensitivity, specificity, ppv, f1 = score_linkage_vs_truth(
        matches, true_matches, num_records
    )
    assert sensitivity == 1.0
    assert specificity == 0.926
    assert ppv == 0.75
    assert f1 == 0.857

    cluster_mode_matches = {1: {5, 11, 12, 13}, 23: {24, 31, 32}}
    sensitivity, specificity, ppv, f1 = score_linkage_vs_truth(
        cluster_mode_matches, true_matches, num_records, True
    )
    assert sensitivity == 1.0
    assert specificity == 0.926
    assert ppv == 0.75
    assert f1 == 0.857


def test_load_json_probs_errors():
    with pytest.raises(FileNotFoundError) as e:
        load_json_probs("does_not_exist.json")
    assert "specified file does not exist at" in str(e.value)

    with open("not_valid_json.json", "w") as file:
        file.write("I am not valid JSON")
    with pytest.raises(JSONDecodeError) as e:
        load_json_probs("not_valid_json.json")
    assert "specified file is not valid JSON" in str(e.value)

    os.remove("not_valid_json.json")




def test_algo_read():
    dibbs_basic_algo = read_linkage_config(
        pathlib.Path(__file__).parent.parent.parent
        / "assets"
        / "linkage"
        / "dibbs_basic_algorithm.json"
    )
    assert dibbs_basic_algo == [
        {
            "funcs": {
                "first_name": "func:recordlinker.linkage.matchers.feature_match_fuzzy_string",
                "last_name": "func:recordlinker.linkage.matchers.feature_match_exact",
            },
            "blocks": [
                {"value": "birthdate"},
                {"value": "mrn", "transformation": "last4"},
                {"value": "sex"},
            ],
            "matching_rule": "func:recordlinker.linkage.matchers.eval_perfect_match",
            "cluster_ratio": 0.9,
            "kwargs": {
                "thresholds": {
                    "first_name": 0.9,
                    "last_name": 0.9,
                    "birthdate": 0.95,
                    "address": 0.9,
                    "city": 0.92,
                    "zip": 0.95,
                }
            },
        },
        {
            "funcs": {
                "address": "func:recordlinker.linkage.matchers.feature_match_fuzzy_string",
                "birthdate": "func:recordlinker.linkage.matchers.feature_match_exact",
            },
            "blocks": [
                {"value": "zip"},
                {"value": "first_name", "transformation": "first4"},
                {"value": "last_name", "transformation": "first4"},
                {"value": "sex"},
            ],
            "matching_rule": "func:recordlinker.linkage.matchers.eval_perfect_match",
            "cluster_ratio": 0.9,
            "kwargs": {
                "thresholds": {
                    "first_name": 0.9,
                    "last_name": 0.9,
                    "birthdate": 0.95,
                    "address": 0.9,
                    "city": 0.92,
                    "zip": 0.95,
                }
            },
        },
    ]

    dibbs_enhanced_algo = read_linkage_config(
        pathlib.Path(__file__).parent.parent.parent
        / "assets"
        / "linkage"
        / "dibbs_enhanced_algorithm.json"
    )
    assert dibbs_enhanced_algo == [
        {
            "funcs": {
                "first_name": "func:recordlinker.linkage.matchers.feature_match_log_odds_fuzzy_compare",
                "last_name": "func:recordlinker.linkage.matchers.feature_match_log_odds_fuzzy_compare",
            },
            "blocks": [
                {"value": "birthdate"},
                {"value": "mrn", "transformation": "last4"},
                {"value": "sex"},
            ],
            "matching_rule": "func:recordlinker.linkage.matchers.eval_log_odds_cutoff",
            "cluster_ratio": 0.9,
            "kwargs": {
                "similarity_measure": "JaroWinkler",
                "thresholds": {
                    "first_name": 0.9,
                    "last_name": 0.9,
                    "birthdate": 0.95,
                    "address": 0.9,
                    "city": 0.92,
                    "zip": 0.95,
                },
                "true_match_threshold": 12.2,
                "log_odds": {
                    "address": 8.438284928858774,
                    "birthdate": 10.126641103800338,
                    "city": 2.438553006137189,
                    "first_name": 6.849475906891162,
                    "last_name": 6.350720397426025,
                    "mrn": 0.3051262572525359,
                    "sex": 0.7510419059643679,
                    "state": 0.022376768992488694,
                    "zip": 4.975031471124867,
                },
            },
        },
        {
            "funcs": {
                "address": "func:recordlinker.linkage.matchers.feature_match_log_odds_fuzzy_compare",
                "birthdate": "func:recordlinker.linkage.matchers.feature_match_log_odds_fuzzy_compare",
            },
            "blocks": [
                {"value": "zip"},
                {"value": "first_name", "transformation": "first4"},
                {"value": "last_name", "transformation": "first4"},
                {"value": "sex"},
            ],
            "matching_rule": "func:recordlinker.linkage.matchers.eval_log_odds_cutoff",
            "cluster_ratio": 0.9,
            "kwargs": {
                "similarity_measure": "JaroWinkler",
                "thresholds": {
                    "first_name": 0.9,
                    "last_name": 0.9,
                    "birthdate": 0.95,
                    "address": 0.9,
                    "city": 0.92,
                    "zip": 0.95,
                },
                "true_match_threshold": 17.0,
                "log_odds": {
                    "address": 8.438284928858774,
                    "birthdate": 10.126641103800338,
                    "city": 2.438553006137189,
                    "first_name": 6.849475906891162,
                    "last_name": 6.350720397426025,
                    "mrn": 0.3051262572525359,
                    "sex": 0.7510419059643679,
                    "state": 0.022376768992488694,
                    "zip": 4.975031471124867,
                },
            },
        },
    ]


def test_read_algo_errors():
    with pytest.raises(FileNotFoundError) as e:
        read_linkage_config("invalid.json")
    assert "No file exists at path invalid.json." in str(e.value)
    with open("not_valid_json_test.json", "w") as fp:
        fp.write("this is a random string that is not in json format\n")
    with pytest.raises(JSONDecodeError) as e:
        read_linkage_config("not_valid_json_test.json")
    assert "The specified file is not valid JSON" in str(e.value)
    os.remove("not_valid_json_test.json")


def test_algo_write():
    sample_algo = [
        {
            "funcs": {
                "first_name": matchers.feature_match_fuzzy_string,
                "last_name": matchers.feature_match_exact,
            },
            "blocks": ["MRN4", "ADDRESS4"],
            "matching_rule": matchers.eval_perfect_match,
        },
        {
            "funcs": {
                "last_name": matchers.feature_match_four_char,
                "sex": matchers.feature_match_log_odds_exact,
                "address": matchers.feature_match_log_odds_fuzzy_compare,
            },
            "blocks": ["ZIP", "BIRTH_YEAR"],
            "matching_rule": matchers.eval_log_odds_cutoff,
            "cluster_ratio": 0.9,
            "kwargs": {"similarity_measure": "Levenshtein", "threshold": 0.85},
        },
    ]
    test_file_path = "algo_test_write.json"
    if os.path.isfile("./" + test_file_path):  # pragma: no cover
        os.remove("./" + test_file_path)
    write_linkage_config(sample_algo, test_file_path)

    loaded_algo = read_linkage_config(test_file_path)
    assert loaded_algo == [
        {
            "funcs": {
                "first_name": "func:recordlinker.linkage.matchers.feature_match_fuzzy_string",
                "last_name": "func:recordlinker.linkage.matchers.feature_match_exact",
            },
            "blocks": ["MRN4", "ADDRESS4"],
            "matching_rule": "func:recordlinker.linkage.matchers.eval_perfect_match",
        },
        {
            "funcs": {
                "last_name": "func:recordlinker.linkage.matchers.feature_match_four_char",
                "sex": "func:recordlinker.linkage.matchers.feature_match_log_odds_exact",
                "address": "func:recordlinker.linkage.matchers.feature_match_log_odds_fuzzy_compare",
            },
            "blocks": ["ZIP", "BIRTH_YEAR"],
            "matching_rule": "func:recordlinker.linkage.matchers.eval_log_odds_cutoff",
            "cluster_ratio": 0.9,
            "kwargs": {"similarity_measure": "Levenshtein", "threshold": 0.85},
        },
    ]
    os.remove("./" + test_file_path)


def test_link_record_against_mpi_none_record():
    algorithm = DIBBS_BASIC
    MPI = _init_db()

    patients = json.load(
        open(
            pathlib.Path(__file__).parent.parent.parent
            / "assets"
            / "linkage"
            / "patient_bundle_to_link_with_mpi.json"
        )
    )

    patients = patients["entry"]
    patients = [
        p.get("resource")
        for p in patients
        if p.get("resource", {}).get("resourceType", "") == "Patient"
    ][:2]

    # Test various null data values in incoming record
    patients[1]["gender"] = None
    patients[1]["zip"] = None
    matches = []
    mapped_patients = {}
    for patient in patients:
        matched, pid = link_record_against_mpi(
            patient,
            algorithm,
        )
        matches.append(matched)
        if str(pid) not in mapped_patients:
            mapped_patients[str(pid)] = 0
        mapped_patients[str(pid)] += 1

    # First patient inserted into empty MPI, no match
    # Second patient blocks with first patient in first pass, then fuzzy matches name
    assert matches == [False, True]
    assert sorted(list(mapped_patients.values())) == [2]

    _clean_up(MPI.dal)


# TODO: Move this to an integration test suite
def test_link_record_against_mpi():
    algorithm = DIBBS_BASIC
    MPI = _init_db()
    patients = json.load(
        open(
            pathlib.Path(__file__).parent.parent.parent
            / "assets"
            / "linkage"
            / "patient_bundle_to_link_with_mpi.json"
        )
    )
    patients = patients["entry"]
    patients = [
        p
        for p in patients
        if p.get("resource", {}).get("resourceType", "") == "Patient"
    ]

    matches = []
    mapped_patients = {}
    for patient in patients:
        matched, pid = link_record_against_mpi(
            patient["resource"],
            algorithm,
        )
        matches.append(matched)
        if str(pid) not in mapped_patients:
            mapped_patients[str(pid)] = 0
        mapped_patients[str(pid)] += 1

    # First patient inserted into empty MPI, no match
    # Second patient blocks with first patient in first pass, then fuzzy matches name
    # Third patient is entirely new individual, no match
    # Fourth patient fails blocking with first pass then fails on second
    # Fifth patient: in first pass MRN blocks with one cluster but fails name,
    # in second pass name blocks with different cluster but fails address, no match
    # Sixth patient: in first pass, MRN blocks with one cluster and name matches in it,
    # in second pass name blocks on different cluster and address matches it,
    # finds greatest strength match and correctly assigns to larger cluster
    assert matches == [False, True, False, False, False, False]
    assert sorted(list(mapped_patients.values())) == [1, 1, 1, 1, 2]

    # Re-open connection to check for all insertions
    patient_records = MPI.dal.select_results(select(MPI.dal.PATIENT_TABLE))
    patient_id_count = {}
    person_id_count = {}
    for patient in patient_records[1:]:
        if str(patient[0]) not in patient_id_count:
            patient_id_count[str(patient[0])] = 1
        else:
            patient_id_count[str(patient[0])] = patient_id_count[str(patient[0])] + 1
        if str(patient[1]) not in person_id_count:
            person_id_count[str(patient[1])] = 1
        else:
            person_id_count[str(patient[1])] = person_id_count[str(patient[1])] + 1

    assert len(patient_records[1:]) == len(patients)
    for person_id in person_id_count:
        assert person_id_count[person_id] == mapped_patients[person_id]

    # name and given_name
    given_name_count = 0
    name_count = 0
    for patient in patients:
        for name in patient["resource"]["name"]:
            name_count += 1
            for given_name in name["given"]:
                given_name_count += 1
    given_name_records = MPI.dal.select_results(select(MPI.dal.GIVEN_NAME_TABLE))
    assert len(given_name_records[1:]) == given_name_count
    name_records = MPI.dal.select_results(select(MPI.dal.NAME_TABLE))
    assert len(name_records[1:]) == name_count

    # address
    address_records = MPI.dal.select_results(select(MPI.dal.ADDRESS_TABLE))
    address_count = 0
    for patient in patients:
        for address in patient["resource"]["address"]:
            address_count += 1
    assert len(address_records[1:]) == address_count

    _clean_up(MPI.dal)


def test_link_record_against_mpi_enhanced_algo():
    algorithm = DIBBS_ENHANCED
    MPI = _init_db()
    patients = json.load(
        open(
            pathlib.Path(__file__).parent.parent.parent
            / "assets"
            / "linkage"
            / "patient_bundle_to_link_with_mpi.json"
        )
    )
    patients = patients["entry"]
    patients = [
        p
        for p in patients
        if p.get("resource", {}).get("resourceType", "") == "Patient"
    ]
    # add an additional patient that will fuzzy match to patient 0
    patient0_copy = copy.deepcopy(patients[0])
    patient0_copy["resource"]["id"] = str(uuid.uuid4())
    patient0_copy["resource"]["name"][0]["given"][0] = "Jhon"
    patients.append(patient0_copy)
    matches = []
    mapped_patients = {}
    for patient in patients:
        matched, pid = link_record_against_mpi(
            patient["resource"],
            algorithm,
        )
        matches.append(matched)
        if str(pid) not in mapped_patients:
            mapped_patients[str(pid)] = 0
        mapped_patients[str(pid)] += 1

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

    # Re-open connection to check for all insertions
    patient_records = MPI.dal.select_results(select(MPI.dal.PATIENT_TABLE))
    patient_id_count = {}
    person_id_count = {}
    for patient in patient_records[1:]:
        if str(patient[0]) not in patient_id_count:
            patient_id_count[str(patient[0])] = 1
        else:
            patient_id_count[str(patient[0])] = patient_id_count[str(patient[0])] + 1
        if str(patient[1]) not in person_id_count:
            person_id_count[str(patient[1])] = 1
        else:
            person_id_count[str(patient[1])] = person_id_count[str(patient[1])] + 1

    assert len(patient_records[1:]) == len(patients)
    for person_id in person_id_count:
        assert person_id_count[person_id] == mapped_patients[person_id]

    # name and given_name
    given_name_count = 0
    name_count = 0
    for patient in patients:
        for name in patient["resource"]["name"]:
            name_count += 1
            for given_name in name["given"]:
                given_name_count += 1
    given_name_records = MPI.dal.select_results(select(MPI.dal.GIVEN_NAME_TABLE))
    assert len(given_name_records[1:]) == given_name_count
    name_records = MPI.dal.select_results(select(MPI.dal.NAME_TABLE))
    assert len(name_records[1:]) == name_count

    # address
    address_records = MPI.dal.select_results(select(MPI.dal.ADDRESS_TABLE))
    address_count = 0
    for patient in patients:
        for address in patient["resource"]["address"]:
            address_count += 1
    assert len(address_records[1:]) == address_count

    _clean_up(MPI.dal)


def test_add_person_resource():
    bundle = json.load(
        open(
            pathlib.Path(__file__).parent.parent.parent
            / "assets"
            / "general"
            / "patient_bundle.json"
        )
    )
    raw_bundle = copy.deepcopy(bundle)
    patient_id = "TEST_PATIENT_ID"
    person_id = "TEST_PERSON_ID"

    returned_bundle = add_person_resource(
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


def test_compare_address_elements():
    feature_funcs = {
        "address": matchers.feature_match_four_char,
    }
    col_to_idx = {"address": 2}
    record = [
        "123",
        "1",
        ["John", "Paul", "George"],
        "1980-01-01",
        ["123 Main St"],
    ]
    record2 = [
        "123",
        "1",
        ["John", "Paul", "George"],
        "1980-01-01",
        ["123 Main St", "9 North Ave"],
    ]
    mpi_patient1 = [
        "456",
        "2",
        "John",
        "1980-01-01",
        "123 Main St",
    ]
    mpi_patient2 = [
        "789",
        "3",
        "Pierre",
        "1980-01-01",
        "6 South St",
    ]

    same_address = _compare_address_elements(
        record, mpi_patient1, feature_funcs, "address", col_to_idx
    )
    assert same_address is True

    same_address = _compare_address_elements(
        record2, mpi_patient1, feature_funcs, "address", col_to_idx
    )
    assert same_address is True

    different_address = _compare_address_elements(
        record, mpi_patient2, feature_funcs, "address", col_to_idx
    )
    assert different_address is False


def test_compare_name_elements():
    feature_funcs = {"first": matchers.feature_match_fuzzy_string}
    col_to_idx = {"first": 0}
    record = [
        "123",
        "1",
        ["John", "Paul", "George"],
        "1980-01-01",
        ["123 Main St"],
    ]
    record3 = [
        "123",
        "1",
        ["Jean", "Pierre"],
        "1980-01-01",
        ["123 Main St", "9 North Ave"],
    ]
    mpi_patient1 = [
        "456",
        "2",
        "John",
        "1980-01-01",
        "756 South St",
    ]
    mpi_patient2 = [
        "789",
        "3",
        "Jean",
        "1980-01-01",
        "6 South St",
    ]

    same_name = _compare_name_elements(
        record[2:], mpi_patient1[2:], feature_funcs, "first", col_to_idx
    )
    assert same_name is True

    # Assert same first name with new middle name in record == true fuzzy match
    add_middle_name = _compare_name_elements(
        record3[2:], mpi_patient2[2:], feature_funcs, "first", col_to_idx
    )
    assert add_middle_name is True

    add_middle_name = _compare_name_elements(
        record[2:], mpi_patient1[2:], feature_funcs, "first", col_to_idx
    )
    assert add_middle_name is True

    # Assert no match with different names
    different_names = _compare_name_elements(
        record3[2:], mpi_patient1[2:], feature_funcs, "first", col_to_idx
    )
    assert different_names is False


def test_condense_extracted_address():
    patients = json.load(
        open(
            pathlib.Path(__file__).parent.parent.parent
            / "assets"
            / "linkage"
            / "patient_bundle_to_link_with_mpi.json"
        )
    )
    patients = patients["entry"]
    patients = [
        p.get("resource", {})
        for p in patients
        if p.get("resource", {}).get("resourceType", "") == "Patient"
    ]
    patient = patients[2]
    assert _condense_extract_address_from_resource(patient, "address") == [
        "PO Box 1 First Rock",
        "Bay 16 Ward Sector 24",
    ]


def test_flatten_patient():
    patients = json.load(
        open(
            pathlib.Path(__file__).parent.parent.parent
            / "assets"
            / "linkage"
            / "patient_bundle_to_link_with_mpi.json"
        )
    )

    patients = patients["entry"]
    patients = [
        p.get("resource", {})
        for p in patients
        if p.get("resource", {}).get("resourceType", "") == "Patient"
    ]

    col_to_idx = {
        "address": 0,
        "birthdate": 1,
        "city": 2,
        "first_name": 3,
        "last_name": 4,
        "mrn": 4,
        "sex": 5,
        "state": 6,
        "zip": 7,
    }

    # Use patient with multiple identifiers to also test MRN-specific filter
    assert _flatten_patient_resource(patients[2], col_to_idx) == [
        "2c6d5fd1-4a70-11eb-99fd-ad786a821574",
        None,
        ["PO Box 1 First Rock", "Bay 16 Ward Sector 24"],
        "2060-05-14",
        ["Bozeman", "Brooklyn"],
        ["Tali", "Zora", "Tali", "Zora", "Tali", "Zora"],
        "Vas Normandy",
        "7894561235",
        "female",
        ["Montana", "New York"],
        ["11111", "11111"],
    ]


def test_multi_element_blocking():
    MPI = _init_db()
    patients = json.load(
        open(
            pathlib.Path(__file__).parent.parent.parent
            / "assets"
            / "linkage"
            / "patient_bundle_to_link_with_mpi.json"
        )
    )
    patients = patients["entry"]
    patients = [
        p.get("resource", {})
        for p in patients
        if p.get("resource", {}).get("resourceType", "") == "Patient"
    ]

    # Insert multi-entry patient into DB
    patient = patients[2]
    algorithm = DIBBS_BASIC
    link_record_against_mpi(patient, algorithm)

    # Now check that we can block on either name & return same results
    # First row of returned results is headers
    vm_found_records = MPI.get_block_data({"last_name": {"value": "Vas Neema"}})
    nr_found_records = MPI.get_block_data({"last_name": {"value": "Nar Raya"}})
    assert vm_found_records == nr_found_records

    _clean_up(MPI.dal)


def test_convert_given_name_to_first_name():
    assert (
        _convert_given_name_to_first_name([]) == []
    ), "Empty data should return empty data"

    data = [["last_name"], ["LENNON"], ["MCCARTNEY"], ["HARRISON"], ["STARKLEY"]]
    assert (
        _convert_given_name_to_first_name(data) == data
    ), "Data without given names should return the same data"

    data = [
        [
            "mrn",
            "last_name",
            "given_name",
            "city",
        ],
        ["111111111", "LENNON", ["JOHN", "WINSTON", "ONO"], "Liverpool"],
        ["222222222", "MCCARTNEY", ["JAMES", "PAUL"], "Liverpool"],
        ["333333333", "HARRISON", ["GEORGE", "HAROLD"], "Liverpool"],
        ["444444444", "STARKLEY", ["RICHARD"], "Liverpool"],
    ]
    assert _convert_given_name_to_first_name(data) == [
        [
            "mrn",
            "last_name",
            "first_name",
            "city",
        ],
        ["111111111", "LENNON", "JOHN WINSTON ONO", "Liverpool"],
        ["222222222", "MCCARTNEY", "JAMES PAUL", "Liverpool"],
        ["333333333", "HARRISON", "GEORGE HAROLD", "Liverpool"],
        ["444444444", "STARKLEY", "RICHARD", "Liverpool"],
    ], "Given names should be concatenated into a single string"
