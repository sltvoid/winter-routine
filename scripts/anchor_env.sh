#!/usr/bin/env bash
# Compute date anchors once and persist only non-secret values for later shells.
set -euo pipefail

out="${1:-/tmp/morning_briefing_dates.env}"
today_et="${TODAY_ET:-$(TZ=America/Toronto date +%F)}"
yesterday_et="${YESTERDAY_ET:-$(TZ=America/Toronto date -v-1d +%F 2>/dev/null || TZ=America/Toronto date -d 'yesterday' +%F)}"
pipeline_id="${PIPELINE_ID:-$(python3 -c 'import uuid; print(uuid.uuid4())')}"
yesterday_dow="${YESTERDAY_DAY_OF_WEEK:-$(TZ=America/Toronto date -v-1d +%A 2>/dev/null || TZ=America/Toronto date -d 'yesterday' +%A)}"
today_dow="${TODAY_DAY_OF_WEEK:-$(TZ=America/Toronto date +%A)}"

umask 077
cat > "$out" <<EOF
export TODAY_ET='$today_et'
export YESTERDAY_ET='$yesterday_et'
export PIPELINE_ID='$pipeline_id'
export YESTERDAY_DAY_OF_WEEK='$yesterday_dow'
export TODAY_DAY_OF_WEEK='$today_dow'
EOF

export TODAY_ET="$today_et"
export YESTERDAY_ET="$yesterday_et"
export PIPELINE_ID="$pipeline_id"
export YESTERDAY_DAY_OF_WEEK="$yesterday_dow"
export TODAY_DAY_OF_WEEK="$today_dow"

echo "anchor_env.sh: ok TODAY_ET=$TODAY_ET YESTERDAY_ET=$YESTERDAY_ET PIPELINE_ID=$PIPELINE_ID"
