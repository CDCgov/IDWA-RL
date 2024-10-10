import pytest
from fastapi.testclient import TestClient

from recordlinker import database
from recordlinker import main
from recordlinker import utils
from recordlinker import models


@pytest.fixture(scope="function")
def session():
    with database.get_test_session() as session:
        yield session


@pytest.fixture(scope="function")
def client():
    # Create a new testing session, its important just to call the
    # get_test_session() function once per test, as it resets the database
    # tables everytime its called
    with database.get_test_session() as session:
        # Override the get_session dependency in the FastAPI app to use
        # a simple function that returns the testing session, this will
        # make the session persist for each call to the client within the
        # scope of the test
        main.app.dependency_overrides[database.get_session] = lambda: session
        with TestClient(main.app) as c:
            yield c

@pytest.fixture
def basic_algorithm():
    basic_algo_pass1 = models.AlgorithmPass(
        id=1, 
        algorithm_id=1, 
        blocking_keys=[1,2,3], 
        evaluators={
            "first_name": "func:recordlinker.linking.matchers.feature_match_fuzzy_string", 
            "last_name": "func:recordlinker.linking.matchers.feature_match_exact"
        }, 
        rule="func:recordlinker.linking.matchers.eval_perfect_match", 
        cluster_ratio=0.9, 
        kwargs={
            "thresholds": {
                    "first_name": 0.9,
                    "last_name": 0.9,
                    "birthdate": 0.95,
                    "address": 0.9,
                    "city": 0.92,
                    "zip": 0.95,
                }
        }
    )
    basic_algo_pass2 = models.AlgorithmPass(
        id=2, 
        algorithm_id=1, 
        blocking_keys=[4,5,6,3], 
        evaluators={
            "address": "func:recordlinker.linking.matchers.feature_match_fuzzy_string", 
            "birthdate": "func:recordlinker.linking.matchers.feature_match_exact"
        }, 
        rule="func:recordlinker.linking.matchers.eval_perfect_match", 
        cluster_ratio=0.9, 
        kwargs={
            "thresholds": {
                    "first_name": 0.9,
                    "last_name": 0.9,
                    "birthdate": 0.95,
                    "address": 0.9,
                    "city": 0.92,
                    "zip": 0.95,
                }
        }
    )
    return models.Algorithm(id=1, label="DIBBS_BASIC", is_default=True, description="First algorithm", passes=[basic_algo_pass1, basic_algo_pass2])

@pytest.fixture
def enhanced_algorithm():
    enhanced_algo_pass1 = models.AlgorithmPass(
        id=1, 
        algorithm_id=1, 
        blocking_keys=[1,2,3], 
        evaluators={
            "first_name": "func:recordlinker.linking.matchers.feature_match_log_odds_fuzzy_compare", 
            "last_name": "func:recordlinker.linking.matchers.feature_match_log_odds_fuzzy_compare"
        }, 
        rule="func:recordlinker.linking.matchers.eval_log_odds_cutoff", 
        cluster_ratio=0.9, 
        kwargs={
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
    )
    enhanced_algo_pass2 = models.AlgorithmPass(
        id=2, 
        algorithm_id=1, 
        blocking_keys=[4,5,6,3], 
        evaluators={
            "address": "func:recordlinker.linking.matchers.feature_match_log_odds_fuzzy_compare", 
            "birthdate": "func:recordlinker.linking.matchers.feature_match_log_odds_fuzzy_compare"
        }, 
        rule="func:recordlinker.linking.matchers.eval_log_odds_cutoff", 
        cluster_ratio=0.9, 
        kwargs={
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
    )
    return models.Algorithm(id=1, label="DIBBS_ENHANCED", is_default=False, description="First algorithm", passes=[enhanced_algo_pass1, enhanced_algo_pass2])
