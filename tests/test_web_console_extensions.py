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


def create_world(base: str, *, name: str, seed: str):
    status, _, created = request_json(
        base + "/api/worlds",
        method="POST",
        payload={
            "name": name,
            "world_type": "agrarian_town",
            "era": "agrarian",
            "population": 4,
            "location_count": 6,
            "resource_abundance": 50,
            "social_stability": 60,
            "conflicts": ["resource_scarcity"],
            "seed": seed,
        },
    )
    assert status == 201
    return created


def enter_world(base: str, created):
    with urlopen(base + created["inspect_url"], timeout=5) as response:
        html = response.read().decode("utf-8")
        cookie = response.headers["Set-Cookie"].split(";", 1)[0]
    return html, cookie


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
        assert "location.href='/'" in html

        created = create_world(base, name="临安测试镇", seed="zh-test")
        world_id = created["world"]["world_id"]
        db_path = tmp_path / "worlds" / f"{world_id}.db"
        assert db_path.exists()

        inspector_html, cookie = enter_world(base, created)
        assert ".actor-id,.profile-id{display:none}" in inspector_html
        assert "grain:'粮食'" in inspector_html
        assert "function actorLabel(id)" in inspector_html
        assert "${esc(actorLabel(id))}</button>" in inspector_html
        assert "${esc(actorLabel(actor))}" in inspector_html
        assert "visibleEvents=events.filter" in inspector_html
        assert "actorLabel(n.perspective_actor_id)" in inspector_html
        assert "function worldosControlWorldId()" in inspector_html
        assert "world_id:worldosControlWorldId()" in inspector_html

        status, _, overview = request_json(base + "/api/overview?timeline=main", cookie=cookie)
        assert status == 200
        assert overview["summary"]["flags"]["locations"] == ["农田", "集市", "民居", "寺庙", "工坊", "河畔"]
        assert "农田" in overview["map"]
        assert "farm" not in overview["map"]
        assert "river" not in overview["map"]
        assert all(actor["actor_id"].startswith("人物-") for actor in overview["actors"])
        assert all(not actor["actor_id"].startswith("resident-") for actor in overview["actors"])
        assert all("Resident" not in actor["name"] for actor in overview["actors"])

        status, _, missing_target = request_json(
            base + "/api/control/run",
            method="POST",
            payload={"ticks": 1},
        )
        assert status == 400
        assert "缺少世界标识" in missing_target["error"]

        _, _, still_zero = request_json(base + "/api/overview?timeline=main", cookie=cookie)
        assert still_zero["summary"]["current_tick"] == 0

        status, _, run = request_json(
            base + "/api/control/run",
            method="POST",
            payload={"world_id": world_id, "ticks": 1},
        )
        assert status == 200
        assert run["world_id"] == world_id
        assert run["before_tick"] == 0
        assert run["after_tick"] == 1

        second = create_world(base, name="安全世界", seed="safe-world")
        second_id = second["world"]["world_id"]
        _, second_cookie = enter_world(base, second)
        _, _, second_before = request_json(base + "/api/overview?timeline=main", cookie=second_cookie)
        assert second_before["summary"]["current_tick"] == 0

        status, headers, deleted = request_json(base + f"/api/worlds/{world_id}", method="DELETE")
        assert status == 200
        assert deleted["deleted"] is True
        assert "Max-Age=0" in headers.get("Set-Cookie", "")
        assert "Expires=" in headers.get("Set-Cookie", "")
        assert not db_path.exists()

        status, stale_headers, stale = request_json(
            base + "/api/control/run",
            method="POST",
            payload={"world_id": world_id, "ticks": 1},
            cookie=cookie,
        )
        assert status == 404
        assert "已删除或不存在" in stale["error"]
        assert "Max-Age=0" in stale_headers.get("Set-Cookie", "")

        _, _, second_after = request_json(base + "/api/overview?timeline=main", cookie=second_cookie)
        assert second_after["summary"]["current_tick"] == 0

        _, _, worlds = request_json(base + "/api/worlds")
        assert [item["world_id"] for item in worlds["worlds"]] == [second_id]
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
