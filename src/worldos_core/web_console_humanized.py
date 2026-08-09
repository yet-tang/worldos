from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .web_console_extensions import make_console_handler as make_extended_console_handler


_RESIDENT_PRESENTATION_HELPERS = r"""
function uiStatusLabel(value){
  if(lang!=='zh') return value||'—';
  return {
    active:'进行中',pending:'待处理',completed:'已完成',complete:'已完成',done:'已完成',
    failed:'失败',cancelled:'已取消',canceled:'已取消',blocked:'受阻',planned:'已计划',
    in_progress:'进行中',open:'开放',closed:'结束'
  }[value]||value||'—';
}
function uiMemoryKind(kind){
  if(lang!=='zh') return kind||'Memory';
  return {working:'短期记忆',episodic:'经历记忆',semantic:'长期认知',identity:'身份记忆'}[kind]||'记忆';
}
function uiGoalLabel(type){
  if(lang!=='zh') return type||'Goal';
  return {
    survival:'维持生存',food_security:'保障食物',safety:'保证安全',rest:'恢复体力',
    produce:'生产资源',production:'生产资源',trade:'完成交易',wealth:'积累资源',
    socialize:'与人交往',relationship:'改善关系',explore:'探索世界'
  }[type]||type||'未命名目标';
}
function uiActionLabel(type){
  if(lang!=='zh') return type||'Action';
  return {
    move:'前往地点',move_to:'前往地点',travel:'前往地点',produce:'生产资源',work:'工作',
    trade:'进行交易',buy:'购买',sell:'出售',rest:'休息',eat:'进食',consume:'使用资源',
    spread_rumor:'传播消息',observe:'观察',wait:'等待'
  }[type]||type||'行动';
}
function uiFactType(type){
  if(lang!=='zh') return eventLabel(type);
  return {
    'rumor.spread':'听到传闻','resource.produced':'生产活动','survival.metabolized':'身体状态',
    'entity.moved':'移动','health.changed':'健康变化','trade.completed':'交易',
    'conflict.resolved':'冲突结果','goal.created':'形成目标','entity.deactivated':'停止活动',
    'entity.component_set':'内部状态同步','need.assessed':'内部需求评估'
  }[type]||eventLabel(type);
}
function uiFactEnvelope(value,fallbackType){
  let root=value&&typeof value==='object'?value:{};
  if(root.content&&typeof root.content==='object') root=root.content;
  const type=root.fact_type||root.event_type||fallbackType||'';
  const data=root.data&&typeof root.data==='object'?root.data:root;
  const eventType=data.event_type||type;
  const payload=data.payload&&typeof data.payload==='object'?data.payload:{};
  const subjects=Array.isArray(data.subject_ids)?data.subject_ids:(Array.isArray(root.subject_ids)?root.subject_ids:[]);
  const actorId=data.actor_id||root.actor_id||subjects[0]||'';
  return {type:eventType,payload,subjects,actorId,data,root};
}
function uiFactSentence(value,fallbackType){
  const f=uiFactEnvelope(value,fallbackType);
  const p=f.payload||{};
  const who=actorLabel(f.actorId||f.subjects?.[0]||'');
  const subjectNames=(f.subjects||[]).map(actorLabel).filter(Boolean);
  if(f.type==='rumor.spread'){
    const rumor=p.rumor||p.text||p.message||'';
    const source=actorLabel(p.source_id||f.actorId||f.subjects?.[0]||'')||who;
    const target=actorLabel(p.target_id||p.listener_id||f.subjects?.[1]||'');
    if(lang==='zh') return `${source||'某人'}${target?`告诉${target}`:'听到消息'}${rumor?`：“${rumor}”`:''}`;
    return `${source||'Someone'}${target?` told ${target}`:' heard a rumor'}${rumor?`: “${rumor}”`:''}`;
  }
  if(f.type==='resource.produced'){
    const qty=p.quantity??'';
    const resource=resourceLabel(p.resource||'');
    return lang==='zh'?`${who||'该居民'}生产了${qty!==''?` ${qty} 份`:''}${resource||'资源'}`:`${who||'Resident'} produced ${qty} ${resource}`.trim();
  }
  if(f.type==='survival.metabolized'){
    const parts=[];
    if(p.hunger!==undefined) parts.push(lang==='zh'?`饥饿 ${p.hunger}`:`hunger ${p.hunger}`);
    if(p.fatigue!==undefined) parts.push(lang==='zh'?`疲劳 ${p.fatigue}`:`fatigue ${p.fatigue}`);
    return lang==='zh'?`${who||'该居民'}的状态变为：${parts.join('，')||'发生变化'}`:`${who||'Resident'}: ${parts.join(', ')||'state changed'}`;
  }
  if(f.type==='entity.moved'){
    const to=placeLabel(p.to_location_id||p.location_id||'');
    return lang==='zh'?`${who||'该居民'}前往${to||'另一个地点'}`:`${who||'Resident'} moved to ${to}`;
  }
  if(f.type==='health.changed'){
    const delta=p.delta;
    if(lang==='zh') return `${who||'该居民'}的健康${delta===undefined?'发生变化':`${delta>=0?'增加':'减少'} ${Math.abs(delta)}`}`;
    return `${who||'Resident'} health ${delta===undefined?'changed':`${delta>=0?'+':''}${delta}`}`;
  }
  if(f.type==='trade.completed'){
    const seller=actorLabel(p.seller_id||f.actorId||'');
    const buyer=actorLabel(p.buyer_id||'');
    const resource=resourceLabel(p.resource||'资源');
    const qty=p.quantity??'';
    if(lang==='zh') return `${seller||'卖方'}与${buyer||'买方'}完成交易${qty!==''?`：${qty} 份${resource}`:''}`;
    return `${seller||'Seller'} traded with ${buyer||'buyer'}${qty!==''?`: ${qty} ${resource}`:''}`;
  }
  if(f.type==='conflict.resolved'){
    const names=subjectNames.length?subjectNames.join('、'):(who||'相关居民');
    return lang==='zh'?`${names}之间的一次冲突得到结算`:`A conflict involving ${names} was resolved`;
  }
  if(f.type==='entity.deactivated'){
    return lang==='zh'?`${who||'该居民'}停止活动`:`${who||'Resident'} became inactive`;
  }
  const label=uiFactType(f.type);
  if(subjectNames.length) return lang==='zh'?`${subjectNames.join('、')}：${label}`:`${subjectNames.join(', ')}: ${label}`;
  return label|| (lang==='zh'?'发生了一件事':'An event occurred');
}
const UI_TECHNICAL_FACTS=new Set([
  'entity.component_set','entity.component_removed','observation.created','belief.updated',
  'memory.recorded','memory.forgotten','tick.started','tick.completed','need.assessed'
]);
function uiFactTypeOf(value,fallbackType){return uiFactEnvelope(value,fallbackType).type||fallbackType||''}
function uiVisibleFact(type){return !UI_TECHNICAL_FACTS.has(type)}
function uiBeliefs(items){return (items||[]).filter(item=>uiVisibleFact(uiFactTypeOf(item.data,item.fact_type)))}
function uiObservations(items){return (items||[]).filter(item=>uiVisibleFact(uiFactTypeOf(item.data,item.fact_type)))}
function uiMemories(items){
  const seen=new Set();
  const ranked={identity:4,episodic:3,semantic:2,working:1};
  const sorted=[...(items||[])].sort((a,b)=>((b.tick??0)-(a.tick??0))||((ranked[b.kind]||0)-(ranked[a.kind]||0)));
  const result=[];
  for(const item of sorted){
    const type=uiFactTypeOf(item.content,item.content?.fact_type);
    if(!uiVisibleFact(type)) continue;
    const key=item.content?.belief_id||item.source_ids?.[0]||`${type}|${JSON.stringify(item.content?.data||item.content||{})}`;
    if(seen.has(key)) continue;
    seen.add(key);result.push(item);
  }
  return result.slice(0,24);
}
function uiActionDetail(args){
  if(!args||typeof args!=='object') return '';
  const parts=[];
  if(args.location_id||args.to_location_id) parts.push(placeLabel(args.location_id||args.to_location_id));
  if(args.resource) parts.push(resourceLabel(args.resource));
  if(args.quantity!==undefined) parts.push(lang==='zh'?`数量 ${args.quantity}`:`qty ${args.quantity}`);
  if(args.target_actor_id||args.target_id) parts.push(actorLabel(args.target_actor_id||args.target_id));
  return parts.join(' · ');
}
"""


