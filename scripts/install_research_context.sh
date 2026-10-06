#!/usr/bin/env bash
# One offline update; preserve the current HTML/backend and never rewrite SQLite.
set -euo pipefail
upset_update_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd ~/Projects/upset
source .venv/bin/activate
upset_database="data/processed/research_rahiki_v1/upset.sqlite"
test -f "$upset_database"
test -f "$upset_update_dir/research.html"

upset_patch=""
upset_installed=false
for upset_candidate in backend-after-division.patch backend-before-division.patch; do
  if git apply --reverse --check "$upset_update_dir/$upset_candidate" 2>/dev/null; then
    upset_installed=true
    break
  fi
  if git apply --check "$upset_update_dir/$upset_candidate" 2>/dev/null; then
    upset_patch="$upset_update_dir/$upset_candidate"
    break
  fi
done
if [ "$upset_installed" = false ] && [ -z "$upset_patch" ]; then
  echo 'Your backend differs from both supported versions. No files were changed.' >&2
  exit 1
fi

upset_backup="data/processed/site_backups/research-context-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$upset_backup"
for upset_path in src/upset/research_app.py src/upset/research_context.py \
  src/upset/data/reviewed_bout_metadata.py src/upset/web/research_methodology.js \
  src/upset/web/research.html; do
  if [ -f "$upset_path" ]; then
    mkdir -p "$upset_backup/$(dirname "$upset_path")"
    cp -p "$upset_path" "$upset_backup/$upset_path"
  else
    printf '%s\n' "$upset_path" >> "$upset_backup/new-files.txt"
  fi
done
cat > "$upset_backup/restore.sh" <<'RESTORE'
#!/usr/bin/env bash
set -euo pipefail
upset_saved="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd ~/Projects/upset
for upset_path in src/upset/research_app.py src/upset/research_context.py \
  src/upset/data/reviewed_bout_metadata.py src/upset/web/research_methodology.js \
  src/upset/web/research.html; do
  if [ -f "$upset_saved/$upset_path" ]; then
    cp -p "$upset_saved/$upset_path" "$upset_path"
  fi
done
if [ -f "$upset_saved/new-files.txt" ]; then
  while IFS= read -r upset_path; do rm -f "$upset_path"; done < "$upset_saved/new-files.txt"
fi
echo 'Previous source files restored. The database was untouched.'
RESTORE

upset_rollback() {
  echo 'Update verification failed. Restoring the previous source files.' >&2
  bash "$upset_backup/restore.sh"
}
trap upset_rollback ERR
if [ "$upset_installed" = false ]; then git apply "$upset_patch"; fi
cp "$upset_update_dir/research.html" src/upset/web/research.html

python - <<'PY'
import hashlib
from pathlib import Path
from upset.research_app import route
p = Path('data/processed/research_rahiki_v1/upset.sqlite')
digest = hashlib.sha256(p.read_bytes()).hexdigest()
for name, uid, division, titles in (
    ('Alex Pereira', 'bb826765-47c1-4238-9c17-f77e59518192', 'Heavyweight', 9),
    ('Ilia Topuria', '7a1b1eb6-1471-4f85-987c-d77c340947eb', 'Lightweight', 4),
):
    report = route(p, f'/api/fighter?id={uid}&before=2026-10-04&window=0')
    assert report['summary']['division'] == division
    assert report['summary']['title_bouts'] == titles
    assert report['metrics']['opponent_records']['bouts'] == report['metrics']['bouts']
    control = report['metrics']['control_shares']
    if control['observed_seconds']:
        assert abs(sum(control[k] for k in (
            'in_control_fraction', 'controlled_fraction', 'neither_credited_fraction')) - 1) < 1e-12
    assert 'knockdowns_received_per_100_sig_absorbed' in report['metrics']['power_durability']
    print(f'Checked: {name} — division, title count and research context')
assert hashlib.sha256(p.read_bytes()).hexdigest() == digest
print('Database unchanged. No API requests made.')
PY
trap - ERR
echo "Previous source saved in: $upset_backup"
echo "To revert after stopping the viewer: bash $upset_backup/restore.sh"
echo 'Open http://127.0.0.1:8767 and refresh with Cmd+Shift+R.'
caffeinate -i python -m upset.research_app --database "$upset_database" --port 8767
