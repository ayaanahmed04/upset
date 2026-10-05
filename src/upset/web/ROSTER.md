# Optional roster file: ACTIVE badges and fighter images

The research database has no contract status (`profile.status` is null for every
fighter) and no images. Both come from a small hand-maintained JSON file passed at
start-up:

```
python -m upset.research_app \
  --database data/processed/research_v2/upset.sqlite \
  --roster data/roster/roster.json
```

Without `--roster` the site works as before: no ACTIVE badge, monogram portraits.

## Format

```json
{
  "as_of": "2026-10-01",
  "source": "UFC.com athlete roster, checked by hand",
  "fighters": {
    "24565b85-c2c9-4c4f-b2f3-733d3c81c1ed": {
      "status": "active",
      "image": "max-holloway.jpg",
      "image_credit": "Photo: <author>, CC BY-SA 4.0, via Wikimedia Commons",
      "image_kind": "photo"
    }
  }
}
```

- Keys are UPSET fighter IDs (preferred) or UFCStats source fighter IDs. Link
  roster rows through your identity tooling, never by display name alone.
- `status`: `"active"` shows the green ACTIVE badge. Any other string (for example
  `"released"`, `"retired"`) is shown as a neutral badge. Missing means unknown.
- The badge is shown only when the page's "Before" date is on or after `as_of`
  and no more than 62 days later. A later roster observation cannot establish
  status at an earlier date. Missing or stale status remains unknown.
- `image`: a file name in `data/roster/media/` (letters, digits, `-`, `_`;
  jpg/png/webp). It is served at `/media/<name>`. Alternatively `image_url` can
  point to an external URL you are allowed to use.
- Keep an `image_credit` for every image whose licence requires attribution.
