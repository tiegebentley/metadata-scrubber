#!/usr/bin/env bash
# Run the factory loop locally against a real GitHub issue, without waiting
# for the Actions workflow. Requires `gh auth login` and `claude` login done
# already on this machine.
#
# Usage: factory/local_test.sh <issue-number>
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
chmod +x factory/run_factory.sh factory/validate.sh
factory/run_factory.sh "${1:?usage: local_test.sh <issue-number>}"
