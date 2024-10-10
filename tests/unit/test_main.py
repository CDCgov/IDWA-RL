import copy
from unittest import mock

from fastapi import status

from recordlinker import utils

def test_health_check(client):
    actual_response = client.get("/")
    assert actual_response.status_code == 200
    assert actual_response.json() == {"status": "OK"}

def test_openapi(client):
    actual_response = client.get("/openapi.json")
    assert actual_response.status_code == 200

@mock.patch("recordlinker.linking.algorithm_service.get_all_algorithm_labels")
def test_get_algorithms(patched_subprocess, client):
    patched_subprocess.return_value = ["DIBBS_BASIC"]
    actual_response = client.get("/algorithms")

    assert actual_response.json() == {"algorithms": ["DIBBS_BASIC"]}
    assert actual_response.status_code == status.HTTP_200_OK

@mock.patch("recordlinker.linking.algorithm_service.get_algorithm_by_label")
def test_linkage_bundle_with_no_patient(patched_subprocess, basic_algorithm, client):
    patched_subprocess.return_value = basic_algorithm
    bad_bundle = {"entry": []}
    expected_response = {
        "message": "Supplied bundle contains no Patient resource to link on.",
        "found_match": False,
        "updated_bundle": bad_bundle,
    }
    actual_response = client.post(
        "/link-record",
        json={"bundle": bad_bundle},
    )
    assert actual_response.json() == expected_response
    assert actual_response.status_code == status.HTTP_400_BAD_REQUEST

@mock.patch("recordlinker.linking.algorithm_service.get_algorithm_by_label")
def test_linkage_success(patched_subprocess, basic_algorithm, client):
    patched_subprocess.return_value = basic_algorithm
    test_bundle = utils.read_json_from_assets("patient_bundle_to_link_with_mpi.json")
    entry_list = copy.deepcopy(test_bundle["entry"])

    bundle_1 = test_bundle
    bundle_1["entry"] = [entry_list[0]]
    resp_1 = client.post("/link-record", json={"bundle": bundle_1})
    new_bundle = resp_1.json()["updated_bundle"]
    person_1 = [
        r.get("resource")
        for r in new_bundle["entry"]
        if r.get("resource").get("resourceType") == "Person"
    ][0]
    assert not resp_1.json()["found_match"]

    bundle_2 = test_bundle
    bundle_2["entry"] = [entry_list[1]]
    resp_2 = client.post("/link-record", json={"bundle": bundle_2})
    new_bundle = resp_2.json()["updated_bundle"]
    person_2 = [
        r.get("resource")
        for r in new_bundle["entry"]
        if r.get("resource").get("resourceType") == "Person"
    ][0]
    assert resp_2.json()["found_match"]
    assert person_2.get("id") == person_1.get("id")

    bundle_3 = test_bundle
    bundle_3["entry"] = [entry_list[2]]
    resp_3 = client.post("/link-record", json={"bundle": bundle_3})
    assert not resp_3.json()["found_match"]

    # Cluster membership success--justified match
    bundle_4 = test_bundle
    bundle_4["entry"] = [entry_list[3]]
    resp_4 = client.post("/link-record", json={"bundle": bundle_4})
    new_bundle = resp_4.json()["updated_bundle"]
    person_4 = [
        r.get("resource")
        for r in new_bundle["entry"]
        if r.get("resource").get("resourceType") == "Person"
    ][0]
    assert resp_4.json()["found_match"]
    assert person_4.get("id") == person_1.get("id")

    bundle_5 = test_bundle
    bundle_5["entry"] = [entry_list[4]]
    resp_5 = client.post("/link-record", json={"bundle": bundle_5})
    assert not resp_5.json()["found_match"]

    bundle_6 = test_bundle
    bundle_6["entry"] = [entry_list[5]]
    resp_6 = client.post("/link-record", json={"bundle": bundle_6})
    new_bundle = resp_6.json()["updated_bundle"]
    person_6 = [
        r.get("resource")
        for r in new_bundle["entry"]
        if r.get("resource").get("resourceType") == "Person"
    ][0]
    assert not resp_6.json()["found_match"]

@mock.patch("recordlinker.linking.algorithm_service.get_algorithm_by_label")
def test_use_enhanced_algo(patched_subprocess, enhanced_algorithm, client):
    patched_subprocess.return_value = enhanced_algorithm
    test_bundle = utils.read_json_from_assets("patient_bundle_to_link_with_mpi.json")
    entry_list = copy.deepcopy(test_bundle["entry"])

    bundle_1 = test_bundle
    bundle_1["entry"] = [entry_list[0]]
    resp_1 = client.post("/link-record", json={"bundle": bundle_1, "algorithm": "DIBBS_ENHANCED"})
    new_bundle = resp_1.json()["updated_bundle"]
    person_1 = [
        r.get("resource")
        for r in new_bundle["entry"]
        if r.get("resource").get("resourceType") == "Person"
    ][0]
    assert not resp_1.json()["found_match"]

    bundle_2 = test_bundle
    bundle_2["entry"] = [entry_list[1]]
    resp_2 = client.post("/link-record", json={"bundle": bundle_2, "algorithm": "DIBBS_ENHANCED"})
    new_bundle = resp_2.json()["updated_bundle"]
    person_2 = [
        r.get("resource")
        for r in new_bundle["entry"]
        if r.get("resource").get("resourceType") == "Person"
    ][0]
    assert resp_2.json()["found_match"]
    assert person_2.get("id") == person_1.get("id")

    bundle_3 = test_bundle
    bundle_3["entry"] = [entry_list[2]]
    resp_3 = client.post("/link-record", json={"bundle": bundle_3, "algorithm": "DIBBS_ENHANCED"})
    assert not resp_3.json()["found_match"]

    bundle_4 = test_bundle
    bundle_4["entry"] = [entry_list[3]]
    resp_4 = client.post("/link-record", json={"bundle": bundle_4, "algorithm": "DIBBS_ENHANCED"})
    new_bundle = resp_4.json()["updated_bundle"]
    person_4 = [
        r.get("resource")
        for r in new_bundle["entry"]
        if r.get("resource").get("resourceType") == "Person"
    ][0]
    assert resp_4.json()["found_match"]
    assert person_4.get("id") == person_1.get("id")

    bundle_5 = test_bundle
    bundle_5["entry"] = [entry_list[4]]
    resp_5 = client.post("/link-record", json={"bundle": bundle_5, "algorithm": "DIBBS_ENHANCED"})
    assert not resp_5.json()["found_match"]

    bundle_6 = test_bundle
    bundle_6["entry"] = [entry_list[5]]
    resp_6 = client.post("/link-record", json={"bundle": bundle_6, "algorithm": "DIBBS_ENHANCED"})
    new_bundle = resp_6.json()["updated_bundle"]
    person_6 = [
        r.get("resource")
        for r in new_bundle["entry"]
        if r.get("resource").get("resourceType") == "Person"
    ][0]
    assert not resp_6.json()["found_match"]


@mock.patch("recordlinker.linking.algorithm_service.get_algorithm_by_label")
def test_invalid_algorithm_param(patched_subprocess, client):
    patched_subprocess.return_value = None
    test_bundle = utils.read_json_from_assets("patient_bundle_to_link_with_mpi.json")
    expected_response = {
        "found_match": False,
        "updated_bundle": test_bundle,
        "message": "Error: Invalid algorithm specified",
    }

    actual_response = client.post(
        "/link-record", json={"bundle": test_bundle, "algorithm": "INVALID"}
    )

    assert actual_response.json() == expected_response
    assert actual_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY