import json
from http.server import ThreadingHTTPServer
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from worldos_core.web_console_extensions import make_console_handler


def request_json(url: str, *, method: str = "GET", payload=None, cookie: str | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers.items()), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), json.loads(exc.read().decode("utf-8"))


def test_extended_console_creates_chinese_world_and_deletes_it(tmp_path):
    handler = make_console_handler(tmp_path / "world.db")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert "删除世界" in html
        assert "确定删除世界" in html

        status, _, created = request_json(
            base + "/api/worlds",
            method="POST",
            payload={
                "name": "临安测试镇",
                "world_type": "agrarian_town",
                "era": "agrarian",
                "population": 4,
                "location_count": 6,
                "resource_abundance": 50,
                "social_stability": 60,
                "conflicts": ["resource_scarcity"],
                "seed": "zh-test",
            },
        )
        assert status == 201
        world_id = created["world"]["world_id"]
        db_path = tmp_path / "worlds" / f"{world_id}.db"
        assert db_path.exists()

        with urlopen(base + created["inspect_url"], timeout=5) as response:
            inspector_html = response.read().decode("utf-8")
            cookie = response.headers["Set-Cookie"].split(";", 1)[0]
        assert ".actor-id,.profile-id{display:none}" in inspector_html
        assert "grain:'粮食'" in inspector_html
        assert "function actorLabel(id)" in inspector_html
        assert "${esc(actorLabel(id))}</button>" in inspector_html
        assert "${esc(actorLabel(actor))}" in inspector_html
        assert "visibleEvents=events.filter" in inspector_html
        assert "actorLabel(n.perspective_actor_id)" in inspector_html

        status, _, overview = request_json(base + "/api/overview?timeline=main", cookie=cookie)
        assert status == 200
        assert overview["summary"]["flags"]["locations"] == ["农田", "集市", "民居", "寺庙", "工坊", "河畔"]
        assert "农田" in overview["map"]
        assert "farm" not in overview["map"]
        assert "river" not in overview["map"]
        assert all(actor["actor_id"].startswith("人物-") for actor in overview["actors"])
        assert all(not actor["actor_id"].startswith("resident-") for actor in overview["actors"])
        assert all("Resident" not in actor["name"] for actor in overview["actors"])

        status, headers, deleted = request_json(base + f"/api/worlds/{world_id}", method="DELETE")
        assert status == 200
        assert deleted["deleted"] is True
        assert "Max-Age=0" in headers.get("Set-Cookie", "")
        assert not db_path.exists()

        _, _, worlds = request_json(base + "/api/worlds")
        assert worlds["worlds"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_extended_console_refuses_legacy_delete(tmp_path):
    legacy = tmp_path / "world.db"
    legacy.touch()
    handler = make_console_handler(legacy)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, _, body = request_json(base + "/api/worlds/first-living-world", method="DELETE")
        assert status == 403
        assert "不能" in body["error"]
        assert legacy.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
