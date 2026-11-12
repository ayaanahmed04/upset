#!/bin/zsh
# Start one verified local release. Snapshots are paired with their exact database.
set -euo pipefail
task_root="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$task_root"
task_port="${UPSET_PORT:-8768}"
task_bind_host="${UPSET_BIND_HOST:-127.0.0.1}"
task_rating_version="${UPSET_RATING_VERSION:-v5}"
task_roster="data/roster/roster.json"
task_historical=()
task_professional=()
task_event_names=()
task_release="${UPSET_DATA_RELEASE:-nov10-coverage}"
case "$task_release" in
  nov10-coverage|nov10-records|nov10-history|nov10-backfill)
    task_review_version="v2"
    task_history_version="v1"
    if [[ "$task_release" == "nov10-coverage" ]]; then
      task_review_version="v3"
      task_history_version="v2"
    fi
    task_rating_suffix="2026_11_10_reviewed_$task_review_version"
    task_rating_top_suffix="$task_rating_suffix"
    task_striking="data/processed/experimental_striking_preview_$task_rating_suffix"
    task_archive="data/processed/cito_current_$task_rating_suffix"
    task_database="data/processed/research_$task_rating_suffix/upset.sqlite"
    task_roster="data/roster/roster_2026_11_10_reviewed_v2.json"
    if [[ "$task_release" != "nov10-backfill" ]]; then
      task_historical=(--historical-results "data/processed/ufc1_results_2026_11_10_$task_history_version")
    fi
    if [[ "$task_release" == "nov10-coverage" ]]; then
      task_event_names=(--event-names "data/processed/event_names_2026_11_10_v1"
        --fighter-aliases "data/processed/fighter_aliases_2026_11_10_v1"
        --provider-audit "data/processed/provider_audit_2026_11_10_v3"
        --market-odds "data/processed/market_odds_2026_11_10_v3"
        --market-archive "data/raw/ufc_market_odds_2026_11_10_v1/kaggle-odds.zip"
        --skill-profiles "data/published/skills/skills_2026_11_12.json")
    fi
    if [[ "$task_release" == "nov10-coverage" || "$task_release" == "nov10-records" ]]; then
      task_professional=(--professional-records "data/roster/pro_records_2026_11_10_$task_history_version.json")
    fi
    ;;
  nov10)
    task_rating_suffix="2026_11_10_reviewed_v1"
    task_rating_top_suffix="$task_rating_suffix"
    task_striking="data/processed/experimental_striking_preview_2026_11_10_reviewed_v1"
    task_archive="data/processed/cito_current_2026_11_10_reviewed_v1"
    task_database="data/processed/research_2026_11_10_reviewed_v1/upset.sqlite"
    ;;
  nov08)
    task_rating_suffix="2026_11_08_reviewed_v1"
    task_rating_top_suffix="$task_rating_suffix"
    task_striking="data/processed/experimental_striking_preview_2026_11_08_reviewed_v1"
    task_archive="data/processed/cito_current_2026_11_08_reviewed_v1"
    task_database="data/processed/research_2026_11_08_reviewed_v1/upset.sqlite"
    ;;
  nov06)
    task_rating_suffix="2026_11_05_backfill_v1"
    task_rating_top_suffix="2026_11_06_backfill_v2"
    task_striking="data/processed/experimental_striking_preview_2026_11_06_backfill_v1"
    task_archive="data/processed/cito_current_2026_11_05_backfill_v1"
    task_database="data/processed/research_2026_11_05_backfill_v1/upset.sqlite"
    ;;
  *) print 'UPSET_DATA_RELEASE must be nov10-coverage, nov10-records, nov10-history, nov10-backfill, nov10, nov08 or nov06.'; exit 1 ;;
esac

if [[ "$task_port" != <1-65535> ]]; then
  print 'UPSET_PORT must be a port from 1 to 65535.'
  exit 1
fi
if /usr/sbin/lsof -nP -iTCP:"$task_port" -sTCP:LISTEN >/dev/null 2>&1; then
  print "Port $task_port is already in use. If UPSET is running, open http://127.0.0.1:$task_port"
  print 'Stop that server before starting a second one.'
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  print 'The UPSET Python environment is missing. See docs/OVERALL_RATING_2026_11_05.md.'
  exit 1
fi
case "$task_rating_version" in
  v5) task_rating="data/processed/overall_rating_v5_1_$task_rating_top_suffix" ;;
  v4) task_rating="data/processed/overall_rating_v4_$task_rating_top_suffix" ;;
  v3) task_rating="data/processed/overall_rating_v3_$task_rating_top_suffix" ;;
  v2) task_rating="data/processed/overall_rating_v2_$task_rating_suffix" ;;
  v1) task_rating="data/processed/overall_rating_$task_rating_suffix" ;;
  *) print 'UPSET_RATING_VERSION must be v5, v4, v3, v2 or v1.'; exit 1 ;;
esac
for task_file in "$task_rating/manifest.json" "$task_striking/manifest.json" "$task_database" "$task_archive/review.json" "$task_roster"; do
  if [[ ! -f "$task_file" ]]; then
    print "Verified UPSET release file is missing: $task_file"
    print 'See docs/RECOVERY_2026_11_06.md for the matching saved snapshots.'
    exit 1
  fi
done
task_forecast=()
if [[ "$task_release" == "nov10-coverage" && "$task_rating_version" == "v5" ]]; then
  task_forecast=(--forecast-adjustment "data/processed/forecast_adjustment_2026_11_12_v1")
fi
if [[ -n "${UPSET_PORTRAIT_SOURCE:-}" ]]; then
  .venv/bin/python scripts/import_fighter_portraits.py --archive "$UPSET_PORTRAIT_SOURCE" \
    --database "$task_database" --registry "$task_archive/fighter_registry.json" --roster "$task_roster"
fi
print "Starting local UPSET with Experimental $task_rating_version. Leave this window running."
exec /usr/bin/caffeinate -i .venv/bin/python -m upset.research_app \
  --database "$task_database" --design broadcast --roster "$task_roster" \
  --coverage-review "$task_archive" --rating-snapshot "$task_rating" \
  --striking-preview "$task_striking" "${task_historical[@]}" "${task_professional[@]}" "${task_event_names[@]}" "${task_forecast[@]}" --host "$task_bind_host" --port "$task_port"
