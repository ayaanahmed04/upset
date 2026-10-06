#!/usr/bin/env bash
# Refresh division logic and reviewed metadata without rewriting the database.
set -euo pipefail
upset_update_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd ~/Projects/upset
source .venv/bin/activate
test -f "$upset_update_dir/backend.patch"
test -f "$upset_update_dir/research.html"
upset_database="data/processed/research_rahiki_v1/upset.sqlite"
test -f "$upset_database"

if git apply --reverse --check "$upset_update_dir/backend.patch" 2>/dev/null; then
  upset_backend_installed=true
else
  git apply --check "$upset_update_dir/backend.patch"
  upset_backend_installed=false
fi

upset_backup="data/processed/site_backups/division-update-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$upset_backup"
cp src/upset/web/research.html "$upset_backup/research.html"
cp src/upset/research_app.py "$upset_backup/research_app.py"
cp src/upset/data/reviewed_bout_metadata.py "$upset_backup/reviewed_bout_metadata.py"
if [ "$upset_backend_installed" = false ]; then
  git apply "$upset_update_dir/backend.patch"
fi

python - <<'PY'
from pathlib import Path
from upset.research_app import connect, fighter_report, search
p = Path('data/processed/research_rahiki_v1/upset.sqlite')
with connect(p) as db:
    for name, uid, division, titles in (
        ('Alex Pereira', 'bb826765-47c1-4238-9c17-f77e59518192', 'Heavyweight', 9),
        ('Ilia Topuria', '7a1b1eb6-1471-4f85-987c-d77c340947eb', 'Lightweight', 4),
    ):
        report = fighter_report(db, uid, '2026-10-04', 0)
        assert report['summary']['division'] == division, f'{name}: wrong division'
        assert report['summary']['title_bouts'] == titles, f'{name}: title metadata check failed'
        assert next(hit for hit in search(db, name, '2026-10-04') if hit['id'] == uid)['division'] == division
        print(f'Checked: {name} — {division}, {titles} title fights')
PY

cp "$upset_update_dir/research.html" src/upset/web/research.html
echo "Previous site and backend saved in: $upset_backup"
echo 'Open http://127.0.0.1:8767 and refresh with Cmd+Shift+R.'
caffeinate -i python -m upset.research_app --database "$upset_database" --port 8767
