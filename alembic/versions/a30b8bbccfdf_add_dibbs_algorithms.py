"""add dibbs algorithms

Revision ID: a30b8bbccfdf
Revises: d9eba1bdbad1
Create Date: 2024-09-26 15:10:15.179656

"""

from typing import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op
from recordlinker.models import Algorithm
from recordlinker.models import AlgorithmPass
from recordlinker.models import BlockingKey

# revision identifiers, used by Alembic.
revision: str = 'a30b8bbccfdf'
down_revision: Union[str, None] = 'd9eba1bdbad1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FUZZY_THRESHOLDS = {
    "first_name": 0.9,
    "last_name": 0.9,
    "birthdate": 0.95,
    "address": 0.9,
    "city": 0.92,
    "zip": 0.95,
}

LOG_ODDS_SCORES = {
    "address": 8.438284928858774,
    "birthdate": 10.126641103800338,
    "city": 2.438553006137189,
    "first_name": 6.849475906891162,
    "last_name": 6.350720397426025,
    "mrn": 0.3051262572525359,
    "sex": 0.7510419059643679,
    "state": 0.022376768992488694,
    "zip": 4.975031471124867,
}

DIBBS_BASIC = {
    "id": 1,
    "is_default": True,
    "label": "DIBBS_BASIC",
    "description": "Compares the fields of two records using string similarity scoring. If similarity score is above fuzzy threshold then the fields agree. If all fields being considered agree, then the records are a match."
}

DIBBS_ENHANCED = {
    "id": 2, 
    "is_default": False,
    "label": "DIBBS_ENHANCED",
    "description": "Similair to the basic algorithm with the addition of log odds scoring. String comparison scores are multiplied by unique scoring weights for each field. If the sum of all considered weights is greater than a threshold then the records are a match."
}

DIBBS_BASIC_PASS_ONE = {
    "id": 1,
    "algorithm_id": 1,
    "blocking_keys": [BlockingKey.BIRTHDATE.name, BlockingKey.MRN.name, BlockingKey.SEX.name],
    "evaluators": {"first_name": "func:recordlinker.linking.matchers.feature_match_fuzzy_string", "last_name": "func:recordlinker.linking.matchers.feature_match_exact"},
    "rule": "func:recordlinker.linking.matchers.eval_perfect_match",
    "cluster_ratio": 0.9,
    "kwargs": {"thresholds": FUZZY_THRESHOLDS}
}

DIBBS_BASIC_PASS_TWO = {
    "id": 2,
    "algorithm_id": 1,
    "blocking_keys": [BlockingKey.ZIP.name, BlockingKey.FIRST_NAME.name, BlockingKey.LAST_NAME.name, BlockingKey.SEX.name],
    "evaluators": {"address": "func:recordlinker.linking.matchers.feature_match_fuzzy_string", "birthdate": "func:recordlinker.linking.matchers.feature_match_exact"},
    "rule": "func:recordlinker.linking.matchers.eval_perfect_match",
    "cluster_ratio": 0.9,
    "kwargs": {"thresholds": FUZZY_THRESHOLDS}
}

DIBBS_ENHANCED_PASS_ONE = {
    "id": 3,
    "algorithm_id": 2,
    "blocking_keys": [BlockingKey.BIRTHDATE.name, BlockingKey.MRN.name, BlockingKey.SEX.name],
    "evaluators": {"first_name": "func:recordlinker.linking.matchers.feature_match_log_odds_fuzzy_compare", "last_name": "func:recordlinker.linking.matchers.feature_match_log_odds_fuzzy_compare"},
    "rule": "func:recordlinker.linking.matchers.eval_log_odds_cutoff",
    "cluster_ratio": 0.9,
    "kwargs": {
            "similarity_measure": "JaroWinkler",
            "thresholds": FUZZY_THRESHOLDS,
            "true_match_threshold": 12.2,
            "log_odds": LOG_ODDS_SCORES,
        }
}

DIBBS_ENHANCED_PASS_TWO = {
    "id": 4,
    "algorithm_id": 2,
    "blocking_keys": [BlockingKey.ZIP.name, BlockingKey.FIRST_NAME.name, BlockingKey.LAST_NAME.name, BlockingKey.SEX.name],
    "evaluators": {"address": "func:recordlinker.linking.matchers.feature_match_log_odds_fuzzy_compare", "birthdate": "func:recordlinker.linking.matchers.feature_match_log_odds_fuzzy_compare"},
    "rule": "func:recordlinker.linking.matchers.eval_log_odds_cutoff",
    "cluster_ratio": 0.9,
    "kwargs": {
            "similarity_measure": "JaroWinkler",
            "thresholds": FUZZY_THRESHOLDS,
            "true_match_threshold": 17.0,
            "log_odds": LOG_ODDS_SCORES,
        }
}

def upgrade() -> None:
    #insert alogithms
    op.execute(sa.insert(Algorithm).values(DIBBS_BASIC))
    op.execute(sa.insert(Algorithm).values(DIBBS_ENHANCED))
    
    # #insert algorithm passes
    op.execute(sa.insert(AlgorithmPass).values(DIBBS_BASIC_PASS_ONE))
    op.execute(sa.insert(AlgorithmPass).values(DIBBS_BASIC_PASS_TWO))
    op.execute(sa.insert(AlgorithmPass).values(DIBBS_ENHANCED_PASS_ONE))
    op.execute(sa.insert(AlgorithmPass).values(DIBBS_ENHANCED_PASS_TWO))

def downgrade() -> None:
    # #delete algorithm pass rows
    op.execute(sa.delete(AlgorithmPass).where(AlgorithmPass.id == 1))
    op.execute(sa.delete(AlgorithmPass).where(AlgorithmPass.id == 2))
    op.execute(sa.delete(AlgorithmPass).where(AlgorithmPass.id == 3))
    op.execute(sa.delete(AlgorithmPass).where(AlgorithmPass.id == 4))

    #delete algorithm rows
    op.execute(sa.delete(Algorithm).where(Algorithm.id == 1))
    op.execute(sa.delete(Algorithm).where(Algorithm.id == 2))
