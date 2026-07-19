"""Playwright spot-check for Stage 7: Overview page renders updated insights, no errors."""
import time, sys, http.server, socketserver, threading, os
from playwright.sync_api import sync_playwright

PORT = 8203
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
def serve():
    os.chdir("frontend/dist")
    with socketserver.TCPServer(("127.0.0.1", PORT), H) as h: h.serve_forever()
threading.Thread(target=serve, daemon=True).start(); time.sleep(1)

errors = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"http://127.0.0.1:{PORT}/#/", wait_until="networkidle"); pg.wait_for_timeout(1500)
    body = pg.inner_text("body")
    # insight #1 reframed + folds in [37]/[39]
    assert "no improvement outlasted it" in body, "insight #1 not reframed"
    assert "taken on notice" in body, "[37] not folded into synthesis"
    assert "durable-improvement" in body, "[39] durable-hunt verdict missing"
    assert "nothing changed for keeps" in body, "[39] verdict sentence missing"
    # insight #8 credit adds [36] + [35]
    assert "least" in body and "1.6%" in body, "[36] credit numbers missing"
    assert "decider-tied supplier" in body, "[35] credit missing"
    cards = pg.query_selector_all(".overview-insight")
    print(f"[ok] Overview renders {len(cards)} insight cards; [37]/[39]/[36]/[35] folded in")
    b.close()
print("Console/page errors:", errors if errors else "NONE")
sys.exit(1 if errors else 0)
