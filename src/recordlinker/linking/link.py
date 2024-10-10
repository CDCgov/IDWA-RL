"""
recordlinker.linking.link
~~~~~~~~~~~~~~~~~~~~~~~~~

This module is used to run the linkage algorithm using the MPI service
"""

import collections
import typing

import pydantic
from opentelemetry import trace
from sqlalchemy import orm

from recordlinker import models
from recordlinker import utils
from recordlinker.linking import matchers

from . import mpi_service

TRACER = trace.get_tracer(__name__)


# TODO: This is a FHIR specific function, should be moved to a FHIR module
def fhir_record_to_pii_record(fhir_record: dict) -> models.PIIRecord:
    """
    Parse the FHIR record into a PIIRecord object
    """
    val = {
        "external_id": fhir_record.get("id"),
        "name": fhir_record.get("name", []),
        "birthDate": fhir_record.get("birthDate"),
        "sex": fhir_record.get("gender"),
        "address": fhir_record.get("address", []),
        "phone": fhir_record.get("telecom", []),
        "mrn": None,
    }
    for identifier in fhir_record.get("identifier", []):
        for coding in identifier.get("type", {}).get("coding", []):
            if coding.get("code") == "MR":
                val["mrn"] = identifier.get("value")
    for address in val["address"]:
        for extension in address.get("extension", []):
            if extension.get("url") == "http://hl7.org/fhir/StructureDefinition/geolocation":
                for coord in extension.get("extension", []):
                    if coord.get("url") == "latitude":
                        address["latitude"] = coord.get("valueDecimal")
                    elif coord.get("url") == "longitude":
                        address["longitude"] = coord.get("valueDecimal")
    return models.PIIRecord(**val)


# TODO: This is a FHIR specific function, should be moved to a FHIR module
def add_person_resource(
    person_id: str,
    patient_id: str,
    bundle: dict = pydantic.Field(description="A FHIR bundle"),
) -> dict:
    """
    Adds a simplified person resource to a bundle if the patient resource in the bundle
    matches an existing record in the Master Patient Index. Returns the bundle with
    the newly added person resource.

    :param person_id: _description_
    :param patient_id: _description_
    :param bundle: _description_, defaults to Field(description="A FHIR bundle")
    :return: _description_
    """
    person_resource = {
        "fullUrl": f"urn:uuid:{person_id}",
        "resource": {
            "resourceType": "Person",
            "id": f"{person_id}",
            "link": [{"target": {"reference": f"Patient/{patient_id}"}}],
        },
        "request": {
            "method": "PUT",
            "url": f"Person/{person_id}",
        },
    }
    bundle.get("entry", []).append(person_resource)
    return bundle


def compare(record: models.PIIRecord, patient: models.Patient, algorithm_pass: models.AlgorithmPass) -> bool:
    """
    Compare the incoming record to the linked patient
    """
    # all the functions used for comparison
    funcs: dict[models.Feature, matchers.FEATURE_COMPARE_FUNC] = utils.bind_functions(algorithm_pass.evaluators)
    # a function to determine a match based on the comparison results
    matching_rule: matchers.MATCH_RULE_FUNC = utils.str_to_callable(algorithm_pass.rule)
    # # keyword arguments to pass to comparison functions and matching rule
    kwargs: dict[typing.Any, typing.Any] = algorithm_pass.kwargs

    results: list[float] = []
    for field, func in funcs.items():
        if field not in {i.value for i in models.Feature}:
            raise ValueError(f"Invalid comparison field: {field}")
        # Evaluate the comparison function and append the result to the list
        result: float = func(record, patient, models.Feature(field), **kwargs)
        results.append(result)
    return matching_rule(results, **kwargs)


def link_record_against_mpi(
    record: dict,
    session: orm.Session,
    algorithm: models.Algorithm,
    external_person_id: typing.Optional[str] = None,
) -> tuple[bool, str]:
    """
    Runs record linkage on a single incoming record (extracted from a FHIR
    bundle) using an existing database as an MPI. Uses a flexible algorithm
    configuration to allow customization of the exact kind of linkage to
    run. Linkage is assumed to run using cluster membership (i.e. the new
    record must match a certain proportion of existing records all assigned
    to a person in order to match), and if multiple persons are matched,
    the new record is linked to the person with the strongest membership
    percentage.

    :param record: The FHIR-formatted patient resource to try to match to
      other records in the MPI.
    :param session: The SQLAlchemy session to use for database operations.
    :param algorithm: An algorithm configuration object
    :returns: A tuple consisting of a boolean indicating whether a match
      was found for the new record in the MPI, followed by the ID of the
      Person entity now associated with the incoming patient (either a
      new Person ID or the ID of an existing matched Person).
    """
    # Extract the PII values from the incoming record
    pii_record: models.PIIRecord = fhir_record_to_pii_record(record)

    # Membership scores need to persist across linkage passes so that we can
    # find the highest scoring match across all passes
    scores: dict[models.Person, float] = collections.defaultdict(float)
    for algorithm_pass in algorithm.passes:
        with TRACER.start_as_current_span("link.pass"):
            # the minimum ratio of matches needed to be considered a cluster member
            cluster_ratio = algorithm_pass.cluster_ratio
            # initialize a dictionary to hold the clusters of patients for each person
            clusters: dict[models.Person, list[models.Patient]] = collections.defaultdict(list)
            # block on the pii_record and the algorithm's blocking criteria, then
            # iterate over the patients, grouping them by person
            with TRACER.start_as_current_span("link.block"):
                patients = mpi_service.get_block_data(session, pii_record, algorithm_pass)
                for patient in patients:
                    clusters[patient.person].append(patient)

            # evaluate each Person cluster to see if the incoming record is a match
            with TRACER.start_as_current_span("link.evaluate"):
                for person, patients in clusters.items():
                    assert patients, "Patient cluster should not be empty"
                    matched_count = 0
                    for patient in patients:
                        # increment our match count if the pii_record matches the patient
                        with TRACER.start_as_current_span("link.compare"):
                            if compare(pii_record, patient, algorithm_pass):
                                matched_count += 1
                    # calculate the match ratio for this person cluster
                    match_ratio = matched_count / len(patients)
                    if match_ratio >= cluster_ratio:
                        # The match ratio is larger than the minimum cluster threshold,
                        # optionally update the max score for this person
                        scores[person] = max(scores[person], match_ratio)

    matched_person: typing.Optional[models.Person] = None
    if scores:
        # Find the person with the highest matching score
        matched_person, _ = max(scores.items(), key=lambda i: i[1])

    with TRACER.start_as_current_span("insert"):
        patient = mpi_service.insert_patient(
            session,
            pii_record,
            matched_person,
            pii_record.external_id,
            external_person_id,
        )
    # return a tuple indicating whether a match was found and the person ID
    return (bool(matched_person), str(patient.person.internal_id))
