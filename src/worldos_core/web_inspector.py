from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .inspector import WorldInspector
from .narrator import NarratorReadAPI
from .sqlite_store import SQLiteEventStore


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WorldOS Inspector</title>
<style>
:root{font-family:ui-sans-serif,system-ui;background:#0b1020;color:#e8ecf6}body{margin:0}header{padding:18px 24px;background:#121a31;position:sticky;top:0}main{padding:20px;display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}.card{background:#121a31;border:1px solid #263253;border-radius:12px;padding:16px;min-height:120px}.wide{grid-column:1/-1}h1,h2{margin:0 0 12px}select,input,button{background:#0b1020;color:#e8ecf6;border:1px solid #3a496f;border-radius:6px;padding:8px}pre{white-space:pre-wrap;word-break:break-word;max-height:360px;overflow:auto}.row{display:flex;gap:8px;flex-wrap:wrap}.muted{color:#9cabc9}.actor{cursor:pointer;padding:6px 0;border-bottom:1px solid #263253}
</style></head>
<body><header><h1>WorldOS Web Inspector</h1><div class="row"><input id="timeline" value="main" aria-label="Timeline"><button onclick="loadAll()">Refresh</button><input id="actor" placeholder="actor id"><button onclick="loadActor()">Inspect actor</button><input id="compare" placeholder="compare timeline"><button onclick="loadCompare()">Compare</button></div></header>
<main>
<section class="card"><h2>World</h2><pre id="overview"></pre></section>
<section class="card"><h2>Map</h2><pre id="map"></pre></section>
<section class="card"><h2>Actors</h2><div id="actors"></div></section>
<section class="card"><h2>Actor state</h2><pre id="state"></pre></section>
<section class="card"><h2>Goals & plans</h2><pre id="planning"></pre></section>
<section class="card"><h2>Beliefs & memories</h2><pre id="mind"></pre></section>
<section class="card"><h2>Relationships</h2><pre id="relationships"></pre></section>
<section class="card"><h2>Branch comparison</h2><pre id="comparison"></pre></section>
<section class="card wide"><h2>Event timeline</h2><pre id="events"></pre></section>
<section class="card wide"><h2>Narrator context</h2><pre id="narrator"></pre></section>
</main><script>
const fmt=x=>JSON.stringify(x,null,2);const timeline=()=>document.getElementById('timeline').value;
async function get(path){const r=await fetch(path);if(!r.ok)throw new Error(await r.text());return r.json()}
async function loadAll(){try{const t=encodeURIComponent(timeline());const [o,e,n]=await Promise.all([get('/api/overview?timeline='+t),get('/api/events?timeline='+t+'&limit=200'),get('/api/narrative?timeline='+t)]);overview.textContent=fmt(o.summary);map.textContent=fmt(o.map);relationships.textContent=fmt(o.relationships);events.textContent=fmt(e);narrator.textContent=fmt(n);actors.innerHTML=o.actors.map(a=>`<div class="actor" onclick="document.getElementById('actor').value='${a.actor_id}';loadActor()">${a.actor_id} <span class="muted">${a.location_id||''}</span></div>`).join('')}catch(e){overview.textContent=e}}
async function loadActor(){try{const id=document.getElementById('actor').value;if(!id)return;const a=await get('/api/actor/'+encodeURIComponent(id)+'?timeline='+encodeURIComponent(timeline()));state.textContent=fmt(a.entity);planning.textContent=fmt({goals:a.goals,plan_steps:a.plan_steps});mind.textContent=fmt({beliefs:a.beliefs,memories:a.memories,observations:a.observations});narrator.textContent=fmt(await get('/api/narrative?timeline='+encodeURIComponent(timeline())+'&actor='+encodeURIComponent(id)))}catch(e){state.textContent=e}}
async function loadCompare(){try{comparison.textContent=fmt(await get('/api/compare?left='+encodeURIComponent(timeline())+'&right='+encodeURIComponent(document.getElementById('compare').value)))}catch(e){comparison.textContent=e}}
loadAll();
</script></body></html>"""


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


class WebInspectorService:
    """Read-only projection service used by the Web Inspector HTTP adapter."""

    def __init__(self, store: SQLiteEventStore) -> None:
        self.store = store
        self.inspector = WorldInspector(store)
        self.narrator = NarratorReadAPI(self.inspector)

    def overview(self, timeline_id: str = "main") -> dict[str, Any]:
        snapshot = self.inspector.snapshot(timeline_id)
        actors: list[dict[str, Any]] = []
        locations: dict[str, list[str]] = {}
        relationships: dict[str, Any] = {}
        for entity_id, entity in sorted(snapshot.world.entities.items()):
            components = entity.components
            position = components.get("position", {})
            location_id = position.get("location_id") if isinstance(position, dict) else None
            if entity.kind == "human" or any(key in components for key in ("needs", "health", "memory")):
                actors.append({"actor_id": entity_id, "kind": entity.kind, "location_id": location_id})
            if location_id:
                locations.setdefault(str(location_id), []).append(entity_id)
            if "relationships" in components:
                relationships[entity_id] = components["relationships"]
        return {
            "summary": {
                "timeline": snapshot.timeline,
                "through_sequence": snapshot.through_sequence,
                "event_count": snapshot.event_count,
                "world_hash": snapshot.world_hash,
                "flags": snapshot.world.flags,
                "entity_count": len(snapshot.world.entities),
            },
            "map": {key: sorted(value) for key, value in sorted(locations.items())},
            "actors": actors,
            "relationships": relationships,
        }

    def actor(self, actor_id: str, timeline_id: str = "main") -> dict[str, Any]:
        return _jsonable(self.inspector.actor(actor_id, timeline_id))

    def events(self, timeline_id: str = "main", *, limit: int = 200) -> list[dict[str, Any]]:
        if limit < 1 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")
        events = self.inspector.events(timeline_id)
        return [_jsonable(event) for event in events[-limit:]]

    def narrative(self, timeline_id: str = "main", actor_id: str | None = None) -> dict[str, Any]:
        return _jsonable(self.narrator.context(timeline_id, perspective_actor_id=actor_id))

    def compare(self, left: str, right: str) -> dict[str, Any]:
        left_snapshot = self.inspector.snapshot(left)
        right_snapshot = self.inspector.snapshot(right)
        left_entities = left_snapshot.world.entities
        right_entities = right_snapshot.world.entities
        changed = sorted(
            entity_id
            for entity_id in set(left_entities) | set(right_entities)
            if _jsonable(left_entities.get(entity_id)) != _jsonable(right_entities.get(entity_id))
        )
        return {
            "left": {"timeline_id": left, "sequence": left_snapshot.through_sequence, "world_hash": left_snapshot.world_hash},
            "right": {"timeline_id": right, "sequence": right_snapshot.through_sequence, "world_hash": right_snapshot.world_hash},
            "same_world": left_snapshot.world_hash == right_snapshot.world_hash,
            "changed_entities": changed,
            "flags": {"left": left_snapshot.world.flags, "right": right_snapshot.world.flags},
        }


def make_handler(database_path: str | Path) -> type[BaseHTTPRequestHandler]:
    database = str(database_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(HTTPStatus.OK, HTML, "text/html; charset=utf-8")
                return
            try:
                query = parse_qs(parsed.query)
                timeline = query.get("timeline", ["main"])[0]
                with SQLiteEventStore(database) as store:
                    service = WebInspectorService(store)
                    if parsed.path == "/api/overview":
                        payload = service.overview(timeline)
                    elif parsed.path == "/api/events":
                        payload = service.events(timeline, limit=int(query.get("limit", ["200"])[0]))
                    elif parsed.path.startswith("/api/actor/"):
                        payload = service.actor(parsed.path.removeprefix("/api/actor/"), timeline)
                    elif parsed.path == "/api/narrative":
                        payload = service.narrative(timeline, query.get("actor", [None])[0])
                    elif parsed.path == "/api/compare":
                        payload = service.compare(query.get("left", ["main"])[0], query["right"][0])
                    else:
                        self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                        return
                self._send(HTTPStatus.OK, payload)
            except (KeyError, TypeError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:  # read-only boundary returns a safe error document
                self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})

        def _send(self, status: HTTPStatus, payload: Any, content_type: str = "application/json; charset=utf-8") -> None:
            body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def serve_web_inspector(database_path: str | Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    if not 0 < port < 65536:
        raise ValueError("port must be between 1 and 65535")
    server = ThreadingHTTPServer((host, port), make_handler(database_path))
    try:
        server.serve_forever()
    finally:
        server.server_close()
