import json
from http.server import ThreadingHTTPServer
import threading
from urllib.request import Request, urlopen

from worldos_core.web_console import make_console_handler


def request_json(url: str, *, method: str = "GET", payload=None, cookie: str | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=5) as response:
        return response.status, dict(response.headers.items()), json.loads(response.read().decode("utf-8"))


def test_console_creates_world_and_routes_inspector_to_it(tmp_path):
    handler = make_console_handler(tmp_path / "world.db")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert "我的世界" in html
        assert "创建新世界" in html

        status, _, created = request_json(
            base + "/api/worlds",
            method="POST",
            payload={
                "name": "测试镇",
                "world_type": "agrarian_town",
                "era": "agrarian",
                "population": 6,
                "location_count": 3,
                "resource_abundance": 40,
                "social_stability": 50,
                "conflicts": ["resource_scarcity"],
                "seed": "test-seed",
            },
        )
        assert status == 201
        world_id = created["world"]["world_id"]
        assert "database_path" not in created["world"]

        with urlopen(base + created["inspect_url"], timeout=5) as response:
            inspector = response.read().decode("utf-8")
            cookie = response.headers["Set-Cookie"].split(";", 1)[0]
        assert "WorldOS 世界观察台" in inspector
        assert cookie.startswith("worldos_world=")

        status, _, overview = request_json(base + "/api/overview?timeline=main", cookie=cookie)
        assert status == 200
        assert overview["summary"]["flags"]["world_name"] == "测试镇"
        assert len(overview["actors"]) == 6
        assert len(overview["map"]) == 3

        _, _, worlds = request_json(base + "/api/worlds")
        assert [item["world_id"] for item in worlds["worlds"]] == [world_id]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
