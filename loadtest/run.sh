#!/usr/bin/env bash
# Load test one running stack (plan.md step 5): fan-out GET /posts/{id} at a
# fixed concurrency/duration, plus one write-path run against POST /posts.
# Reused across both stacks — same script, different base URL.
#
# Usage: loadtest/run.sh <label> <base_url>
#   loadtest/run.sh go        http://localhost:8080/api/v1
#   loadtest/run.sh ballerina http://localhost:8081/api/v1
#
# Requires: hey (https://github.com/rakyt/hey), jq, and the target service
# running against a db seeded from ../seed.sql (uses fixed post id 1 and
# alice's known credentials).
set -euo pipefail

LABEL="${1:?usage: run.sh <label> <base_url>}"
BASE_URL="${2:?usage: run.sh <label> <base_url>}"

GET_DURATION="${LOADTEST_GET_DURATION:-30s}"
GET_CONCURRENCY="${LOADTEST_GET_CONCURRENCY:-50}"
POST_DURATION="${LOADTEST_POST_DURATION:-10s}"
POST_CONCURRENCY="${LOADTEST_POST_CONCURRENCY:-10}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$SCRIPT_DIR/results"
mkdir -p "$OUT_DIR"

echo "==> $LABEL: logging in as alice to get a bearer token"
TOKEN=$(curl -sf -X POST "$BASE_URL/auth/login" \
    -H 'Content-Type: application/json' \
    -d '{"email":"alice@example.com","password":"password123"}' | jq -r .token)
if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "error: could not obtain a token from $BASE_URL/auth/login (is the db seeded from seed.sql?)" >&2
    exit 1
fi

echo "==> $LABEL: GET /posts/1 fan-out, ${GET_CONCURRENCY} concurrent for ${GET_DURATION}"
hey -z "$GET_DURATION" -c "$GET_CONCURRENCY" "$BASE_URL/posts/1" | tee "$OUT_DIR/$LABEL-get.txt"

echo "==> $LABEL: POST /posts write path, ${POST_CONCURRENCY} concurrent for ${POST_DURATION}"
hey -z "$POST_DURATION" -c "$POST_CONCURRENCY" -m POST \
    -H "Authorization: Bearer $TOKEN" -T 'application/json' \
    -d '{"title":"load test post","body":"load test body"}' \
    "$BASE_URL/posts" | tee "$OUT_DIR/$LABEL-post.txt"

python3 "$SCRIPT_DIR/summarize.py" "$LABEL" "$OUT_DIR/$LABEL-get.txt" "$OUT_DIR/$LABEL-post.txt" "$OUT_DIR/summary.md"
echo "==> $LABEL: done. Raw output in $OUT_DIR/$LABEL-{get,post}.txt, table in $OUT_DIR/summary.md"
