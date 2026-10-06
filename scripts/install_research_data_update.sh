#!/usr/bin/env bash
# Install only the reviewed data repair and current HTML; preserve old snapshots.
set -euo pipefail
upset_update_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd ~/Projects/upset
source .venv/bin/activate

test -f "$upset_update_dir/backend.patch"
test -f "$upset_update_dir/research.html"
test -f data/processed/cito_current_refresh_v1/manifest.json
test -f data/raw/cito_fighter_bundles_v1/fighters/9833306c-3365-486b-b8d5-0451a08b32de/fights.json

upset_backup="data/processed/site_backups/data-update-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$upset_backup"
cp src/upset/web/research.html "$upset_backup/research.html"
cp src/upset/data/build_research_db.py "$upset_backup/build_research_db.py"
cp src/upset/data/export_cito_refresh.py "$upset_backup/export_cito_refresh.py"

if git apply --reverse --check "$upset_update_dir/backend.patch" 2>/dev/null; then
  echo 'Backend update already installed.'
else
  git apply --check "$upset_update_dir/backend.patch"
  git apply "$upset_update_dir/backend.patch"
fi

python -m upset.data.integrate_cito_rahiki_identities
python -m upset.data.build_research_db \
  --current data/processed/cito_current_rahiki_v1 \
  --registry data/processed/cito_current_rahiki_v1/fighter_registry.json \
  --output data/processed/research_rahiki_v1

python - <<'PY'
from pathlib import Path
from upset.research_app import route
p = Path('data/processed/research_rahiki_v1/upset.sqlite')
for name, uid, count in (
    ('Harry Hardwick', '20d07fe2-4596-46cc-8fca-a9a35ffa1e09', 2),
    ('Marwan Rahiki', 'a1fc1206-827f-4eef-b8e0-45de11445f33', 3),
    ('Tommy McMillen', '72de8d6d-ee19-4600-bf68-6f4b16db551b', 3),
):
    report = route(p, f'/api/fighter?id={uid}&before=2026-10-04&window=0')
    if len(report['history']) != count:
        raise ValueError(f'{name}: expected {count} linked UFC bouts')
    print(f'Checked: {name} — {count} UFC bouts')
PY

cp "$upset_update_dir/research.html" src/upset/web/research.html
echo "Previous site and backend saved in: $upset_backup"
echo 'Open http://127.0.0.1:8767 and refresh with Cmd+Shift+R.'
echo 'Default Before date: October 4. Leave this terminal running; Ctrl+C stops it.'
caffeinate -i python -m upset.research_app \
  --database data/processed/research_rahiki_v1/upset.sqlite --port 8767
