#!/usr/bin/env bash
# Dated acquisition + offline integration. Existing archive/UI remain in place.
set -eo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source .venv/bin/activate

echo '[1/4] Refreshing the event listing and later UFC cards (September 27–October 5).'
python -m upset.data.refresh_cito_current \
  --root data/raw/cito_refresh_2026_10_05_v1 \
  --from-date 2026-09-27 --through-date 2026-10-05 \
  --max-pages 50 --max-cards 20 --retry-failed

echo '[2/4] Validating new cards and carrying forward reviewed identities.'
python -m upset.data.export_cito_refresh \
  --refresh data/raw/cito_refresh_2026_10_05_v1 \
  --output data/processed/cito_current_refresh_v1

echo '[3/4] Replaying the frozen model; this is a retrospective diagnostic.'
python -m upset.modeling.run_current_replay \
  --current data/processed/cito_current_refresh_v1 \
  --registry data/processed/cito_current_refresh_v1/fighter_registry.json \
  --output data/processed/current_replay_v3

echo '[4/4] Building the updated local research database and review ZIP.'
python -m upset.data.build_research_db \
  --current data/processed/cito_current_refresh_v1 \
  --registry data/processed/cito_current_refresh_v1/fighter_registry.json \
  --output data/processed/research_refresh_v1

zip -q -r data/processed/upset_current_refresh_review_v1.zip \
  data/raw/cito_refresh_2026_10_05_v1 \
  data/processed/cito_current_refresh_v1 \
  data/processed/current_replay_v3 \
  data/processed/research_refresh_v1/manifest.json

echo 'Finished. Review ZIP: data/processed/upset_current_refresh_review_v1.zip'
echo 'The existing viewer keeps its old database. New viewer instructions: docs/CITO_CURRENT_REFRESH.md'
if command -v open >/dev/null 2>&1; then
  open -R data/processed/upset_current_refresh_review_v1.zip
fi
