from __future__ import annotations

import json
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .web_inspector import HTML as INSPECTOR_HTML
from .web_inspector import WebInspectorService, _jsonable
from .sqlite_store import SQLiteEventStore
from .world_creator import WorldCatalog, WorldConfig


CREATOR_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>WorldOS · 我的世界</title>
<style>
:root{font-family:Inter,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;color:#edf2ff;background:#070c16;--panel:#111a2a;--line:#273650;--muted:#91a1bb;--accent:#7dd3fc;--good:#86efac;--warn:#fde68a}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 15% 0,#132846 0,transparent 35%),#070c16;min-height:100vh}button,input,select{font:inherit}button{cursor:pointer}.shell{max-width:1260px;margin:auto;padding:28px 22px 60px}.top{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:28px}.brand{display:flex;gap:12px;align-items:center}.mark{width:42px;height:42px;border-radius:13px;display:grid;place-items:center;font-weight:800;background:linear-gradient(145deg,#2563eb,#0891b2)}h1{font-size:21px;margin:0}.muted{color:var(--muted)}.hero{padding:32px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(145deg,rgba(21,33,54,.96),rgba(13,23,39,.92));margin-bottom:20px}.hero .eyebrow{font-size:11px;letter-spacing:.16em;color:var(--accent);font-weight:800}.hero h2{font-size:36px;margin:8px 0 8px}.hero p{max-width:760px;line-height:1.75;margin:0;color:#aab9cf}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card{background:rgba(17,26,42,.94);border:1px solid var(--line);border-radius:18px;padding:20px}.card h3{margin:0 0 5px}.worlds{display:flex;flex-direction:column;gap:10px;margin-top:16px}.world{border:1px solid var(--line);background:#0c1524;border-radius:14px;padding:15px;display:grid;grid-template-columns:1fr auto;gap:12px}.world-title{font-size:17px;font-weight:750}.tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.tag{font-size:11px;color:#c9ddf5;background:#172941;border-radius:999px;padding:4px 7px}.btn{border:1px solid #365274;border-radius:10px;padding:9px 12px;background:#10213a;color:#d8edff}.btn.primary{background:#e6f6ff;color:#071b2d;border-color:#d4efff;font-weight:760}.btn:hover{filter:brightness(1.08)}form{display:flex;flex-direction:column;gap:16px;margin-top:16px}.step{border-top:1px solid #20304a;padding-top:14px}.step:first-child{border-top:0;padding-top:0}.step-title{font-size:12px;color:var(--accent);font-weight:750;letter-spacing:.06em;margin-bottom:10px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}.field{display:flex;flex-direction:column;gap:6px}.field.full{grid-column:1/-1}label{font-size:12px;color:#b9c8dc}input,select{width:100%;border:1px solid #30435f;border-radius:10px;padding:10px;background:#0b1422;color:#edf2ff}.range-row{display:grid;grid-template-columns:1fr 52px;gap:9px;align-items:center}.range-row input[type=range]{padding:0}.checks{display:grid;grid-template-columns:1fr 1fr;gap:7px}.check{display:flex;gap:7px;align-items:center;padding:8px;border:1px solid #253650;border-radius:10px;background:#0c1524;font-size:12px}.check input{width:auto}.notice{font-size:12px;color:var(--muted);line-height:1.65;background:#0b1422;border:1px solid #22324a;border-radius:10px;padding:10px}.success{color:var(--good)}.error{color:#fca5a5}.empty{padding:24px;border:1px dashed var(--line);border-radius:13px;text-align:center;color:var(--muted)}@media(max-width:850px){.grid{grid-template-columns:1fr}.hero h2{font-size:29px}.fields,.checks{grid-template-columns:1fr}.field.full{grid-column:auto}.world{grid-template-columns:1fr}}
</style></head>
<body><div class="shell">
<div class="top"><div class="brand"><div class="mark">W</div><div><h1>WorldOS</h1><div class="muted">Development · World Creator</div></div></div><div class="muted">创世台 v0.1</div></div>
<section class="hero"><div class="eyebrow">CREATE · RUN · OBSERVE · BRANCH</div><h2>我的世界</h2><p>每个世界都有独立的初始条件、居民、资源与矛盾。创世配置会先被编译成标准 Event Batch，再交给 WorldOS Runtime；配置本身不会绕过事件账本直接修改世界。</p></section>
<div class="grid">
<section class="card"><h3>已有世界</h3><div class="muted">进入任意世界后使用 Inspector 观察它。</div><div id="worlds" class="worlds"><div class="empty">正在读取世界…</div></div></section>
<section class="card"><h3>创建新世界</h3><div class="muted">快速创世 · 先定义初始条件，再让世界自己演化。</div>
<form id="createForm">
<div class="step"><div class="step-title">01 · 基础设定</div><div class="fields">
<div class="field full"><label>世界名称</label><input id="name" maxlength="80" required value="临安镇"></div>
<div class="field"><label>世界类型</label><select id="worldType"><option value="agrarian_town">古代小镇</option><option value="modern_community">现代社区</option><option value="island_survival">荒岛生存</option><option value="mars_colony">火星殖民地</option><option value="custom">自定义</option></select></div>
<div class="field"><label>文明阶段</label><select id="era"><option value="primitive">原始</option><option value="agrarian" selected>农业</option><option value="industrial">工业</option><option value="modern">现代</option><option value="future">未来</option></select></div>
<div class="field"><label>居民数量</label><input id="population" type="number" min="1" max="200" value="24"></div>
<div class="field"><label>地点数量</label><input id="locationCount" type="number" min="1" max="20" value="6"></div>
</div></div>
<div class="step"><div class="step-title">02 · 世界压力</div><div class="fields">
<div class="field full"><label>资源丰度 · <span id="resourceValue">55</span></label><div class="range-row"><input id="resource" type="range" min="0" max="100" value="55"><span>富饶</span></div></div>
<div class="field full"><label>社会稳定度 · <span id="stabilityValue">60</span></label><div class="range-row"><input id="stability" type="range" min="0" max="100" value="60"><span>稳定</span></div></div>
</div></div>
<div class="step"><div class="step-title">03 · 初始矛盾</div><div class="checks">
<label class="check"><input type="checkbox" name="conflict" value="resource_scarcity" checked>资源短缺</label>
<label class="check"><input type="checkbox" name="conflict" value="inequality">阶层差异</label>
<label class="check"><input type="checkbox" name="conflict" value="external_threat">外部威胁</label>
<label class="check"><input type="checkbox" name="conflict" value="disease">疫病</label>
<label class="check"><input type="checkbox" name="conflict" value="power_struggle">权力斗争</label>
</div></div>
<div class="step"><div class="step-title">04 · 可重复性</div><div class="field"><label>World Seed</label><input id="seed" maxlength="120" value="linan-001"></div><div class="notice" style="margin-top:9px">相同配置 + 相同 Seed 会编译出同一批初始世界事件。创建后的世界使用独立 SQLite 数据库，不会修改其他世界。</div></div>
<button class="btn primary" id="createBtn" type="submit">创建世界并进入</button><div id="message"></div>
</form></section>
</div></div>
<script>
const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
$('resource').oninput=()=>$('resourceValue').textContent=$('resource').value;$('stability').oninput=()=>$('stabilityValue').textContent=$('stability').value;
$('worldType').onchange=()=>{const m={agrarian_town:'agrarian',modern_community:'modern',island_survival:'primitive',mars_colony:'future'};if(m[$('worldType').value])$('era').value=m[$('worldType').value]};
async function api(path,opts){const r=await fetch(path,opts);let body={};try{body=await r.json()}catch{}if(!r.ok)throw new Error(body.error||r.statusText);return body}
async function loadWorlds(){try{const data=await api('/api/worlds');if(!data.worlds.length){$('worlds').innerHTML='<div class="empty">还没有世界。创建第一个吧。</div>';return}$('worlds').innerHTML=data.worlds.map(w=>`<div class="world"><div><div class="world-title">${esc(w.name)}</div><div class="tags"><span class="tag">${esc(w.world_type)}</span><span class="tag">${esc(w.era)}</span><span class="tag">${w.population} 居民</span><span class="tag">${w.location_count} 地点</span>${w.legacy?'<span class="tag">开发样板</span>':''}</div><div class="muted" style="font-size:11px;margin-top:8px">${esc(w.world_id)}</div></div><div><button class="btn" onclick="location.href='/world/${encodeURIComponent(w.world_id)}'">进入世界</button></div></div>`).join('')}catch(e){$('worlds').innerHTML=`<div class="error">${esc(e.message)}</div>`}}
$('createForm').onsubmit=async e=>{e.preventDefault();$('createBtn').disabled=true;$('message').textContent='正在编译创世事件…';$('message').className='muted';try{const config={name:$('name').value,world_type:$('worldType').value,era:$('era').value,population:Number($('population').value),location_count:Number($('locationCount').value),resource_abundance:Number($('resource').value),social_stability:Number($('stability').value),conflicts:[...document.querySelectorAll('input[name=conflict]:checked')].map(x=>x.value),seed:$('seed').value};const result=await api('/api/worlds',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});$('message').textContent='世界已创建，正在进入…';$('message').className='success';location.href=result.inspect_url}catch(e){$('message').textContent=e.message;$('message').className='error';$('createBtn').disabled=false}};
loadWorlds();
</script></body></html>"""


def _public_descriptor(item: Any) -> dict[str, Any]:
    payload = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
    payload.pop("database_path", None)
    return payload


def _cookie_world(headers: Any) -> str | None:
    raw = headers.get("Cookie")
    if not raw:
        return None
    cookie = SimpleCookie()
    cookie.load(raw)
    morsel = cookie.get("worldos_world")
    return morsel.value if morsel else None


def make_console_handler(database_path: str | Path) -> type[BaseHTTPRequestHandler]:
    legacy_database = Path(database_path)
    catalog = WorldCatalog(legacy_database.parent, legacy_db_path=legacy_database)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(HTTPStatus.OK, CREATOR_HTML, "text/html; charset=utf-8")
                return
            if parsed.path.startswith("/world/"):
                world_id = unquote(parsed.path.removeprefix("/world/")).strip("/")
                try:
                    catalog.get(world_id)
                except KeyError as exc:
                    self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                    return
                self._send(
                    HTTPStatus.OK,
                    INSPECTOR_HTML,
                    "text/html; charset=utf-8",
                    extra_headers={"Set-Cookie": f"worldos_world={world_id}; Path=/; SameSite=Lax"},
                )
                return
            try:
                if parsed.path == "/api/worlds":
                    self._send(HTTPStatus.OK, {"worlds": [_public_descriptor(item) for item in catalog.list_worlds()]})
                    return
                database = self._selected_database()
                query = parse_qs(parsed.query)
                timeline = query.get("timeline", ["main"])[0]
                with SQLiteEventStore(database) as store:
                    service = WebInspectorService(store)
                    if parsed.path == "/api/overview":
                        payload = service.overview(timeline)
                    elif parsed.path == "/api/events":
                        payload = service.events(timeline, limit=int(query.get("limit", ["200"])[0]))
                    elif parsed.path.startswith("/api/actor/"):
                        payload = service.actor(unquote(parsed.path.removeprefix("/api/actor/")), timeline)
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
            except Exception as exc:
                self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/worlds":
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 64_000:
                    raise ValueError("request body must be between 1 and 64000 bytes")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                config = WorldConfig.model_validate(payload)
                descriptor = catalog.create(config)
                self._send(
                    HTTPStatus.CREATED,
                    {"world": _public_descriptor(descriptor), "inspect_url": f"/world/{descriptor.world_id}"},
                )
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def _selected_database(self) -> Path:
            world_id = _cookie_world(self.headers)
            if world_id:
                return Path(catalog.get(world_id).database_path)
            default = catalog.default_world()
            if default is None:
                raise KeyError("no world exists yet")
            return Path(default.database_path)

        def _send(
            self,
            status: HTTPStatus,
            payload: Any,
            content_type: str = "application/json; charset=utf-8",
            *,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def serve_world_console(database_path: str | Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    if not 0 < port < 65536:
        raise ValueError("port must be between 1 and 65535")
    server = ThreadingHTTPServer((host, port), make_console_handler(database_path))
    try:
        server.serve_forever()
    finally:
        server.server_close()
