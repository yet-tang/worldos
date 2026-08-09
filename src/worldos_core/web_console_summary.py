from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .web_console_extensions import make_console_handler as make_extended_console_handler
from .web_console_humanized import _humanize_resident_html


_SUMMARY_HELPERS = r"""
function uiSeverity(value, warn, critical){
  const n=Number(value??0);
  if(n>=critical) return 'critical';
  if(n>=warn) return 'warn';
  return 'ok';
}
function uiSituationCard(a){
  const c=a.entity?.components||{};
  const needs=c.needs||c.survival||{};
  const health=c.health||{};
  const hunger=Number(needs.hunger??0);
  const fatigue=Number(needs.fatigue??0);
  const hp=Number(health.current??100);
  const hpMax=Math.max(1,Number(health.maximum??100));
  const warnings=[];
  if(hunger>=90) warnings.push(lang==='zh'?'严重饥饿，需要立即进食':'Severely hungry; needs food now');
  else if(hunger>=70) warnings.push(lang==='zh'?'已经很饿，应该优先进食':'Hungry; eating should take priority');
  if(fatigue>=90) warnings.push(lang==='zh'?'极度疲劳，需要立即休息':'Exhausted; needs rest now');
  else if(fatigue>=75) warnings.push(lang==='zh'?'已经疲劳，应该优先休息':'Tired; resting should take priority');
  if(hp/hpMax<=.5) warnings.push(lang==='zh'?'健康状况危险':'Health is in danger');
  const state=warnings.length?(lang==='zh'?'需要自理':'Needs self-care'):(lang==='zh'?'状态稳定':'Stable');
  return `<div class="situation-card"><div class="situation-head"><strong>${lang==='zh'?'当前处境':'Current situation'}</strong><span class="situation-state ${warnings.length?'danger':'safe'}">${state}</span></div><div class="situation-grid"><div><span>${lang==='zh'?'健康':'Health'}</span><strong>${valueOrDash(hp)} / ${valueOrDash(hpMax)}</strong></div><div class="${uiSeverity(hunger,70,90)}"><span>${lang==='zh'?'饥饿':'Hunger'}</span><strong>${valueOrDash(hunger)}</strong></div><div class="${uiSeverity(fatigue,75,90)}"><span>${lang==='zh'?'疲劳':'Fatigue'}</span><strong>${valueOrDash(fatigue)}</strong></div></div>${warnings.length?`<div class="situation-warnings">${warnings.map(x=>`<div>• ${esc(x)}</div>`).join('')}</div>`:`<div class="situation-note">${lang==='zh'?'目前没有迫切的生存需求。':'No urgent survival need right now.'}</div>`}</div>`;
}
function uiCompactBeliefs(items){
  const rows=uiBeliefs(items).slice().sort((a,b)=>(b.updated_tick??b.tick??0)-(a.updated_tick??a.tick??0));
  const seen=new Set();const result=[];
  for(const item of rows){
    const f=uiFactEnvelope(item.data,item.fact_type);
    const key=`${f.type}|${(f.subjects||[]).join('|')}`;
    if(seen.has(key)) continue;
    seen.add(key);result.push(item);
    if(result.length>=8) break;
  }
  return result;
}
function uiCompactMemories(items){
  const rows=uiMemories(items);
  const important=new Set(['rumor.spread','trade.completed','conflict.resolved','entity.moved','eat.resolved','rest.resolved','entity.deactivated']);
  const preferred=rows.filter(m=>important.has(uiFactTypeOf(m.content,m.content?.fact_type)));
  const fallback=rows.filter(m=>!important.has(uiFactTypeOf(m.content,m.content?.fact_type)));
  return [...preferred,...fallback].slice(0,10);
}
function uiObservationDigest(items){
  const rows=uiObservations(items).slice().sort((a,b)=>(a.tick??0)-(b.tick??0));
  if(!rows.length) return [];
  const recent=rows.slice(-80);
  const production=new Map();
  let healthDelta=0,healthCount=0,minTick=null,maxTick=null;
  let latestBody=null,lastEat=null,lastRest=null;
  const important=[];
  for(const item of recent){
    const f=uiFactEnvelope(item.data,item.fact_type);const p=f.payload||{};
    minTick=minTick===null?item.tick:Math.min(minTick,item.tick??minTick);
    maxTick=maxTick===null?item.tick:Math.max(maxTick,item.tick??maxTick);
    if(f.type==='resource.produced'){
      const resource=p.resource||'resource';production.set(resource,(production.get(resource)||0)+Number(p.quantity||0));continue;
    }
    if(f.type==='health.changed'){
      healthDelta+=Number(p.delta||0);healthCount+=1;continue;
    }
    if(f.type==='survival.metabolized'){latestBody={item,f};continue;}
    if(f.type==='eat.resolved'){lastEat={item,f};important.push({item,f});continue;}
    if(f.type==='rest.resolved'){lastRest={item,f};important.push({item,f});continue;}
    if(['rumor.spread','trade.completed','conflict.resolved','entity.moved','entity.deactivated'].includes(f.type)) important.push({item,f});
  }
  const out=[];
  const span=minTick===null?'':(minTick===maxTick?`${minTick}`:`${minTick}–${maxTick}`);
  for(const [resource,qty] of production.entries()){
    out.push({label:lang==='zh'?'生产汇总':'Production',tick:span,text:lang==='zh'?`最近记录中共生产 ${qty} 份${resourceLabel(resource)}`:`Produced ${qty} ${resourceLabel(resource)} in recent records`});
  }
  if(healthCount){
    const direction=healthDelta>=0?(lang==='zh'?'增加':'increased'):(lang==='zh'?'减少':'decreased');
    out.push({label:lang==='zh'?'健康趋势':'Health trend',tick:span,text:lang==='zh'?`最近记录中健康累计${direction} ${Math.abs(healthDelta)}（${healthCount} 次变化）`:`Health ${direction} by ${Math.abs(healthDelta)} across ${healthCount} changes`});
  }
  if(latestBody){
    const p=latestBody.f.payload||{};
    out.push({label:lang==='zh'?'当前身体状态':'Body state',tick:String(latestBody.item.tick??''),text:lang==='zh'?`最近记录：饥饿 ${valueOrDash(p.hunger)}，疲劳 ${valueOrDash(p.fatigue)}`:`Latest: hunger ${valueOrDash(p.hunger)}, fatigue ${valueOrDash(p.fatigue)}`});
  }
  if(lastEat) out.push({label:lang==='zh'?'最近进食':'Last meal',tick:String(lastEat.item.tick??''),text:uiFactSentence(lastEat.item.data,lastEat.item.fact_type)});
  if(lastRest) out.push({label:lang==='zh'?'最近休息':'Last rest',tick:String(lastRest.item.tick??''),text:uiFactSentence(lastRest.item.data,lastRest.item.fact_type)});
  for(const entry of important.slice(-5).reverse()){
    if(entry===lastEat||entry===lastRest) continue;
    out.push({label:uiFactType(entry.f.type),tick:String(entry.item.tick??''),text:uiFactSentence(entry.item.data,entry.item.fact_type)});
  }
  return out.slice(0,10);
}
function uiObservationDigestSection(items){
  const rows=uiObservationDigest(items);
  const title=lang==='zh'?'最近动态摘要':'Recent activity summary';
  return `<div class="section-title">${title}</div><div class="item-list">${rows.length?rows.map(r=>`<div class="item"><div class="knowledge-meta"><strong>${esc(r.label)}</strong>${r.tick?`<span class="tag">${lang==='zh'?`第 ${esc(r.tick)} 回合`:`Tick ${esc(r.tick)}`}</span>`:''}</div><div class="knowledge-copy">${esc(r.text)}</div></div>`).join(''):`<div class="item">${t('none')}</div>`}</div>`;
}
function uiFactSentenceSummary(e){
  const p=e.payload||{};const who=actorLabel(e.actor_id||e.subject_ids?.[0]||'');
  if(e.event_type==='eat.resolved') return lang==='zh'?`${who||'该居民'}吃了 ${p.quantity??1} 份${resourceLabel(p.resource||'food')}，饥饿 ${p.hunger_before??'—'}→${p.hunger_after??'—'}`:`${who||'Resident'} ate; hunger ${p.hunger_before??'—'}→${p.hunger_after??'—'}`;
  if(e.event_type==='rest.resolved') return lang==='zh'?`${who||'该居民'}休息后，疲劳 ${p.fatigue_before??'—'}→${p.fatigue_after??'—'}`:`${who||'Resident'} rested; fatigue ${p.fatigue_before??'—'}→${p.fatigue_after??'—'}`;
  return eventSummary(e);
}
function uiNarrativeDigest(events){
  const recent=(events||[]).filter(e=>!(e.tick===0&&['entity.created','world.flag_set'].includes(e.event_type))).slice(-140);
  const production=new Map();let healthDelta=0;let healthCount=0;const notable=[];
  const ignored=new Set(['tick.started','tick.completed','entity.component_set','entity.component_removed','survival.metabolized','observation.created','belief.updated','memory.recorded','memory.forgotten','need.assessed','goal.created','goal.status_changed','plan.step_created','plan.step_status_changed','eat.attempted','rest.attempted']);
  for(const e of recent){
    if(e.event_type==='resource.produced'){const r=e.payload?.resource||'resource';production.set(r,(production.get(r)||0)+Number(e.payload?.quantity||0));continue;}
    if(e.event_type==='health.changed'){healthDelta+=Number(e.payload?.delta||0);healthCount+=1;continue;}
    if(ignored.has(e.event_type)) continue;
    notable.push(e);
  }
  const chips=[];
  for(const [r,q] of production.entries()) chips.push(`${lang==='zh'?'生产':'Produced'} ${q} ${resourceLabel(r)}`);
  if(healthCount) chips.push(`${lang==='zh'?'健康累计变化':'Health net'} ${healthDelta>=0?'+':''}${healthDelta}`);
  const summary=chips.length?`<div class="digest-strip">${chips.map(x=>`<span>${esc(x)}</span>`).join('')}</div>`:'';
  const items=notable.slice(-14).reverse().map(e=>`<div class="narrative-event"><span class="tag">${lang==='zh'?`第 ${e.tick} 回合`:`Tick ${e.tick}`}</span><strong>${esc(e.event_type==='eat.resolved'?(lang==='zh'?'进食':'Ate'):e.event_type==='rest.resolved'?(lang==='zh'?'休息':'Rested'):eventLabel(e.event_type))}</strong> · ${esc(uiFactSentenceSummary(e))}</div>`).join('');
  return summary+(items||`<div class="empty">${t('none')}</div>`);
}
"""


