#!/bin/sh
#
# Run mypy on new files changed or added in git.
#
# Usage: scripts/check_types.sh <python-path> <python-path>
#
# <python-path> is the path to run with mypy. If not specified, mypy with run
# off of the files found in git status. You can run multiple paths with mypy
set -e

cd "$(dirname "$0")/.."

PATHS=${*:-$(git status -s | sed "s@^[^ ]* @$PWD/@")}

# non_python_list=()
# for p in ${PATHS}; do
#   echo "$p"
#   if [[ $p == *.py ]]; then
#       mypy $p --ignore-missing-imports
#   else
#       non_python_list+=(1)
#   fi
# done

full_directory() {
  for p in ${PATHS}**/*/; do
    target="src/recordlinker/linkage/"
    if [ "$p" != "$target" ]; then
      for f in $p**; do
        mypy "$f" --ignore-missing-imports --follow-imports=skip
      done
    fi
  done
}

single_files() {
  non_python_list=()
  for p in ${PATHS}; do
    if [[ $p == *.py ]]; then
        echo "$p"
        mypy $p --ignore-missing-imports --follow-imports=skip
    fi
  done

  if [[ -n ${non_python_list[@]} ]]; then
      echo "Either no git changes or no python files"
  fi
}

if [[ -d $PATHS  ]]; then
    echo "from full dir"
    full_directory
else
    echo "from single dir"
    single_files
fi

