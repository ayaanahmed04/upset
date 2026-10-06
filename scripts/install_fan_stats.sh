#!/usr/bin/env bash
# Apply the small API update, back up the current site, and restart the viewer.
set -euo pipefail
upset_update_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd ~/Projects/upset
source .venv/bin/activate

test -f "$upset_update_dir/backend.patch"
test -f "$upset_update_dir/research.html"
upset_database="data/processed/research_rahiki_v1/upset.sqlite"
if [ ! -f "$upset_database" ]; then
  echo 'The latest research database is missing. Install the previous data update before this update.' >&2
  exit 1
fi

if git apply --reverse --check "$upset_update_dir/backend.patch" 2>/dev/null; then
  upset_backend_installed=true
else
  git apply --check "$upset_update_dir/backend.patch"
  upset_backend_installed=false
fi

upset_backup="data/processed/site_backups/fan-stats-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$upset_backup"
cp src/upset/web/research.html "$upset_backup/research.html"
cp src/upset/research_app.py "$upset_backup/research_app.py"
if [ -f src/upset/data/reviewed_bout_metadata.py ]; then
  cp src/upset/data/reviewed_bout_metadata.py "$upset_backup/reviewed_bout_metadata.py"
fi
cp "$upset_update_dir/backend.patch" "$upset_backup/backend.patch"
if [ "$upset_backend_installed" = false ]; then
  git apply "$upset_update_dir/backend.patch"
fi

python - <<'PY'
from pathlib import Path
from upset.research_app import connect, fighter_report
p = Path('data/processed/research_rahiki_v1/upset.sqlite')
with connect(p) as db:
    report = fighter_report(db, '59b863b8-106c-40e8-93cd-270d7194ecb6', '2026-10-04', 0)
    assert report['summary']['title_bouts'] == 2, 'Khamzat title metadata check failed.'
    assert 'power_durability' in report['metrics'], 'Fan statistics API check failed.'
    print('Checked: Khamzat has 2 title fights; fan statistics API loaded.')
PY

cp "$upset_update_dir/research.html" src/upset/web/research.html
echo "Previous site and backend saved in: $upset_backup"
echo 'Open http://127.0.0.1:8767 and refresh with Cmd+Shift+R.'
caffeinate -i python -m upset.research_app --database "$upset_database" --port 8767
