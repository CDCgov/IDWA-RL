"""
unit.linking.test_matchers
~~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains unit tests for the :mod:`~recordlinker.linking.matchers` module.
"""

import pytest

from recordlinker import models
from recordlinker import schemas
from recordlinker.linking import matchers


def test_get_fuzzy_params():
    assert matchers._get_fuzzy_params("last_name") == ("JaroWinkler", 0.7)

    kwargs = {
        "similarity_measure": "Levenshtein",
        "thresholds": {"city": 0.95, "address": 0.98},
    }
    assert matchers._get_fuzzy_params("city", **kwargs) == ("Levenshtein", 0.95)
    assert matchers._get_fuzzy_params("address", **kwargs) == ("Levenshtein", 0.98)
    assert matchers._get_fuzzy_params("first_name", **kwargs) == ("Levenshtein", 0.7)


def test_feature_match_any():
    record = schemas.PIIRecord(
        name=[{"given": ["John"], "family": "Smith"}, {"family": "Harrison"}],
        birthDate="Jan 1 1980",
    )
    pat1 = models.Patient(
        data={"name": [{"given": ["John", "Michael"], "family": "Doe"}], "birthDate": "1980-01-01"}
    )
    pat2 = models.Patient(data={"name": [{"given": ["Michael"], "family": "Smith"}], "sex": "male"})
    pat3 = models.Patient(data={"name": [{"family": "Smith"}, {"family": "Williams"}]})

    assert matchers.feature_match_any(record, pat1, schemas.Feature.FIRST_NAME)
    assert not matchers.feature_match_any(record, pat1, schemas.Feature.LAST_NAME)
    assert matchers.feature_match_any(record, pat1, schemas.Feature.BIRTHDATE)
    assert not matchers.feature_match_any(record, pat1, schemas.Feature.ZIPCODE)

    assert not matchers.feature_match_any(record, pat2, schemas.Feature.FIRST_NAME)
    assert matchers.feature_match_any(record, pat2, schemas.Feature.LAST_NAME)
    assert not matchers.feature_match_any(record, pat2, schemas.Feature.SEX)
    assert not matchers.feature_match_any(record, pat1, schemas.Feature.ZIPCODE)

    assert not matchers.feature_match_any(record, pat3, schemas.Feature.FIRST_NAME)
    assert matchers.feature_match_any(record, pat3, schemas.Feature.LAST_NAME)
    assert not matchers.feature_match_any(record, pat3, schemas.Feature.BIRTHDATE)

    with pytest.raises(ValueError):
        matchers.feature_match_any(record, pat1, "unknown")


def test_feature_match_exact():
    record = schemas.PIIRecord(
        name=[{"given": ["John"], "family": "Smith"}, {"family": "Harrison"}],
        birthDate="December 31, 1999",
    )
    pat1 = models.Patient(
        data={"name": [{"given": ["John", "Michael"], "family": "Doe"}], "birthDate": "1999-12-31"}
    )
    pat2 = models.Patient(
        data={
            "name": [{"given": ["John"], "family": "Smith"}],
            "sex": "male",
            "address": [{"zipcode": "12345"}],
        },
    )
    pat3 = models.Patient(data={"name": [{"family": "Smith"}, {"family": "Harrison"}]})

    assert not matchers.feature_match_exact(record, pat1, schemas.Feature.FIRST_NAME)
    assert not matchers.feature_match_exact(record, pat1, schemas.Feature.LAST_NAME)
    assert matchers.feature_match_exact(record, pat1, schemas.Feature.BIRTHDATE)
    assert not matchers.feature_match_exact(record, pat1, schemas.Feature.ZIPCODE)

    assert matchers.feature_match_exact(record, pat2, schemas.Feature.FIRST_NAME)
    assert not matchers.feature_match_exact(record, pat2, schemas.Feature.LAST_NAME)
    assert not matchers.feature_match_exact(record, pat2, schemas.Feature.SEX)
    assert not matchers.feature_match_exact(record, pat2, schemas.Feature.ZIPCODE)

    assert not matchers.feature_match_exact(record, pat3, schemas.Feature.FIRST_NAME)
    assert matchers.feature_match_exact(record, pat3, schemas.Feature.LAST_NAME)
    assert not matchers.feature_match_exact(record, pat3, schemas.Feature.BIRTHDATE)

    with pytest.raises(ValueError):
        matchers.feature_match_exact(record, pat1, "unknown")


def test_feature_match_fuzzy_string():
    record = schemas.PIIRecord(
        name=[{"given": ["John"], "family": "Smith"}, {"family": "Harrison"}],
        birthDate="1980-01-01",
    )
    pat1 = models.Patient(
        data={"name": [{"given": ["Jon", "Mike"], "family": "Doe"}], "birthDate": "Jan 1 1980"}
    )
    pat2 = models.Patient(data={"name": [{"given": ["Michael"], "family": "Smtih"}], "sex": "male"})
    pat3 = models.Patient(data={"name": [{"family": "Smyth"}, {"family": "Williams"}]})

    assert matchers.feature_match_fuzzy_string(record, pat1, schemas.Feature.FIRST_NAME)
    assert not matchers.feature_match_fuzzy_string(record, pat1, schemas.Feature.LAST_NAME)

    assert not matchers.feature_match_fuzzy_string(record, pat2, schemas.Feature.FIRST_NAME)
    assert matchers.feature_match_fuzzy_string(record, pat2, schemas.Feature.LAST_NAME)

    assert not matchers.feature_match_fuzzy_string(record, pat3, schemas.Feature.FIRST_NAME)
    assert matchers.feature_match_fuzzy_string(record, pat3, schemas.Feature.LAST_NAME)

    with pytest.raises(ValueError):
        matchers.feature_match_fuzzy_string(record, pat1, "first_name")


def test_feature_match_log_odds_fuzzy_compare():
    with pytest.raises(ValueError):
        matchers.feature_match_log_odds_fuzzy_compare(
            schemas.PIIRecord(),
            models.Patient(),
            schemas.Feature.MRN,
        )

    rec = schemas.PIIRecord(
        name=[{"given": ["John"], "family": "Shepard"}],
        birthDate="1980-11-7",
        address=[{"line": ["1234 Silversun Strip"]}],
    )
    pat = models.Patient(
        data={
            "name": [{"given": ["John"], "family": "Sheperd"}],
            "birthDate": "1970-06-07",
            "address": [{"line": ["asdfghjeki"]}],
        }
    )
    log_odds = {
        schemas.Feature.FIRST_NAME.value: 4.0,
        schemas.Feature.LAST_NAME.value: 6.5,
        schemas.Feature.BIRTHDATE.value: 9.8,
        schemas.Feature.ADDRESS.value: 3.7,
    }

    assert (
        matchers.feature_match_log_odds_fuzzy_compare(
            rec, pat, schemas.Feature.FIRST_NAME, log_odds=log_odds
        )
        == 4.0
    )

    assert (
        round(
            matchers.feature_match_log_odds_fuzzy_compare(
                rec, pat, schemas.Feature.LAST_NAME, log_odds=log_odds
            ),
            3,
        )
        == 6.129
    )

    assert (
        round(
            matchers.feature_match_log_odds_fuzzy_compare(
                rec, pat, schemas.Feature.BIRTHDATE, log_odds=log_odds
            ),
            3,
        )
        == 7.859
    )

    assert (
        round(
            matchers.feature_match_log_odds_fuzzy_compare(
                rec, pat, schemas.Feature.ADDRESS, log_odds=log_odds
            ),
            3,
        )
        == 0.0
    )
