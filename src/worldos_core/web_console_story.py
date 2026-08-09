from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .web_console_summary import make_console_handler as make_summary_console_handler


_STORY_HELPERS = r"""
function storyTraitLabel(key){
  if(lang!=='zh') return key;
  return {sociability:'合群',generosity:'慷慨',assertiveness:'强势',risk_tolerance:'冒险',security:'安全感',belonging:'归属感',status:'地位欲',wealth:'财富欲',curiosity:'好奇心'}[key]||key;
}
function storyMotivationLabel(key){
  if(lang!=='zh') return key||'';
  return {security:'安全',care:'关怀',belonging:'归属',status:'地位',wealth:'财富',curiosity:'好奇'}[key]||key||'';
}
function storyProfileSection(a){
  const c=a?.entity?.components||{};
  const personality=c.personality||{};
  const drives=c.drives||{};
  const traits=Object.entries(personality).map(([k,v])=>`<span class="tag">${esc(storyTraitLabel(k))} ${esc(v)}</span>`).join('');
  const wants=Object.entries(drives).map(([k,v])=>`<span class="tag">${esc(storyTraitLabel(k))} ${esc(v)}</span>`).join('');
  if(!traits&&!wants) return `<div class="section-title">${lang==='zh'?'性格与长期欲望':'Character & drives'}</div><div class="item">${lang==='zh'?'首次运行后，人物会形成稳定的性格与长期欲望。':'Stable personality and drives will materialize after the first turn.'}</div>`;
  return `<div class="section-title">${lang==='zh'?'性格与长期欲望':'Character & drives'}</div><div class="item"><div class="knowledge-meta"><strong>${lang==='zh'?'性格':'Personality'}</strong></div><div class="chips">${traits||'—'}</div><div class="knowledge-meta" style="margin-top:10px"><strong>${lang==='zh'?'长期欲望':'Long-term drives'}</strong></div><div class="chips">${wants||'—'}</div></div>`;
}
function storyGoals(items){
  const goals=[...(items||[])];
  goals.sort((a,b)=>((a.status==='active'?0:1)-(b.status==='active'?0:1))||((b.created_tick??0)-(a.created_tick??0))||((b.priority??0)-(a.priority??0)));
  return goals.slice(0,12);
}
const _storyBaseGoalLabel=uiGoalLabel;
uiGoalLabel=function(type){
  const labels={request_resource:'寻求帮助',help_resident:'帮助他人',strengthen_relationship:'经营关系',confront_rival:'面对矛盾'};
  if(lang==='zh'&&labels[type]) return labels[type];
  return _storyBaseGoalLabel(type);
};
const _storyBaseActionLabel=uiActionLabel;
uiActionLabel=function(type){
  const labels={request_resource:'向人求助',help_resident:'主动帮助',socialize:'交谈相处',confront:'正面交涉'};
  if(lang==='zh'&&labels[type]) return labels[type];
  return _storyBaseActionLabel(type);
};
const _storyBaseFactType=uiFactType;
uiFactType=function(type){
  const labels={'social.interacted':'交往','social.rumor_shared':'交换消息','social.helped':'主动帮助','social.requested':'提出请求','social.request_resolved':'请求结果','social.confronted':'发生争执'};
  if(lang==='zh'&&labels[type]) return labels[type];
  return _storyBaseFactType(type);
};
const _storyBaseFactSentence=uiFactSentence;
uiFactSentence=function(value,fallbackType){
  const f=uiFactEnvelope(value,fallbackType);const p=f.payload||{};
  const actor=actorLabel(f.actorId||f.subjects?.[0]||'')||'某人';
  const target=actorLabel(p.target_id||f.subjects?.[1]||'')||'另一名居民';
  if(f.type==='social.interacted') return lang==='zh'?`${actor}和${target}聊了一会儿，关系更近了一些`:`${actor} spent time with ${target}`;
  if(f.type==='social.rumor_shared') return lang==='zh'?`${actor}把“${p.rumor||'一条消息'}”告诉了${target}`:`${actor} shared a rumor with ${target}`;
  if(f.type==='social.helped') return lang==='zh'?`${actor}给了${target} ${p.quantity??1} 份${resourceLabel(p.resource||'food')}`:`${actor} helped ${target}`;
  if(f.type==='social.requested') return lang==='zh'?`${actor}向${target}请求 ${p.quantity??1} 份${resourceLabel(p.resource||'food')}`:`${actor} asked ${target} for ${p.resource||'a resource'}`;
  if(f.type==='social.request_resolved') return lang==='zh'?`${target}${p.outcome==='accepted'?'答应':'拒绝'}了${actor}的请求`:`${target} ${p.outcome==='accepted'?'accepted':'rejected'} ${actor}'s request`;
  if(f.type==='social.confronted') return lang==='zh'?`${actor}和${target}发生了一次正面争执`:`${actor} confronted ${target}`;
  return _storyBaseFactSentence(value,fallbackType);
};
const _storyBaseEventLabel=eventLabel;
eventLabel=function(type){
  const labels={'social.interacted':'交往','social.rumor_shared':'交换消息','social.helped':'主动帮助','social.requested':'提出请求','social.request_resolved':'请求结果','social.confronted':'发生争执'};
  if(lang==='zh'&&labels[type]) return labels[type];
  return _storyBaseEventLabel(type);
};
const _storyBaseEventSummary=eventSummary;
eventSummary=function(e){
  const p=e.payload||{};const actor=actorLabel(e.actor_id||e.subject_ids?.[0]||'')||'';const target=actorLabel(p.target_id||e.subject_ids?.[1]||'')||'';
  if(e.event_type==='social.interacted') return `${actor} ↔ ${target}`;
  if(e.event_type==='social.rumor_shared') return `${actor} → ${target} · ${p.rumor||''}`;
  if(e.event_type==='social.helped') return `${actor} → ${target} · ${resourceLabel(p.resource||'food')} +${p.quantity??1}`;
  if(e.event_type==='social.requested') return `${actor} → ${target} · 请求${resourceLabel(p.resource||'food')}`;
  if(e.event_type==='social.request_resolved') return `${target} · ${p.outcome==='accepted'?'答应':'拒绝'}${actor}`;
  if(e.event_type==='social.confronted') return `${actor} ↔ ${target} · 争执`;
  return _storyBaseEventSummary(e);
};
"""


