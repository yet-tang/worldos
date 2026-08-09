from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .web_console_extensions import make_console_handler as make_extended_console_handler
from .web_console_humanized import _humanize_resident_html
from .web_console_summary import _summarize_html


_STORY_HELPERS = r"""
const STORY_SOCIAL_FACTS=new Set(['social.interacted','social.rumor_shared','social.helped','social.requested','social.request_resolved','social.confronted','social.repaid','obligation.created','obligation.fulfilled','obligation.defaulted']);
const STORY_INTERNAL_FACTS=new Set(['motivation.considered','motivation.selected']);
function storyTraitLabel(key){
  if(lang!=='zh') return key;
  return {sociability:'合群',generosity:'慷慨',assertiveness:'强势',risk_tolerance:'冒险',security:'安全感',belonging:'归属感',status:'地位欲',wealth:'财富欲',curiosity:'好奇心'}[key]||key;
}
function storyMotivationLabel(key){
  if(lang!=='zh') return key||'';
  return {security:'安全',care:'关怀',belonging:'归属',status:'地位',wealth:'财富',curiosity:'好奇',reciprocity:'人情'}[key]||key||'';
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
function storyBondLabel(b){
  if((b.grievance??0)>=24||(b.affinity??0)<=-35) return lang==='zh'?'仇敌':'Enemy';
  if((b.grievance??0)>=8||(b.affinity??0)<=-12) return lang==='zh'?'对手':'Rival';
  if((b.trust??0)>=28&&(b.affinity??0)>=16) return lang==='zh'?'盟友':'Ally';
  if((b.affinity??0)>=20&&(b.trust??0)>=10) return lang==='zh'?'朋友':'Friend';
  if((b.interactions??0)>=2) return lang==='zh'?'熟人':'Acquaintance';
  return lang==='zh'?'陌生人':'Stranger';
}
function storyObligationStatus(status){
  if(lang!=='zh') return status||'';
  return {open:'待兑现',fulfilled:'已兑现',defaulted:'已失约'}[status]||status||'';
}
function storySocialStructureSection(a){
  const bonds=[...(a?.social_bonds||[])].filter(b=>(b.interactions??0)>0||(b.trust??0)!==0||(b.affinity??0)!==0||(b.grievance??0)!==0).slice(0,10);
  const owed=[...(a?.obligations_as_debtor||[])].slice(0,8);
  const receivable=[...(a?.obligations_as_creditor||[])].slice(0,8);
  if(!bonds.length&&!owed.length&&!receivable.length) return '';
  const bondRows=bonds.map(b=>`<div class="item"><div class="knowledge-meta"><strong>${esc(actorLabel(b.other_id)||b.other_id)}</strong><span class="tag">${esc(storyBondLabel(b))}</span></div><span class="hint">${lang==='zh'?'亲近':'Affinity'} ${valueOrDash(b.affinity)} · ${lang==='zh'?'信任':'Trust'} ${valueOrDash(b.trust)} · ${lang==='zh'?'怨气':'Grievance'} ${valueOrDash(b.grievance)}</span></div>`).join('');
  const debtRows=owed.map(o=>`<div class="item"><div class="knowledge-meta"><strong>${lang==='zh'?'欠':'Owe'} ${esc(actorLabel(o.creditor_id)||o.creditor_id)}</strong><span class="tag">${esc(storyObligationStatus(o.status))}</span></div><span class="hint">${valueOrDash(o.quantity)} ${esc(resourceLabel(o.resource||'food'))} · ${lang==='zh'?'期限第':'due tick'} ${valueOrDash(o.due_tick)} ${lang==='zh'?'回合':''}</span></div>`).join('');
  const creditRows=receivable.map(o=>`<div class="item"><div class="knowledge-meta"><strong>${esc(actorLabel(o.debtor_id)||o.debtor_id)} ${lang==='zh'?'欠我':'owes me'}</strong><span class="tag">${esc(storyObligationStatus(o.status))}</span></div><span class="hint">${valueOrDash(o.quantity)} ${esc(resourceLabel(o.resource||'food'))} · ${lang==='zh'?'期限第':'due tick'} ${valueOrDash(o.due_tick)} ${lang==='zh'?'回合':''}</span></div>`).join('');
  let html=`<div class="section-title">${lang==='zh'?'社会关系与人情':'Social bonds & obligations'}</div>`;
  if(bondRows) html+=`<div class="item-list">${bondRows}</div>`;
  if(debtRows) html+=`<div class="section-title">${lang==='zh'?'我欠的人情':'What I owe'}</div><div class="item-list">${debtRows}</div>`;
  if(creditRows) html+=`<div class="section-title">${lang==='zh'?'别人欠我的':'What others owe me'}</div><div class="item-list">${creditRows}</div>`;
  return html;
}
function storyGoals(items){
  const goals=[...(items||[])];
  goals.sort((a,b)=>((a.status==='active'?0:1)-(b.status==='active'?0:1))||((b.created_tick??0)-(a.created_tick??0))||((b.priority??0)-(a.priority??0)));
  return goals.slice(0,12);
}
const _storyBaseGoalLabel=uiGoalLabel;
uiGoalLabel=function(type){
  const labels={request_resource:'寻求帮助',help_resident:'帮助他人',strengthen_relationship:'经营关系',confront_rival:'面对矛盾',explore_location:'探索地点',repay_obligation:'兑现人情'};
  if(lang==='zh'&&labels[type]) return labels[type];
  return _storyBaseGoalLabel(type);
};
const _storyBaseActionLabel=uiActionLabel;
uiActionLabel=function(type){
  const labels={request_resource:'向人求助',help_resident:'主动帮助',socialize:'交谈相处',confront:'正面交涉',repay_obligation:'归还人情'};
  if(lang==='zh'&&labels[type]) return labels[type];
  return _storyBaseActionLabel(type);
};
const _storyBaseFactType=uiFactType;
uiFactType=function(type){
  const labels={'social.interacted':'交往','social.rumor_shared':'交换消息','social.helped':'主动帮助','social.requested':'提出请求','social.request_resolved':'请求结果','social.confronted':'发生争执','social.repaid':'兑现人情','obligation.created':'形成承诺','obligation.fulfilled':'履约','obligation.defaulted':'失约'};
  if(lang==='zh'&&labels[type]) return labels[type];
  return _storyBaseFactType(type);
};
const _storyBaseFactSentence=uiFactSentence;
uiFactSentence=function(value,fallbackType){
  const f=uiFactEnvelope(value,fallbackType);const p=f.payload||{};
  const actor=actorLabel(f.actorId||f.subjects?.[0]||'')||'某人';
  const target=actorLabel(p.target_id||p.creditor_id||f.subjects?.[1]||'')||'另一名居民';
  if(f.type==='social.interacted') return lang==='zh'?`${actor}和${target}聊了一会儿，关系更近了一些`:`${actor} spent time with ${target}`;
  if(f.type==='social.rumor_shared') return lang==='zh'?`${actor}把“${p.rumor||'一条消息'}”告诉了${target}`:`${actor} shared a rumor with ${target}`;
  if(f.type==='social.helped') return lang==='zh'?`${actor}给了${target} ${p.quantity??1} 份${resourceLabel(p.resource||'food')}`:`${actor} helped ${target}`;
  if(f.type==='social.requested') return lang==='zh'?`${actor}向${target}请求 ${p.quantity??1} 份${resourceLabel(p.resource||'food')}`:`${actor} asked ${target} for ${p.resource||'a resource'}`;
  if(f.type==='social.request_resolved') return lang==='zh'?`${target}${p.outcome==='accepted'?'答应':'拒绝'}了${actor}的请求`:`${target} ${p.outcome==='accepted'?'accepted':'rejected'} ${actor}'s request`;
  if(f.type==='social.confronted') return lang==='zh'?`${actor}和${target}发生了一次正面争执`:`${actor} confronted ${target}`;
  if(f.type==='social.repaid') return lang==='zh'?`${actor}主动找到${target}，归还了 ${p.quantity??1} 份${resourceLabel(p.resource||'food')}`:`${actor} repaid ${target}`;
  if(f.type==='obligation.created') return lang==='zh'?`${actor}欠下了${target}一笔需要以后兑现的人情`:`${actor} now owes ${target}`;
  if(f.type==='obligation.fulfilled') return lang==='zh'?`${actor}兑现了对${target}的承诺`:`${actor} fulfilled an obligation to ${target}`;
  if(f.type==='obligation.defaulted') return lang==='zh'?`${actor}没有按期兑现对${target}的承诺，信任受到影响`:`${actor} defaulted on an obligation to ${target}`;
  return _storyBaseFactSentence(value,fallbackType);
};
const _storyBaseEventLabel=eventLabel;
eventLabel=function(type){
  const labels={'social.interacted':'交往','social.rumor_shared':'交换消息','social.helped':'主动帮助','social.requested':'提出请求','social.request_resolved':'请求结果','social.confronted':'发生争执','social.repaid':'兑现人情','obligation.created':'形成承诺','obligation.fulfilled':'履约','obligation.defaulted':'失约'};
  if(lang==='zh'&&labels[type]) return labels[type];
  return _storyBaseEventLabel(type);
};
const _storyBaseEventSummary=eventSummary;
eventSummary=function(e){
  const p=e.payload||{};const actor=actorLabel(e.actor_id||e.subject_ids?.[0]||'')||'';const target=actorLabel(p.target_id||p.creditor_id||e.subject_ids?.[1]||'')||'';
  if(e.event_type==='social.interacted') return `${actor} ↔ ${target}`;
  if(e.event_type==='social.rumor_shared') return `${actor} → ${target} · ${p.rumor||''}`;
  if(e.event_type==='social.helped') return `${actor} → ${target} · ${resourceLabel(p.resource||'food')} +${p.quantity??1}`;
  if(e.event_type==='social.requested') return `${actor} → ${target} · 请求${resourceLabel(p.resource||'food')}`;
  if(e.event_type==='social.request_resolved') return `${target} · ${p.outcome==='accepted'?'答应':'拒绝'}${actor}`;
  if(e.event_type==='social.confronted') return `${actor} ↔ ${target} · 争执`;
  if(e.event_type==='social.repaid') return `${actor} → ${target} · 归还${resourceLabel(p.resource||'food')} ${p.quantity??1}`;
  if(e.event_type==='obligation.created') return `${actor} → ${target} · 人情/债务`;
  if(e.event_type==='obligation.fulfilled') return `${actor} → ${target} · 已兑现`;
  if(e.event_type==='obligation.defaulted') return `${actor} → ${target} · 已失约`;
  return _storyBaseEventSummary(e);
};
const _storyBaseCompactMemories=uiCompactMemories;
uiCompactMemories=function(items){
  const all=uiMemories(items);
  const social=all.filter(m=>STORY_SOCIAL_FACTS.has(uiFactTypeOf(m.content,m.content?.fact_type))).slice(0,6);
  const rest=_storyBaseCompactMemories(items).filter(m=>!STORY_SOCIAL_FACTS.has(uiFactTypeOf(m.content,m.content?.fact_type)));
  return [...social,...rest].slice(0,10);
};
const _storyBaseObservationDigest=uiObservationDigest;
uiObservationDigest=function(items){
  const observations=uiObservations(items).slice().sort((a,b)=>(b.tick??0)-(a.tick??0));
  const social=observations.filter(o=>STORY_SOCIAL_FACTS.has(uiFactTypeOf(o.data,o.fact_type))).slice(0,6).map(o=>({label:uiFactType(uiFactTypeOf(o.data,o.fact_type)),tick:String(o.tick??''),text:uiFactSentence(o.data,o.fact_type)}));
  const base=_storyBaseObservationDigest(items);
  const keys=new Set(social.map(x=>`${x.label}|${x.tick}|${x.text}`));
  return [...social,...base.filter(x=>!keys.has(`${x.label}|${x.tick}|${x.text}`))].slice(0,10);
};
const _storyBaseNarrativeDigest=uiNarrativeDigest;
uiNarrativeDigest=function(events){return _storyBaseNarrativeDigest((events||[]).filter(e=>!STORY_INTERNAL_FACTS.has(e.event_type)))};
const _storyBaseRenderEvents=renderEvents;
renderEvents=function(events){
  const raw=events||[];
  _storyBaseRenderEvents(raw.filter(e=>!STORY_INTERNAL_FACTS.has(e.event_type)));
  eventsData=raw;
  $('eventsRaw').textContent=fmt(raw);
};
"""


