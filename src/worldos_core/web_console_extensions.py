from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .web_console import _control_lock, make_console_handler as make_base_console_handler
from .world_creator import WorldCatalog


def _enhance_creator_html(html: str) -> str:
    html = html.replace(
        ".btn.primary{background:#e6f6ff;color:#071b2d;border-color:#d4efff;font-weight:760}.btn:hover{filter:brightness(1.08)}",
        ".btn.primary{background:#e6f6ff;color:#071b2d;border-color:#d4efff;font-weight:760}"
        ".btn.danger{border-color:#7f3440;color:#fecdd3;background:#31151b}"
        ".world-actions{display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap}"
        ".btn:hover{filter:brightness(1.08)}",
    )
    html = html.replace(
        '<div><button class="btn" onclick="location.href=\'/world/${encodeURIComponent(w.world_id)}\'">进入世界</button></div>',
        '<div class="world-actions">'
        '<button class="btn" onclick="location.href=\'/world/${encodeURIComponent(w.world_id)}\'">进入世界</button>'
        '${w.legacy?\'\':`<button class="btn danger" onclick="deleteWorld(\'${encodeURIComponent(w.world_id)}\',\'${esc(w.name)}\')">删除世界</button>`}'
        '</div>',
    )
    html = html.replace(
        "loadWorlds();",
        """async function deleteWorld(encodedId,name){
  const worldId=decodeURIComponent(encodedId);
  if(!confirm(`确定删除世界「${name}」吗？\n\n这个操作会删除该世界的开发数据文件，无法撤销。`)) return;
  try{
    await api('/api/worlds/'+encodeURIComponent(worldId),{method:'DELETE'});
    await loadWorlds();
  }catch(e){
    alert('删除失败：'+e.message);
  }
}

loadWorlds();""",
        1,
    )
    return html


def _enhance_inspector_html(html: str) -> str:
    html = html.replace(
        "return {food:'食物',wood:'木材',cloth:'布料',tools:'工具'}[id]||id",
        "return {food:'食物',wood:'木材',cloth:'布料',tools:'工具',grain:'粮食',credits:'积分',"
        "services:'服务',goods:'商品',knowledge:'知识',water:'水',oxygen:'氧气',energy:'能源',"
        "parts:'零件',data:'数据'}[id]||id",
    )
    html = html.replace(
        "</style>",
        ".actor-id,.profile-id{display:none}</style>",
        1,
    )
    html = html.replace(
        "function valueOrDash(v){return v===undefined||v===null?'—':v}",
        "function actorLabel(id){if(!id)return '';const a=(overviewData?.actors||[]).find(x=>x.actor_id===id);return a?.name||id}\n"
        "function valueOrDash(v){return v===undefined||v===null?'—':v}",
    )
    html = html.replace(
        "${esc(id)}</button>",
        "${esc(actorLabel(id))}</button>",
    )
    html = html.replace(
        "<strong>${esc(actor)}</strong> → ${esc(target)}",
        "<strong>${esc(actorLabel(actor))}</strong> → ${esc(actorLabel(target))}",
    )
    html = html.replace(
        "${e.actor_id||e.subject_ids?.[0]||''} → ${placeLabel(p.to_location_id)}",
        "${actorLabel(e.actor_id||e.subject_ids?.[0]||'')} → ${placeLabel(p.to_location_id)}",
    )
    html = html.replace(
        "${e.subject_ids?.[0]||''} ${p.delta>0?'+':''}${p.delta??''}",
        "${actorLabel(e.subject_ids?.[0]||'')} ${p.delta>0?'+':''}${p.delta??''}",
    )
    html = html.replace(
        "${e.actor_id||''} ${resourceLabel(p.resource||'')} +${p.quantity??''}",
        "${actorLabel(e.actor_id||'')} ${resourceLabel(p.resource||'')} +${p.quantity??''}",
    )
    html = html.replace(
        "${p.seller_id||e.actor_id||''} ↔ ${p.buyer_id||''} ${resourceLabel(p.resource||'')}",
        "${actorLabel(p.seller_id||e.actor_id||'')} ↔ ${actorLabel(p.buyer_id||'')} ${resourceLabel(p.resource||'')}",
    )
    html = html.replace(
        "${e.actor_id||''} → ${p.listener_id||p.target_id||''}",
        "${actorLabel(e.actor_id||'')} → ${actorLabel(p.listener_id||p.target_id||'')}",
    )
    html = html.replace(
        "${e.actor_id||p.owner_id||''} · ${p.goal_type||''}",
        "${actorLabel(e.actor_id||p.owner_id||'')} · ${p.goal_type||''}",
    )
    html = html.replace(
        "${p.observer_id||e.actor_id||''} · ${p.fact_type||''}",
        "${actorLabel(p.observer_id||e.actor_id||'')} · ${p.fact_type||''}",
    )
    html = html.replace(
        "return e.actor_id||e.subject_ids?.join(', ')||''",
        "return actorLabel(e.actor_id)||(e.subject_ids||[]).map(actorLabel).join(', ')||''",
    )
    html = html.replace(
        "const ordered=[...events].reverse();",
        "const visibleEvents=events.filter(e=>!(e.tick===0&&['entity.created','world.flag_set'].includes(e.event_type)));"
        "const ordered=[...visibleEvents].reverse();",
    )
    html = html.replace(
        "const events=n.events||[];",
        "const events=(n.events||[]).filter(e=>!(e.tick===0&&['entity.created','world.flag_set'].includes(e.event_type)));",
    )
    html = html.replace(
        "esc(n.perspective_actor_id)",
        "esc(actorLabel(n.perspective_actor_id))",
    )
    html = html.replace(
        "data.changed_entities.map(esc).join(', ')",
        "data.changed_entities.map(id=>esc(actorLabel(id))).join(', ')",
    )
    html = html.replace("Tick ${e.tick}", "第 ${e.tick} 回合")
    html = html.replace("Tick ${m.tick}", "第 ${m.tick} 回合")
    html = html.replace("Tick ${o.tick}", "第 ${o.tick} 回合")
    return html


