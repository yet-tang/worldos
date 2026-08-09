import json
from http.server import ThreadingHTTPServer
import threading
from urllib.request import Request, urlopen

from worldos_core.web_console_humanized import make_console_handler


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


def test_resident_view_humanizes_cognition_and_keeps_raw_json(tmp_path):
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
                "name": "认知展示测试镇",
                "world_type": "agrarian_town",
                "era": "agrarian",
                "population": 6,
                "location_count": 4,
                "resource_abundance": 50,
                "social_stability": 60,
                "conflicts": ["resource_scarcity"],
                "seed": "humanized-cognition-test",
            },
        )
        assert status == 201

        with urlopen(base + created["inspect_url"], timeout=10) as response:
            html = response.read().decode("utf-8")

        assert "function uiFactSentence" in html
        assert "function uiMemories" in html
        assert "短期记忆" in html
        assert "经历记忆" in html
        assert "长期认知" in html
        assert "可信度" in html
        assert "优先级" in html
        assert "UI_TECHNICAL_FACTS" in html
        assert "entity.component_set" in html

        # Normal cognition cards no longer dump internal dictionaries inline.
        assert "${esc(fmt(b.data||{}))}" not in html
        assert "${esc(fmt(m.content||{}))}" not in html
        assert "${esc(fmt(o.data||{}))}" not in html

        # The complete developer payload is still available behind the raw-data disclosure.
        assert "查看该居民原始 JSON" in html

        # Existing safety/control enhancements must survive the extra presentation layer.
        assert "worldosControlWorldId" in html
        assert "body:JSON.stringify({world_id:worldosControlWorldId(),ticks})" in html
        assert "actorLabel" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
