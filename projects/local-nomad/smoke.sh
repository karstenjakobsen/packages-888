#!/bin/sh
# Exercise the installed cluster as the provisioned operator.
set -eu
project=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
connector="$project/../../connectors/local-nomad/batch.py"
name="smoke-$(cat /proc/sys/kernel/random/uuid)"
"$connector" ready
"$connector" plan "$name" "$project/examples/squares.py"
"$connector" submit "$name" "$project/examples/squares.py"
# Retain failed jobs for inspection. A successful smoke run cleans up its own job.
"$connector" status "$name"
"$connector" wait "$name"
output=$("$connector" logs "$name")
if [ "$output" != "sum-of-squares=338350" ]; then
    echo "Unexpected sample stdout for $name" >&2
    exit 1
fi
echo "$output"
"$connector" cleanup "$name"