def make_console_handler(database_path: str | Path) -> type[BaseHTTPRequestHandler]:
    legacy_database = Path(database_path)
    catalog = WorldCatalog(legacy_database.parent, legacy_db_path=legacy_database)
    BaseHandler = make_base_console_handler(database_path)

    class Handler(BaseHandler):
        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/api/worlds/"):
                self._send(HTTPStatus.NOT_FOUND, {"error": "未找到接口"})
                return

            world_id = unquote(parsed.path.removeprefix("/api/worlds/")).strip("/")
            if not world_id:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "缺少世界标识"})
                return

            try:
                descriptor = catalog.get(world_id)
                if descriptor.legacy:
                    self._send(HTTPStatus.FORBIDDEN, {"error": "开发样板世界不能从页面删除"})
                    return

                lock = _control_lock(descriptor.database_path)
                if not lock.acquire(blocking=False):
                    self._send(HTTPStatus.CONFLICT, {"error": "这个世界正在运行，不能删除"})
                    return
                try:
                    deleted = catalog.delete(world_id)
                finally:
                    lock.release()

                self._send(
                    HTTPStatus.OK,
                    {"deleted": True, "world_id": deleted.world_id, "name": deleted.name},
                    extra_headers={
                        "Set-Cookie": "worldos_world=; Path=/; Max-Age=0; SameSite=Lax"
                    },
                )
            except KeyError:
                self._send(HTTPStatus.NOT_FOUND, {"error": "未找到这个世界"})
            except ValueError as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def _send(
            self,
            status: HTTPStatus,
            payload: Any,
            content_type: str = "application/json; charset=utf-8",
            *,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            if isinstance(payload, str) and content_type.startswith("text/html"):
                if "<h2>我的世界</h2>" in payload:
                    payload = _enhance_creator_html(payload)
                elif "WorldOS 世界观察台" in payload:
                    payload = _enhance_inspector_html(payload)
            super()._send(
                status,
                payload,
                content_type,
                extra_headers=extra_headers,
            )

    return Handler


def serve_world_console(
    database_path: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    if not 0 < port < 65536:
        raise ValueError("端口必须在 1 到 65535 之间")
    server = ThreadingHTTPServer((host, port), make_console_handler(database_path))
    try:
        server.serve_forever()
    finally:
        server.server_close()
