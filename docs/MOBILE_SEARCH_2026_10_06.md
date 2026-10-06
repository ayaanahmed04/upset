# Mobile search follow-up — October 6, 2026 UTC

Ayaan's IMG_3763 phone screenshot confirms the original broadcast site and
square controls are installed. Same-Wi-Fi access is working at the observed
Mac address `http://192.168.4.23:8767`. The screen also shows search results
underneath the homepage text, a narrow header layout and apparent focus zoom.

The mobile header now establishes a positioned stacking context above the
main content. Search occupies its own full-width row, underneath the logo and
controls. Results have an opaque surface, wrap long names, use larger tap
targets and scroll independently. Both search and date inputs use 16px text
to avoid Safari's focus zoom. Zoom remains available to the user.

Dropdown height responds to the visual viewport so the software keyboard does
not cover the bottom of the list. Desktop retains its 420px maximum. The mobile
header remains in normal scrolling flow. Broadcast styling, square corners,
Ayaan's biography, APIs, database and model remain as before.

Delivery: `upset-mobile-search.html`, an installation file containing the
shared About CSS/JS inline for compatibility with Ayaan's existing server.
Back up `src/upset/web/research.html`, then replace only that file. The server
reads HTML per request, so refresh the browser; restarting is unnecessary.
Source logic checks pass; final iPhone appearance needs Ayaan's review after
installation. No rendered browser check was available in this workspace.

## Network follow-up

The temporary Cloudflare link returned a plain Bad Request page. Ayaan abandoned
that route. No persistent server configuration was changed. Stop any old tunnel
with Ctrl+C in its own terminal tab.

The ordinary server binds to 127.0.0.1, which cannot be reached from a phone.
For same-Wi-Fi access, the successful launch uses this runtime wrapper:

```bash
cd ~/Projects/upset
source .venv/bin/activate
caffeinate -i python - \
  --database data/processed/research_v2/upset.sqlite \
  --port 8767 <<'PY'
from http.server import ThreadingHTTPServer
from subprocess import check_output
import upset.research_app as app

ip = check_output(["ipconfig", "getifaddr", "en0"], text=True).strip()
app.ThreadingHTTPServer = lambda address, handler: ThreadingHTTPServer(
    ("0.0.0.0", address[1]), handler)
print(f"\nPHONE LINK: http://{ip}:8767\n", flush=True)
app.main()
PY
```

Stop the old server first if restarting with this command. Use the printed
PHONE LINK on the phone, not 127.0.0.1. The IP can change. Keep the Mac awake,
lid open, on the same trusted Wi-Fi and leave the terminal running. This binds
to the Mac's network interfaces; no public tunnel or router forwarding is
needed. Ctrl+C stops it without changing source files or the read-only database.
