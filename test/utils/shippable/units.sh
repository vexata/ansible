#!/usr/bin/env bash

set -o pipefail -eux

declare -a args
IFS='/:' read -ra args <<< "$1"

version="${args[1]}"

if [[ "${COVERAGE:-}" ]]; then
    timeout=90
else
    timeout=10
fi

ansible-test env --timeout "${timeout}" --color -v

# shellcheck disable=SC2086
ansible-test units --color -v --docker default --python "${version}" ${COVERAGE:+"$COVERAGE"} ${CHANGED:+"$CHANGED"} \
