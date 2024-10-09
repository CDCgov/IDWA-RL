"""
recordlinker.linking.matchers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains functions for evaluating whether two records are
a match based on the similarity of their features. These functions are
used by the record linkage algorithm to determine whether a candidate
pair of records should be considered a match or not.
"""

import typing

import rapidfuzz

from recordlinker.models.mpi import Patient
from recordlinker.schemas.pii import Feature
from recordlinker.schemas.pii import PIIRecord

SIMILARITY_MEASURES = typing.Literal["JaroWinkler", "Levenshtein", "DamerauLevenshtein"]

# A Callable type for comparing a feature on two records
FEATURE_COMPARE_FUNC = typing.Callable[[PIIRecord, Patient, Feature, dict[str, typing.Any]], float]
# A Callable type for evaluating whether a set of feature comparisons constitutes a match
MATCH_RULE_FUNC = typing.Callable[[list[float], dict[str, typing.Any]], bool]


def _get_fuzzy_params(col: str, **kwargs) -> tuple[SIMILARITY_MEASURES, float]:
    """
    Helper method to quickly determine the appropriate similarity measure
    and fuzzy matching threshold to use for fuzzy-comparing a particular
    field between two records.

    :param col: The string name of the column being used in a fuzzy
      comparison.
    :param kwargs: Optionally, a dictionary of keyword arguments containing
      values for a similarity metric and appropriate fuzzy thresholds.
    :return: A tuple containing the similarity metric to use and the
      fuzzy comparison threshold to measure against.
    """
    similarity_measure: SIMILARITY_MEASURES = "JaroWinkler"
    if "similarity_measure" in kwargs:
        similarity_measure = kwargs["similarity_measure"]
        # Ensure the similarity measure is valid
        if similarity_measure not in typing.get_args(SIMILARITY_MEASURES):
            raise ValueError(f"Invalid similarity measure: {similarity_measure}")

    threshold: float = 0.7
    if "thresholds" in kwargs:
        if col in kwargs["thresholds"]:
            threshold = kwargs["thresholds"][col]
    elif "threshold" in kwargs:
        threshold = kwargs["threshold"]

    return (similarity_measure, threshold)


def eval_perfect_match(feature_comparisons: list, **kwargs) -> bool:
    """
    Determines whether a given set of feature comparisons represent a
    'perfect' match (i.e. whether all features that were compared match
    in whatever criteria was specified for them).

    :param feature_comparisons: A list of 1s and 0s, one for each feature
      that was compared during the match algorithm.
    :return: The evaluation of whether the given features all match.
    """
    return sum(feature_comparisons) == len(feature_comparisons)


def eval_log_odds_cutoff(feature_comparisons: list, **kwargs) -> bool:
    """
    Determines whether a given set of feature comparisons matches enough
    to be the result of a true patient link instead of just random chance.
    This is represented using previously computed log-odds ratios.

    :param feature_comparisons: A list of floats representing the log-odds
      score of each field computed on.
    :return: Whether the feature comparisons score well enough to be
      considered a match.
    """
    if "true_match_threshold" not in kwargs:
        raise KeyError("Cutoff threshold for true matches must be passed.")
    return sum(feature_comparisons) >= kwargs["true_match_threshold"]


def feature_match_any(
    record: PIIRecord, patient: Patient, key: Feature, **kwargs: dict
) -> float:
    """
    ...

    :param record: The incoming record to evaluate.
    :param patient: The patient record to compare against.
    :param key: The name of the column being evaluated (e.g. "city").
    :return: A float indicating whether the features are an exact match.
    """
    rec_values = set(record.field_iter(key))
    if not rec_values:
        return 0
    pat_values = set(patient.record.field_iter(key))
    return float(bool(rec_values & pat_values))


# TODO: rename to feature_match_all
def feature_match_exact(
    record: PIIRecord, patient: Patient, key: Feature, **kwargs: dict
) -> float:
    """
    ...

    :param record: The incoming record to evaluate.
    :param patient: The patient record to compare against.
    :param key: The name of the column being evaluated (e.g. "city").
    :return: A float indicating whether the features are an exact match.
    """
    rec_values = set(record.field_iter(key))
    if not rec_values:
        return 0
    pat_values = set(patient.record.field_iter(key))
    return float(rec_values == pat_values)


# TODO: rename to feature_match_fuzzy_any
def feature_match_fuzzy_string(
    record: PIIRecord, patient: Patient, key: Feature, **kwargs: dict
) -> float:
    """
    ...

    :param record: The incoming record to evaluate.
    :param patient: The patient record to compare against.
    :param key: The name of the column being evaluated (e.g. "city").
    :param **kwargs: Optionally, a dictionary including specifications for
      the string comparison metric to use, as well as the cutoff score
      beyond which to classify the strings as a partial match.
    :return: A float indicating whether the features are a fuzzy match.
    """
    similarity_measure, threshold = _get_fuzzy_params(str(key), **kwargs)
    comp_func = getattr(rapidfuzz.distance, similarity_measure).normalized_similarity
    for x in record.field_iter(key):
        for y in patient.record.field_iter(key):
            score = comp_func(x, y)
            if score >= threshold:
                return 1
    return 0


# TODO: rename to feature_match_log_odds_fuzzy_any
def feature_match_log_odds_fuzzy_compare(
    record: PIIRecord, patient: Patient, key: Feature, **kwargs: dict
) -> float:
    """
    ...

    :param record: The incoming record to evaluate.
    :param patient: The patient record to compare against.
    :param key: The name of the column being evaluated (e.g. "city").
    :param **kwargs: Optionally, a dictionary including specifications for
      the string comparison metric to use, as well as the cutoff score
      beyond which to classify the strings as a partial match.
    :return: A float of the score the feature comparison earned.
    """
    log_odds = kwargs.get("log_odds", {}).get(str(key))
    if log_odds is None:
        raise ValueError(f"Log odds not found for feature {key}")

    similarity_measure, threshold = _get_fuzzy_params(str(key), **kwargs)
    comp_func = getattr(rapidfuzz.distance, similarity_measure).normalized_similarity
    max_score = 0.0
    for x in patient.record.field_iter(key):
        for y in record.field_iter(key):
            # for each permutation of values, find the score and record it if its
            # larger than any previous score
            max_score = max(comp_func(x, y), max_score)
    if max_score < threshold:
        # return 0 if our max score is less than the threshold
        return 0.0
    return max_score * log_odds
