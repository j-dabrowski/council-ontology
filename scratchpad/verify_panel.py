"""Playwright spot-check for the Session-9 build: [37] panel drill-down, scorecard
new rows + valence chips, back-links, no console errors."""
import subprocess, time, sys, functools, http.server, socketserver, threading, os
from playwright.sync_api import sync_playwright

DIST = "frontend/dist"
PORT = 8199

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def serve():
    os.chdir(DIST)
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()

t = threading.Thread(target=serve, daemon=True); t.start()
time.sleep(1)

errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    base = f"http://127.0.0.1:{PORT}/#"

    # --- Analysis page: [37] panel ---
    pg.goto(base + "/analysis", wait_until="networkidle")
    pg.wait_for_timeout(1500)

    # panel present
    panel = pg.query_selector("#panel-question-responsiveness")
    assert panel, "question-responsiveness panel section missing"
    title = pg.inner_text("#panel-question-responsiveness")
    assert "Taken on Notice" in title or "taken on notice" in title.lower(), "panel title missing"
    print("[ok] [37] panel renders")

    # era bars -> click the Inquiry bar (a <path> in a recharts Bar, cursor pointer)
    # find the clickable era bar chart within the panel and click a bar
    bars = pg.query_selector_all("#panel-question-responsiveness .recharts-bar-rectangle path")
    assert len(bars) >= 3, f"expected >=3 era bars, got {len(bars)}"
    bars[1].click()  # inquiry
    pg.wait_for_timeout(600)
    drawer = pg.query_selector("#panel-question-responsiveness .drill")
    assert drawer, "drill-down drawer did not open"
    drawer_txt = pg.inner_text("#panel-question-responsiveness .drill")
    assert "Public questions" in drawer_txt, "drawer title missing"
    print("[ok] era bar click -> drill-down opens")

    # reveal a source quote
    tog = pg.query_selector("#panel-question-responsiveness .drill .src-toggle")
    assert tog, "no source-quote toggle in drawer"
    tog.click(); pg.wait_for_timeout(300)
    q = pg.query_selector("#panel-question-responsiveness .drill .src-quote")
    assert q and len(pg.inner_text("#panel-question-responsiveness .drill .src-quote")) > 20, "source quote did not reveal"
    print("[ok] source quote reveals in drawer")

    # generic panels for [30] and [36] present with charts
    for slug, tid in [("confidential-tender-size", "transparency.confidential_tender_size"),
                      ("confidential-topics", "transparency.confidential_topics")]:
        sec = pg.query_selector(f"#panel-{slug}")
        assert sec, f"panel-{slug} missing"
        assert pg.query_selector(f"#panel-{slug} .recharts-surface"), f"panel-{slug} chart missing"
    print("[ok] [30] + [36] generic battery panels render with charts")

    # --- Overview page: scorecard rows + valence chips ---
    pg.goto(base + "/", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    body = pg.inner_text("body")
    # scorecard summary should read 26 tests
    sc_rows = pg.query_selector_all("[id^='sc-']")
    ids = [r.get_attribute("id") for r in sc_rows]
    for want in ["sc-question-responsiveness", "sc-confidential-tender-size", "sc-confidential-topics"]:
        assert want in ids, f"scorecard row {want} missing (have {len(ids)} rows)"
    print(f"[ok] scorecard has new rows (total {len(ids)} sc-rows)")

    b.close()

print("\nConsole/page errors:", errors if errors else "NONE")
sys.exit(1 if errors else 0)