_GOAL_OLD = "html+=listSection(t('goals'),a.goals,g=>`<div class=\"item\"><div class=\"knowledge-meta\"><span class=\"tag\">${esc(uiStatusLabel(g.status))}</span><strong>${esc(uiGoalLabel(g.goal_type))}</strong></div><span class=\"hint\">${lang==='zh'?'优先级':'Priority'} ${valueOrDash(g.priority)}</span></div>`);"
_GOAL_NEW = "html+=storyProfileSection(a);html+=storySocialStructureSection(a);html+=listSection(t('goals'),storyGoals(a.goals),g=>`<div class=\"item\"><div class=\"knowledge-meta\"><span class=\"tag\">${esc(uiStatusLabel(g.status))}</span><strong>${esc(uiGoalLabel(g.goal_type))}</strong>${g.parameters?.source_motivation?`<span class=\"tag\">${esc(storyMotivationLabel(g.parameters.source_motivation))}</span>`:''}</div><span class=\"hint\">${lang==='zh'?'优先级':'Priority'} ${valueOrDash(g.priority)}${g.parameters?.reason?` · ${esc(g.parameters.reason)}`:''}</span></div>`);"


def _story_html(html: str) -> str:
    if "WorldOS 世界观察台" not in html:
        return html
    html = html.replace("function renderActor(a){", _STORY_HELPERS + "\nfunction renderActor(a){", 1)
    html = html.replace(_GOAL_OLD, _GOAL_NEW, 1)
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
                payload = _story_html(_summarize_html(_humanize_resident_html(payload)))
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
