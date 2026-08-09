import json
from http.server import ThreadingHTTPServer
import threading
from urllib.request import Request, urlopen

from worldos_core.web_console_story import make_console_handler


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


def test_story_console_keeps_summary_safety_and_adds_motivation_surface(tmp_path):
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
                "name": "人物动机测试镇",
                "world_type": "agrarian_town",
                "era": "agrarian",
                "population": 6,
                "location_count": 4,
                "resource_abundance": 50,
                "social_stability": 55,
                "conflicts": [],
                "seed": "story-console-test",
            },
        )
        assert status == 201

        with urlopen(base + created["inspect_url"], timeout=10) as response:
            html = response.read().decode("utf-8")

        # PR25 summary layer remains intact.
        assert "当前处境" in html
        assert "最近动态摘要" in html
        assert "function uiObservationDigest" in html

        # New story layer is applied after humanization + summary.
        assert "性格与长期欲望" in html
        assert "function storyProfileSection" in html
        assert "request_resource:'寻求帮助'" in html
        assert "help_resident:'帮助他人'" in html
        assert "social.interacted':'交往'" in html
        assert "storyGoals(a.goals)" in html
        assert "source_motivation" in html

        # Safe explicit-world writes and raw debug surfaces remain available.
        assert "worldosControlWorldId" in html
        assert "body:JSON.stringify({world_id:worldosControlWorldId(),ticks})" in html
        assert "查看该居民原始 JSON" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
