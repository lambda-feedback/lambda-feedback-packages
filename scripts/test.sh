#!/usr/bin/env sh
# Run every package's test suite, each in its own pytest process: every
# package has a `tests` package, and one pytest process cannot import two
# same-named packages. Extra arguments are passed through to pytest.
#
#   poetry run scripts/test.sh -q
set -e
cd "$(dirname "$0")/.."
for pkg in slr_parsing criteria expression_parsing units; do
    echo "== $pkg"
    pytest "$pkg/tests" "$@"
done
