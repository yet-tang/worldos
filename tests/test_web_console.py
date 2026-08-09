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
    with urlopen(request, timeout=10) as response:
        return response.status, dict(response.headers.items()), json.loads(response.read().decode("utf-8"))


def create_test_world(base: str):
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
    return created


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
        assert "开发环境 · 世界创世台" in html
        assert "世界种子（用于复现）" in html
        assert "创世 · 运行 · 观察 · 分支" in html
        assert "Development · World Creator" not in html
        assert "CREATE · RUN · OBSERVE · BRANCH" not in html
        assert "World Seed" not in html

        created = create_test_world(base)
        world_id = created["world"]["world_id"]
        assert "database_path" not in created["world"]
        assert created["world"]["world_type_label"] == "古代小镇"
        assert created["world"]["era_label"] == "农业文明"

        with urlopen(base + created["inspect_url"], timeout=5) as response:
            inspector = response.read().decode("utf-8")
            cookie = response.headers["Set-Cookie"].split(";", 1)[0]
        assert "WorldOS 世界观察台" in inspector
        assert "世界控制" in inspector
        assert "运行 1 回合" in inspector
        assert "运行 10 回合" in inspector
        assert "运行 100 回合" in inspector
        assert "世界观察台 2.0" in inspector
        assert "持续演化世界" in inspector
        assert "查看叙事器原始上下文" in inspector
        assert cookie.startswith("worldos_world=")

        status, _, overview = request_json(base + "/api/overview?timeline=main", cookie=cookie)
        assert status == 200
        assert overview["summary"]["flags"]["world_name"] == "测试镇"
        assert len(overview["actors"]) == 6
        assert len(overview["map"]) == 3

        _, _, worlds = request_json(base + "/api/worlds")
        assert [item["world_id"] for item in worlds["worlds"]] == [world_id]
        assert worlds["worlds"][0]["world_type_label"] == "古代小镇"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_world_control_runs_selected_world_and_refreshes_tick(tmp_path):
    handler = make_console_handler(tmp_path / "world.db")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        created = create_test_world(base)
        with urlopen(base + created["inspect_url"], timeout=5) as response:
            cookie = response.headers["Set-Cookie"].split(";", 1)[0]

        _, _, before = request_json(base + "/api/overview?timeline=main", cookie=cookie)
        assert before["summary"]["current_tick"] == 0
        before_events = before["summary"]["event_count"]

        status, _, one = request_json(
            base + "/api/control/run",
            method="POST",
            payload={"ticks": 1},
            cookie=cookie,
        )
        assert status == 200
        assert one["ticks_run"] == 1
        assert one["before_tick"] == 0
        assert one["after_tick"] == 1
        assert one["after_events"] > before_events

        _, _, after_one = request_json(base + "/api/overview?timeline=main", cookie=cookie)
        assert after_one["summary"]["current_tick"] == 1

        status, _, ten = request_json(
            base + "/api/control/run",
            method="POST",
            payload={"ticks": 10},
            cookie=cookie,
        )
        assert status == 200
        assert ten["ticks_run"] == 10
        assert ten["before_tick"] == 1
        assert ten["after_tick"] == 11

        _, _, after_ten = request_json(base + "/api/overview?timeline=main", cookie=cookie)
        assert after_ten["summary"]["current_tick"] == 11
        assert after_ten["summary"]["event_count"] > after_one["summary"]["event_count"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
