import json
from http.server import ThreadingHTTPServer
import threading
from urllib.request import Request, urlopen

from worldos_core.web_console_summary import make_console_handler


def request_json(url: str, *, method: str = "GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urlopen(request, timeout=10) as response:
        return response.status, dict(response.headers.items()), json.loads(response.read().decode("utf-8"))


def test_world_console_summarizes_routine_activity_and_keeps_debug_data(tmp_path):
    handler = make_console_handler(tmp_path / "world.db")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, _, created = request_json(
            base + "/api/worlds",
            method="POST",
            payload={
                "name": "摘要视图测试镇",
                "world_type": "agrarian_town",
                "era": "agrarian",
                "population": 6,
                "location_count": 4,
                "resource_abundance": 50,
                "social_stability": 60,
                "conflicts": [],
                "seed": "summary-view-test",
            },
        )
        assert status == 201

        with urlopen(base + created["inspect_url"], timeout=10) as response:
            html = response.read().decode("utf-8")

        assert "当前处境" in html
        assert "function uiSituationCard" in html
        assert "function uiObservationDigest" in html
        assert "最近动态摘要" in html
        assert "function uiNarrativeDigest" in html
        assert "健康趋势" in html
        assert "生产汇总" in html

        # The previous human-readable layer and the safe write target invariant
        # remain intact underneath the summary layer.
        assert "function uiFactSentence" in html
        assert "查看该居民原始 JSON" in html
        assert "worldosControlWorldId" in html
        assert "body:JSON.stringify({world_id:worldosControlWorldId(),ticks})" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
