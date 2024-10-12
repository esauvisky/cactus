#!/usr/bin/env bash
set -o errexit; set -o errtrace; set -o pipefail # Exit on errors
# Uncomment line below for debugging:
#PS4=$'+ $(tput sgr0)$(tput setaf 4)DEBUG ${FUNCNAME[0]:+${FUNCNAME[0]}}$(tput bold)[$(tput setaf 6)${LINENO}$(tput setaf 4)]: $(tput sgr0)'; set -o xtrace
__deps=( "sed" "grep" )
for dep in ${__deps[@]}; do hash $dep >& /dev/null || (echo "$dep was not found. Please install it and try again." && exit 1); done

rm -r dist build *.egg-info || true
pip install --upgrade setuptools wheel twine --break-system-packages
python setup.py sdist bdist_wheel
twine upload dist/*