def _summarize_html(html: str) -> str:
    if "WorldOS 世界观察台" not in html:
        return html

    html = html.replace(
        "</style>",
        ".situation-card{margin:14px 0;padding:13px;border:1px solid #314762;border-radius:12px;background:#0b1728}"
        ".situation-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}"
        ".situation-state{font-size:11px;padding:3px 7px;border-radius:999px}.situation-state.safe{background:#123324;color:#a7f3d0}.situation-state.danger{background:#3b1d22;color:#fecaca}"
        ".situation-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.situation-grid>div{border:1px solid #25364e;border-radius:9px;padding:8px}.situation-grid span{display:block;color:#91a1bb;font-size:11px}.situation-grid strong{display:block;margin-top:3px}.situation-grid .warn strong{color:#fde68a}.situation-grid .critical strong{color:#fca5a5}"
        ".situation-warnings,.situation-note{margin-top:9px;font-size:12px;line-height:1.65}.situation-warnings{color:#fecaca}.situation-note{color:#91a1bb}"
        ".digest-strip{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:9px}.digest-strip span{font-size:11px;padding:5px 8px;border-radius:999px;background:#14243a;border:1px solid #2d4666;color:#cfe7ff}"
        "</style>",
        1,
    )
    html = html.replace(
        "function renderActor(a){",
        _SUMMARY_HELPERS + "\nfunction renderActor(a){",
        1,
    )
    html = html.replace(
        "<div class=\"section-title\">${t('inventory')}</div><div class=\"item\">${esc(invText)}</div>`;",
        "<div class=\"section-title\">${t('inventory')}</div><div class=\"item\">${esc(invText)}</div>${uiSituationCard(a)}`;",
        1,
    )
    html = html.replace("uiBeliefs(a.beliefs)", "uiCompactBeliefs(a.beliefs)", 1)
    html = html.replace("uiMemories(a.memories)", "uiCompactMemories(a.memories)", 1)

    observation_marker = (
        "html+=listSection(t('observations'),uiObservations(a.observations),o=>`<div class=\"item\"><div class=\"knowledge-meta\"><strong>${esc(uiFactType(uiFactTypeOf(o.data,o.fact_type)))}</strong><span class=\"tag\">${lang==='zh'?`第 ${o.tick} 回合`:`Tick ${o.tick}`}</span></div><div class=\"knowledge-copy\">${esc(uiFactSentence(o.data,o.fact_type))}</div></div>`);"
    )
    html = html.replace(observation_marker, "html+=uiObservationDigestSection(a.observations);", 1)

    old_narrative = "function renderNarrative(n){narratorData=n;$('narratorRaw').textContent=fmt(n);const mode=n.mode==='actor'?t('perspective'):t('omniscient');const events=n.events||[];$('narrativeBox').innerHTML=`<div class=\"hint\" style=\"margin-bottom:8px\">${mode}${n.perspective_actor_id?' · '+esc(n.perspective_actor_id):''}</div>`+(events.length?events.slice(-40).reverse().map(e=>`<div class=\"narrative-event\"><span class=\"tag\">Tick ${e.tick}</span><strong>${esc(eventLabel(e.event_type))}</strong> · ${esc(eventSummary(e))}</div>`).join(''):`<div class=\"empty\">${t('none')}</div>`)}"
    new_narrative = "function renderNarrative(n){narratorData=n;$('narratorRaw').textContent=fmt(n);const mode=n.mode==='actor'?t('perspective'):t('omniscient');const events=n.events||[];$('narrativeBox').innerHTML=`<div class=\"hint\" style=\"margin-bottom:8px\">${mode}${n.perspective_actor_id?' · '+esc(actorLabel(n.perspective_actor_id)):''}</div>`+uiNarrativeDigest(events)}"
    html = html.replace(old_narrative, new_narrative, 1)
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
                payload = _summarize_html(_humanize_resident_html(payload))
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