_GOAL_OLD = "html+=listSection(t('goals'),a.goals,g=>`<div class=\"item\"><div class=\"knowledge-meta\"><span class=\"tag\">${esc(uiStatusLabel(g.status))}</span><strong>${esc(uiGoalLabel(g.goal_type))}</strong></div><span class=\"hint\">${lang==='zh'?'优先级':'Priority'} ${valueOrDash(g.priority)}</span></div>`);"
_GOAL_NEW = "html+=storyProfileSection(a);html+=listSection(t('goals'),storyGoals(a.goals),g=>`<div class=\"item\"><div class=\"knowledge-meta\"><span class=\"tag\">${esc(uiStatusLabel(g.status))}</span><strong>${esc(uiGoalLabel(g.goal_type))}</strong>${g.parameters?.source_motivation?`<span class=\"tag\">${esc(storyMotivationLabel(g.parameters.source_motivation))}</span>`:''}</div><span class=\"hint\">${lang==='zh'?'优先级':'Priority'} ${valueOrDash(g.priority)}${g.parameters?.reason?` · ${esc(g.parameters.reason)}`:''}</span></div>`);"


def _story_html(html: str) -> str:
    if "WorldOS 世界观察台" not in html:
        return html
    html = html.replace("function renderActor(a){", _STORY_HELPERS + "\nfunction renderActor(a){", 1)
    html = html.replace(_GOAL_OLD, _GOAL_NEW, 1)
    return html


def make_console_handler(database_path: str | Path) -> type[BaseHTTPRequestHandler]:
    BaseHandler = make_summary_console_handler(database_path)
    base_send = BaseHandler._send

    class Handler(BaseHandler):
        def _send(
            self,
            status: HTTPStatus,
            payload: Any,
            content_type: str = "application/json; charset=utf-8",
            *,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            if isinstance(payload, str) and content_type.startswith("text/html"):
                payload = _story_html(payload)
            base_send(self, status, payload, content_type, extra_headers=extra_headers)

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
