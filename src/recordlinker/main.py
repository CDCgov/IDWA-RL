import copy
from pathlib import Path
from typing import Annotated
from typing import Optional

from fastapi import Body
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import Response
from fastapi import status
from pydantic import BaseModel
from pydantic import Field
from sqlalchemy import orm
from sqlalchemy.sql import expression

from recordlinker import utils
from recordlinker.base_service import BaseService
from recordlinker.database import get_session
from recordlinker.linking import algorithm_service
from recordlinker.linking import link

# Instantiate FastAPI via DIBBs' BaseService class
app = BaseService(
    service_name="DIBBs Record Linkage Service",
    service_path="/record-linkage",
    description_path=Path(__file__).parent.parent.parent / "README.md",
    include_health_check_endpoint=False,
    # openapi_url="/record-linkage/openapi.json",
).start()


# Request and response models
class LinkRecordInput(BaseModel):
    """
    Schema for requests to the /link-record endpoint.
    """

    bundle: dict = Field(
        description="A FHIR bundle containing a patient resource to be checked "
        "for links to existing patient records"
    )
    algorithm: Optional[str] = Field(
        description="Optionally, a string that maps to an algorithm label stored in "
        "algorithm table",
        default=None,
    )
    external_person_id: Optional[str] = Field(
        description="The External Identifier, provided by the client,"
        " for a unique patient/person that is linked to patient(s)",
        default=None,
    )


class LinkRecordResponse(BaseModel):
    """
    The schema for responses from the /link-record endpoint.
    """

    found_match: bool = Field(
        description="A true value indicates that one or more existing records "
        "matched with the provided record, and these results have been linked."
    )
    updated_bundle: dict = Field(
        description="If link_found is true, returns the FHIR bundle with updated"
        " references to existing Personresource. If link_found is false, "
        "returns the FHIR bundle with a reference to a newly created "
        "Person resource."
    )
    message: Optional[str] = Field(
        description="An optional message in the case that the linkage endpoint did "
        "not run successfully containing a description of the error that happened.",
        default="",
    )


class HealthCheckResponse(BaseModel):
    """
    The schema for response from the record linkage health check endpoint.
    """

    status: str = Field(description="Returns status of this service")


class GetAlgorithmsResponse(BaseModel):
    """
    The schema for response from he record linkage get algorithms endpoint
    """

    algorithms: list[str] = Field(
        description="Returns a list of algorithms available from the database"
    )


@app.get("/")
async def health_check(db_session: orm.Session = Depends(get_session)) -> HealthCheckResponse:
    """
    Check the status of this service and its connection to Master Patient Index(MPI). If
    an HTTP 200 status code is returned along with '{"status": "OK"}' then the record
    linkage service is available and running properly. The mpi_connection_status field
    contains a description of the connection health to the MPI database.
    """
    try:
        db_session.execute(expression.text("SELECT 1")).all()
        return {"status": "OK"}
    except Exception:
        raise HTTPException(status_code=503, detail={"status": "Service Unavailable"})


# Sample requests and responses for docs
sample_link_record_requests = utils.read_json_from_assets("sample_link_record_requests.json")
sample_link_record_responses = utils.read_json_from_assets("sample_link_record_responses.json")


@app.post("/link-record", status_code=200, responses={200: sample_link_record_responses})
async def link_record(
    request: Request,
    input: Annotated[LinkRecordInput, Body(examples=sample_link_record_requests)],
    response: Response,
    db_session: orm.Session = Depends(get_session),
) -> LinkRecordResponse:
    """
    Compare a FHIR bundle with records in the Master Patient Index (MPI) to
    check for matches with existing patient records If matches are found,
    returns the bundle with updated references to existing patients.
    """

    input = dict(input)
    input_bundle = input.get("bundle", {})
    external_id = input.get("external_person_id", None)

    # get label from params
    algorithm_label = input.get("algorithm")

    #get algorithm from DB
    algorithm = algorithm_service.get_algorithm_by_label(db_session, algorithm_label)

    if not algorithm:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        return {
            "found_match": False,
            "updated_bundle": input_bundle,
            "message": "Error: Invalid algorithm specified",
        }

    # Now extract the patient record we want to link
    try:
        record_to_link = [
            entry.get("resource")
            for entry in input_bundle.get("entry", [])
            if entry.get("resource", {}).get("resourceType", "") == "Patient"
        ][0]
    except IndexError:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {
            "found_match": False,
            "updated_bundle": input_bundle,
            "message": "Supplied bundle contains no Patient resource to link on.",
        }


    # Now link the record
    try:
        # Make a copy of record_to_link so we don't modify the original
        record = copy.deepcopy(record_to_link)
        (found_match, new_person_id) = link.link_record_against_mpi(
            record=record,
            session=db_session,
            algorithm=algorithm,
            external_person_id=external_id,
        )
        updated_bundle = link.add_person_resource(
            new_person_id, record_to_link.get("id", ""), input_bundle
        )
        return {"found_match": found_match, "updated_bundle": updated_bundle}

    except ValueError as err:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return {
            "found_match": False,
            "updated_bundle": input_bundle,
            "message": f"Could not connect to database: {err}",
        }


@app.get("/algorithms")
async def get_algorithm_labels(
    db_session: orm.Session = Depends(get_session),
) -> GetAlgorithmsResponse:
    """
    Get a list of all available algorithms from the database
    """
    algorithms_list = algorithm_service.get_all_algorithm_labels(db_session)

    return {"algorithms": algorithms_list}
