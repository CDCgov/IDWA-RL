#!/bin/sh
#
# Run the unit tests for the project.
#
# Usage: scripts/unit_test.sh <test-spec>
#
# <test-spec> is the path to the test file(s) to run. If not specified, all tests
# in the "test/unit/" directory will be run.
#
set -e

cd "$(dirname "$0")/.."

TESTS=${1:-tests/unit/}

# Run the tests
pytest ${TESTS}