def _humanize_resident_html(html: str) -> str:
    if "WorldOS 世界观察台" not in html:
        return html

    html = html.replace(
        "</style>",
        ".knowledge-copy{margin-top:6px;color:#d7e0ee;line-height:1.65}"
        ".knowledge-meta{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:5px}"
        ".knowledge-meta .tag{margin-right:0}"
        "</style>",
        1,
    )
    html = html.replace(
        "function renderActor(a){",
        _RESIDENT_PRESENTATION_HELPERS + "\nfunction renderActor(a){",
        1,
    )

    html = html.replace(
        "html+=listSection(t('goals'),a.goals,g=>`<div class=\"item\"><span class=\"tag\">${esc(g.status)}</span><strong>${esc(g.goal_type)}</strong><br><span class=\"hint\">priority ${g.priority} · ${esc(fmt(g.parameters||{}))}</span></div>`);",
        "html+=listSection(t('goals'),a.goals,g=>`<div class=\"item\"><div class=\"knowledge-meta\"><span class=\"tag\">${esc(uiStatusLabel(g.status))}</span><strong>${esc(uiGoalLabel(g.goal_type))}</strong></div><span class=\"hint\">${lang==='zh'?'优先级':'Priority'} ${valueOrDash(g.priority)}</span></div>`);",
        1,
    )
    html = html.replace(
        "html+=listSection(t('plans'),a.plan_steps,s=>`<div class=\"item\"><span class=\"tag\">${esc(s.status)}</span><strong>${esc(s.action_type)}</strong><br><span class=\"hint\">${esc(fmt(s.arguments||{}))}</span></div>`);",
        "html+=listSection(t('plans'),a.plan_steps,s=>{const detail=uiActionDetail(s.arguments||{});return `<div class=\"item\"><div class=\"knowledge-meta\"><span class=\"tag\">${esc(uiStatusLabel(s.status))}</span><strong>${esc(uiActionLabel(s.action_type))}</strong></div>${detail?`<span class=\"hint\">${esc(detail)}</span>`:''}</div>`});",
        1,
    )
    html = html.replace(
        "html+=listSection(t('beliefs'),a.beliefs,b=>`<div class=\"item\"><strong>${esc(b.fact_type)}</strong> · ${Math.round((b.confidence??0)*100)}%<br><span class=\"hint\">${esc(fmt(b.data||{}))}</span></div>`);",
        "html+=listSection(t('beliefs'),uiBeliefs(a.beliefs),b=>`<div class=\"item\"><div class=\"knowledge-meta\"><strong>${esc(uiFactType(uiFactTypeOf(b.data,b.fact_type)))}</strong><span class=\"tag\">${lang==='zh'?'可信度':'Confidence'} ${Math.round((b.confidence??0)*100)}%</span></div><div class=\"knowledge-copy\">${esc(uiFactSentence(b.data,b.fact_type))}</div></div>`);",
        1,
    )
    html = html.replace(
        "html+=listSection(t('memories'),a.memories,m=>`<div class=\"item\"><span class=\"tag\">${esc(m.kind)}</span><strong>Tick ${m.tick}</strong> · ${Math.round((m.confidence??0)*100)}%<br><span class=\"hint\">${esc(fmt(m.content||{}))}</span></div>`);",
        "html+=listSection(t('memories'),uiMemories(a.memories),m=>`<div class=\"item\"><div class=\"knowledge-meta\"><span class=\"tag\">${esc(uiMemoryKind(m.kind))}</span><strong>${lang==='zh'?`第 ${m.tick} 回合`:`Tick ${m.tick}`}</strong><span class=\"tag\">${lang==='zh'?'可信度':'Confidence'} ${Math.round((m.confidence??0)*100)}%</span></div><div class=\"knowledge-copy\">${esc(uiFactSentence(m.content,uiFactTypeOf(m.content,'')))}</div></div>`);",
        1,
    )
    html = html.replace(
        "html+=listSection(t('observations'),a.observations,o=>`<div class=\"item\"><strong>${esc(o.fact_type)}</strong> · Tick ${o.tick}<br><span class=\"hint\">${esc(fmt(o.data||{}))}</span></div>`);",
        "html+=listSection(t('observations'),uiObservations(a.observations),o=>`<div class=\"item\"><div class=\"knowledge-meta\"><strong>${esc(uiFactType(uiFactTypeOf(o.data,o.fact_type)))}</strong><span class=\"tag\">${lang==='zh'?`第 ${o.tick} 回合`:`Tick ${o.tick}`}</span></div><div class=\"knowledge-copy\">${esc(uiFactSentence(o.data,o.fact_type))}</div></div>`);",
        1,
    )
    return html


def make_console_handler(database_path: str | Path) -> type[BaseHTTPRequestHandler]:
    BaseHandler = make_extended_console_handler(database_path)
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
                payload = _humanize_resident_html(payload)
            base_send(
                self,
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
