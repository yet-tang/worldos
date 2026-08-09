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
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>WorldOS 世界观察台</title>
<style>
:root{
  font-family:Inter,"PingFang SC","Microsoft YaHei",ui-sans-serif,system-ui,sans-serif;
  color:#edf2ff;background:#080d19;
  --bg:#080d19;--panel:#101827;--panel2:#151f31;--line:#26344d;
  --text:#edf2ff;--muted:#91a1bb;--accent:#7dd3fc;--good:#86efac;
  --warn:#fde68a;--danger:#fca5a5;--shadow:0 18px 50px rgba(0,0,0,.24)
}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0,#12203a 0,transparent 32%),var(--bg);min-height:100vh}
button,input{font:inherit}button{cursor:pointer}.shell{max-width:1500px;margin:0 auto;padding:0 24px 48px}
header{position:sticky;top:0;z-index:10;background:rgba(8,13,25,.9);backdrop-filter:blur(16px);border-bottom:1px solid rgba(38,52,77,.75)}
.header-inner{max-width:1500px;margin:0 auto;padding:16px 24px;display:flex;align-items:center;gap:18px;justify-content:space-between}
.brand{display:flex;align-items:center;gap:12px}.brand-mark{width:36px;height:36px;border-radius:11px;display:grid;place-items:center;background:linear-gradient(145deg,#1d4ed8,#0891b2);font-weight:800;box-shadow:var(--shadow)}
.brand h1{font-size:18px;margin:0}.brand small{display:block;color:var(--muted);margin-top:2px}
.toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}.toolbar input{width:130px}
input,.ghost,.primary{border:1px solid var(--line);border-radius:9px;padding:8px 10px;background:#0c1422;color:var(--text)}
.primary{background:#e6f6ff;color:#082032;border-color:#d4efff;font-weight:700}.ghost:hover,.primary:hover{filter:brightness(1.08)}
.hero{padding:28px 0 14px;display:flex;align-items:flex-end;justify-content:space-between;gap:24px}.eyebrow{color:var(--accent);font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase}.hero h2{font-size:32px;margin:6px 0 4px;letter-spacing:-.02em}.hero p{margin:0;color:var(--muted);max-width:700px;line-height:1.7}
.status-pill{display:inline-flex;align-items:center;gap:7px;border:1px solid #25533d;background:#0e2a21;color:#a7f3d0;padding:7px 10px;border-radius:999px;font-size:13px}.dot{width:7px;height:7px;background:#4ade80;border-radius:50%;box-shadow:0 0 0 4px rgba(74,222,128,.1)}
.metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:16px 0 20px}.metric{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:15px;box-shadow:var(--shadow)}.metric-label{font-size:12px;color:var(--muted)}.metric-value{font-size:24px;font-weight:760;margin-top:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.metric-sub{font-size:11px;color:var(--muted);margin-top:4px}
.grid{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(380px,.8fr);gap:16px}.column{display:flex;flex-direction:column;gap:16px}.card{background:rgba(16,24,39,.92);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:var(--shadow)}.card-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.card h3{margin:0;font-size:16px}.hint{color:var(--muted);font-size:12px}
.map-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.place{border:1px solid var(--line);border-radius:13px;padding:14px;background:#0c1422}.place-name{font-weight:720}.place-count{color:var(--muted);font-size:12px;margin:3px 0 10px}.chips{display:flex;gap:6px;flex-wrap:wrap}.chip{font-size:12px;padding:5px 8px;border:1px solid #2c4365;background:#112039;border-radius:999px;color:#cfe7ff;cursor:pointer}.chip:hover{border-color:#5ea7dc}
.actor-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.actor-card{border:1px solid var(--line);border-radius:13px;padding:13px;background:#0c1422;cursor:pointer;transition:.15s ease}.actor-card:hover,.actor-card.active{transform:translateY(-1px);border-color:#4f87b8;background:#10203a}.actor-title{display:flex;justify-content:space-between;gap:8px;font-weight:720}.actor-id{font-size:11px;color:var(--muted);margin-top:2px}.actor-meta{display:flex;gap:10px;flex-wrap:wrap;color:#c9d7ec;font-size:12px;margin-top:9px}.inactive{color:var(--muted)}
.empty{border:1px dashed var(--line);border-radius:12px;padding:22px;text-align:center;color:var(--muted);line-height:1.6}.profile-title{font-size:21px;font-weight:780}.profile-id{font-size:11px;color:var(--muted);margin-top:3px}.stat-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:14px 0}.mini{background:#0c1422;border:1px solid var(--line);border-radius:10px;padding:10px}.mini span{display:block;color:var(--muted);font-size:11px}.mini strong{display:block;margin-top:4px;font-size:15px}.section-title{font-size:12px;color:var(--muted);margin:15px 0 7px}.item-list{display:flex;flex-direction:column;gap:7px}.item{background:#0c1422;border:1px solid var(--line);border-radius:10px;padding:10px 11px;font-size:13px;line-height:1.55}.item strong{color:#dff3ff}.tag{display:inline-block;padding:2px 6px;margin-right:5px;border-radius:6px;background:#172941;color:#bcdcff;font-size:11px}
.timeline{display:flex;flex-direction:column;gap:7px;max-height:520px;overflow:auto;padding-right:4px}.event{display:grid;grid-template-columns:62px 145px minmax(0,1fr);gap:9px;align-items:start;border-bottom:1px solid #1f2c42;padding:8px 2px;font-size:12px}.event .seq{color:var(--muted)}.event-type{color:#bde7ff}.event-main{color:#d7e0ee;word-break:break-word}
.narrative-box{background:#0c1422;border:1px solid var(--line);border-radius:12px;padding:13px;line-height:1.7;font-size:13px;max-height:420px;overflow:auto}.narrative-event{padding:7px 0;border-bottom:1px solid #1e2c41}.narrative-event:last-child{border:0}
details{margin-top:12px}summary{cursor:pointer;color:#9fb4d1;font-size:12px}pre{white-space:pre-wrap;word-break:break-word;background:#080e19;border:1px solid #1d2a40;border-radius:10px;padding:12px;color:#bcd0ea;max-height:420px;overflow:auto;font-size:11px;line-height:1.55}.compare-result{font-size:13px;line-height:1.7}.same{color:var(--good)}.different{color:var(--warn)}
.toast{position:fixed;right:20px;bottom:20px;background:#152238;border:1px solid #3a5578;border-radius:10px;padding:10px 13px;box-shadow:var(--shadow);display:none;font-size:13px}.loading{opacity:.55;pointer-events:none}
@media(max-width:1050px){.metrics{grid-template-columns:repeat(3,1fr)}.grid{grid-template-columns:1fr}.map-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:700px){.shell{padding:0 14px 30px}.header-inner{padding:12px 14px;align-items:flex-start;flex-direction:column}.toolbar{justify-content:flex-start}.hero{padding-top:20px;align-items:flex-start;flex-direction:column}.hero h2{font-size:26px}.metrics{grid-template-columns:repeat(2,1fr)}.map-grid,.actor-grid{grid-template-columns:1fr}.event{grid-template-columns:54px minmax(0,1fr)}.event-main{grid-column:2}.stat-row{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<header><div class="header-inner">
  <div class="brand"><div class="brand-mark">W</div><div><h1 data-i18n="brand">WorldOS 世界观察台</h1><small data-i18n="readonly">只读观察模式 · Inspector 2.0</small></div></div>
  <div class="toolbar">
    <input id="timeline" value="main" aria-label="Timeline">
    <button class="primary" id="refreshBtn" onclick="loadAll()" data-i18n="refresh">刷新世界</button>
    <button class="ghost" id="langBtn" onclick="toggleLang()">English</button>
  </div>
</div></header>
<div class="shell">
<section class="hero">
  <div><div class="eyebrow">WORLDOS · LIVING WORLD</div><h2 id="worldTitle">First Living World</h2><p data-i18n="heroText">从世界、地点、居民、认知和事件五个层次观察一个持续运行的 AI 世界。这里永远只读，不会改变世界。</p></div>
  <div class="status-pill"><span class="dot"></span><span data-i18n="healthy">世界数据可读取</span></div>
</section>
<section class="metrics">
  <div class="metric"><div class="metric-label" data-i18n="currentTick">当前时间</div><div class="metric-value" id="tickValue">—</div><div class="metric-sub">Tick</div></div>
  <div class="metric"><div class="metric-label" data-i18n="residents">居民</div><div class="metric-value" id="actorCount">—</div><div class="metric-sub" data-i18n="residentsSub">可观察角色</div></div>
  <div class="metric"><div class="metric-label" data-i18n="locations">地点</div><div class="metric-value" id="locationCount">—</div><div class="metric-sub" data-i18n="locationsSub">世界空间</div></div>
  <div class="metric"><div class="metric-label" data-i18n="events">累计事件</div><div class="metric-value" id="eventCount">—</div><div class="metric-sub" data-i18n="eventsSub">事件账本</div></div>
  <div class="metric"><div class="metric-label" data-i18n="timeline">世界线</div><div class="metric-value" id="timelineValue">main</div><div class="metric-sub" id="hashValue">—</div></div>
</section>
<div class="grid">
  <div class="column">
    <section class="card"><div class="card-head"><div><h3 data-i18n="map">世界地图</h3><div class="hint" data-i18n="mapHint">谁现在在哪里</div></div></div><div class="map-grid" id="mapGrid"></div></section>
    <section class="card"><div class="card-head"><div><h3 data-i18n="actorList">居民列表</h3><div class="hint" data-i18n="actorHint">点击居民查看其状态、目标、认知与记忆</div></div></div><div class="actor-grid" id="actorGrid"></div></section>
    <section class="card"><div class="card-head"><div><h3 data-i18n="eventTimeline">世界事件流</h3><div class="hint" data-i18n="eventHint">最近 200 条已提交事件</div></div></div><div class="timeline" id="eventList"></div><details><summary data-i18n="rawEvents">查看原始事件 JSON</summary><pre id="eventsRaw"></pre></details></section>
  </div>
  <div class="column">
    <section class="card"><div class="card-head"><div><h3 data-i18n="actorPanel">居民观察</h3><div class="hint" id="actorPanelHint" data-i18n="actorPanelHint">从左侧选择一名居民</div></div></div><div id="actorPanel" class="empty" data-i18n="actorEmpty">选择一个居民，查看他/她眼中的这个世界。</div></section>
    <section class="card"><div class="card-head"><div><h3 data-i18n="narrator">叙事视角</h3><div class="hint" data-i18n="narratorHint">默认全知；选择居民后切换为该居民所知</div></div></div><div class="narrative-box" id="narrativeBox"></div><details><summary data-i18n="rawNarrator">查看 Narrator 原始上下文</summary><pre id="narratorRaw"></pre></details></section>
    <section class="card"><div class="card-head"><div><h3 data-i18n="relationships">人际关系</h3><div class="hint" data-i18n="relationshipsHint">当前世界投影中的关系数据</div></div></div><div id="relationshipList"></div><details><summary data-i18n="rawRelationships">查看原始关系 JSON</summary><pre id="relationshipsRaw"></pre></details></section>
    <section class="card"><div class="card-head"><div><h3 data-i18n="compare">世界线对比</h3><div class="hint" data-i18n="compareHint">比较 main 与另一条分支世界</div></div></div><div class="toolbar" style="justify-content:flex-start"><input id="compareTimeline" placeholder="living-world-alternate"><button class="ghost" onclick="loadCompare()" data-i18n="compareBtn">开始对比</button></div><div id="compareResult" class="compare-result" style="margin-top:12px"></div><details><summary data-i18n="rawCompare">查看原始对比 JSON</summary><pre id="compareRaw"></pre></details></section>
  </div>
</div>
</div>
<div id="toast" class="toast"></div>
<script>
const I18N={
 zh:{brand:'WorldOS 世界观察台',readonly:'只读观察模式 · Inspector 2.0',refresh:'刷新世界',heroText:'从世界、地点、居民、认知和事件五个层次观察一个持续运行的 AI 世界。这里永远只读，不会改变世界。',healthy:'世界数据可读取',currentTick:'当前时间',residents:'居民',residentsSub:'可观察角色',locations:'地点',locationsSub:'世界空间',events:'累计事件',eventsSub:'事件账本',timeline:'世界线',map:'世界地图',mapHint:'谁现在在哪里',actorList:'居民列表',actorHint:'点击居民查看其状态、目标、认知与记忆',eventTimeline:'世界事件流',eventHint:'最近 200 条已提交事件',rawEvents:'查看原始事件 JSON',actorPanel:'居民观察',actorPanelHint:'从左侧选择一名居民',actorEmpty:'选择一个居民，查看他/她眼中的这个世界。',narrator:'叙事视角',narratorHint:'默认全知；选择居民后切换为该居民所知',rawNarrator:'查看 Narrator 原始上下文',relationships:'人际关系',relationshipsHint:'当前世界投影中的关系数据',rawRelationships:'查看原始关系 JSON',compare:'世界线对比',compareHint:'比较 main 与另一条分支世界',compareBtn:'开始对比',rawCompare:'查看原始对比 JSON',people:'人',noPeople:'暂无居民',location:'地点',health:'健康',hunger:'饥饿',fatigue:'疲劳',wallet:'钱包',job:'职业',inventory:'库存',goals:'当前目标',plans:'计划步骤',beliefs:'这个人相信的事',memories:'最近记忆',observations:'最近观察',active:'活跃',inactive:'停止活动',none:'暂无',omniscient:'全知视角',perspective:'人物视角',event:'事件',tick:'Tick',sameWorld:'两个世界当前状态相同',differentWorld:'两个世界已经产生差异',changedActors:'变化实体',worldCreated:'世界创建',entityCreated:'实体出现',componentSet:'状态变化',moved:'移动',healthChanged:'健康变化',observationCreated:'产生观察',beliefUpdated:'形成认知',memoryRecorded:'形成记忆',goalCreated:'产生目标',goalChanged:'目标状态变化',planCreated:'生成计划',planChanged:'计划状态变化',tickStarted:'时间推进开始',tickCompleted:'时间推进完成',tradeCompleted:'完成交易',resourceProduced:'生产资源',rumorSpread:'传播传闻',conflictResolved:'冲突结算',needAssessed:'需求评估',metabolized:'生存消耗',deactivated:'停止活动',flagSet:'世界参数变化',loadError:'读取失败'},
 en:{brand:'WorldOS Observatory',readonly:'Read-only · Inspector 2.0',refresh:'Refresh',heroText:'Observe a persistent AI world through world state, places, residents, cognition, and events. This console is strictly read-only.',healthy:'World data available',currentTick:'Current time',residents:'Residents',residentsSub:'observable actors',locations:'Locations',locationsSub:'world spaces',events:'Events',eventsSub:'event ledger',timeline:'Timeline',map:'World map',mapHint:'Who is where right now',actorList:'Residents',actorHint:'Select a resident to inspect state, goals, beliefs, and memories',eventTimeline:'World events',eventHint:'Latest 200 committed events',rawEvents:'Raw event JSON',actorPanel:'Resident inspector',actorPanelHint:'Select a resident from the left',actorEmpty:'Select a resident to see the world from their perspective.',narrator:'Narrator view',narratorHint:'Omniscient by default; resident selection narrows perspective',rawNarrator:'Raw narrator context',relationships:'Relationships',relationshipsHint:'Relationship data in the current world projection',rawRelationships:'Raw relationship JSON',compare:'Branch comparison',compareHint:'Compare main with another timeline',compareBtn:'Compare',rawCompare:'Raw comparison JSON',people:'people',noPeople:'No residents',location:'Location',health:'Health',hunger:'Hunger',fatigue:'Fatigue',wallet:'Wallet',job:'Job',inventory:'Inventory',goals:'Goals',plans:'Plan steps',beliefs:'Beliefs',memories:'Memories',observations:'Observations',active:'Active',inactive:'Inactive',none:'None',omniscient:'Omniscient',perspective:'Perspective',event:'Event',tick:'Tick',sameWorld:'The two timelines currently match',differentWorld:'The two timelines have diverged',changedActors:'Changed entities',worldCreated:'World created',entityCreated:'Entity created',componentSet:'State changed',moved:'Moved',healthChanged:'Health changed',observationCreated:'Observation',beliefUpdated:'Belief updated',memoryRecorded:'Memory recorded',goalCreated:'Goal created',goalChanged:'Goal status changed',planCreated:'Plan created',planChanged:'Plan status changed',tickStarted:'Tick started',tickCompleted:'Tick completed',tradeCompleted:'Trade completed',resourceProduced:'Resource produced',rumorSpread:'Rumor spread',conflictResolved:'Conflict resolved',needAssessed:'Needs assessed',metabolized:'Metabolism',deactivated:'Deactivated',flagSet:'World flag changed',loadError:'Load failed'}
};
const EVENT_LABELS={
 'world.created':'worldCreated','entity.created':'entityCreated','entity.component_set':'componentSet','entity.component_removed':'componentSet','entity.moved':'moved','health.changed':'healthChanged','observation.created':'observationCreated','belief.updated':'beliefUpdated','memory.recorded':'memoryRecorded','memory.forgotten':'memories','goal.created':'goalCreated','goal.status_changed':'goalChanged','plan.step_created':'planCreated','plan.step_status_changed':'planChanged','tick.started':'tickStarted','tick.completed':'tickCompleted','trade.completed':'tradeCompleted','resource.produced':'resourceProduced','rumor.spread':'rumorSpread','conflict.resolved':'conflictResolved','need.assessed':'needAssessed','survival.metabolized':'metabolized','entity.deactivated':'deactivated','world.flag_set':'flagSet'
};
let lang=localStorage.getItem('worldos.lang')||'zh';let overviewData=null;let eventsData=[];let narratorData=null;let selectedActor=null;
const $=id=>document.getElementById(id);const t=k=>I18N[lang][k]||k;const fmt=x=>JSON.stringify(x,null,2);const timeline=()=>$('timeline').value||'main';
function esc(v){return String(v??'').replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#039;'}[m]))}
function setLang(){document.documentElement.lang=lang==='zh'?'zh-CN':'en';document.title=lang==='zh'?'WorldOS 世界观察台':'WorldOS Observatory';document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));$('langBtn').textContent=lang==='zh'?'English':'中文';localStorage.setItem('worldos.lang',lang);if(overviewData)renderOverview(overviewData);if(eventsData.length)renderEvents(eventsData);if(narratorData)renderNarrative(narratorData);if(selectedActor)loadActor(selectedActor)}
function toggleLang(){lang=lang==='zh'?'en':'zh';setLang()}
async function get(path){const r=await fetch(path,{cache:'no-store'});if(!r.ok)throw new Error(await r.text());return r.json()}
function showToast(message){const el=$('toast');el.textContent=message;el.style.display='block';setTimeout(()=>el.style.display='none',2500)}
function placeLabel(id){if(lang==='zh'){return {farm:'🌾 农场',market:'🏪 市场',homes:'🏠 家园'}[id]||id}return {farm:'🌾 Farm',market:'🏪 Market',homes:'🏠 Homes'}[id]||id}
function resourceLabel(id){if(lang==='zh'){return {food:'食物',wood:'木材',cloth:'布料',tools:'工具'}[id]||id}return id}
function valueOrDash(v){return v===undefined||v===null?'—':v}
function renderOverview(o){overviewData=o;const s=o.summary||{};$('worldTitle').textContent=s.world_name||s.flags?.world_name||s.flags?.name||'First Living World';$('tickValue').textContent=valueOrDash(s.current_tick);$('actorCount').textContent=(o.actors||[]).length;$('locationCount').textContent=Object.keys(o.map||{}).length;$('eventCount').textContent=valueOrDash(s.event_count);$('timelineValue').textContent=s.timeline?.timeline_id||s.timeline_id||timeline();$('hashValue').textContent=s.world_hash?`${s.world_hash.slice(0,10)}…`:'—';renderMap(o.map||{});renderActors(o.actors||[]);renderRelationships(o.relationships||{});$('relationshipsRaw').textContent=fmt(o.relationships||{})}
function renderMap(map){const entries=Object.entries(map);$('mapGrid').innerHTML=entries.length?entries.map(([place,people])=>`<div class="place"><div class="place-name">${esc(placeLabel(place))}</div><div class="place-count">${people.length} ${t('people')}</div><div class="chips">${people.map(id=>`<button class="chip" data-actor="${esc(id)}">${esc(id)}</button>`).join('')}</div></div>`).join(''):`<div class="empty">${t('none')}</div>`;$('mapGrid').querySelectorAll('[data-actor]').forEach(b=>b.addEventListener('click',()=>loadActor(b.dataset.actor)))}
function renderActors(actors){$('actorGrid').innerHTML=actors.length?actors.map(a=>{const needs=a.needs||{};const h=a.health||{};return `<div class="actor-card ${selectedActor===a.actor_id?'active':''}" data-actor="${esc(a.actor_id)}"><div class="actor-title"><span>${esc(a.name||a.actor_id)}</span><span class="${a.active===false?'inactive':''}">${a.active===false?t('inactive'):t('active')}</span></div><div class="actor-id">${esc(a.actor_id)}</div><div class="actor-meta"><span>📍 ${esc(placeLabel(a.location_id||'—'))}</span><span>❤️ ${valueOrDash(h.current)}</span><span>🍚 ${valueOrDash(needs.hunger)}</span><span>😴 ${valueOrDash(needs.fatigue)}</span></div></div>`}).join(''):`<div class="empty">${t('noPeople')}</div>`;$('actorGrid').querySelectorAll('[data-actor]').forEach(c=>c.addEventListener('click',()=>loadActor(c.dataset.actor)))}
function renderRelationships(rels){const rows=[];for(const [actor,targets] of Object.entries(rels)){for(const [target,value] of Object.entries(targets||{}))rows.push(`<div class="item"><strong>${esc(actor)}</strong> → ${esc(target)} <span class="tag">${esc(value)}</span></div>`)}$('relationshipList').innerHTML=rows.length?`<div class="item-list">${rows.join('')}</div>`:`<div class="empty">${t('none')}</div>`}
function eventLabel(type){const key=EVENT_LABELS[type];return key?t(key):type}
function eventSummary(e){const p=e.payload||{};if(e.event_type==='entity.moved')return `${e.actor_id||e.subject_ids?.[0]||''} → ${placeLabel(p.to_location_id)}`;if(e.event_type==='health.changed')return `${e.subject_ids?.[0]||''} ${p.delta>0?'+':''}${p.delta??''}`;if(e.event_type==='resource.produced')return `${e.actor_id||''} ${resourceLabel(p.resource||'')} +${p.quantity??''}`;if(e.event_type==='trade.completed')return `${p.seller_id||e.actor_id||''} ↔ ${p.buyer_id||''} ${resourceLabel(p.resource||'')}`;if(e.event_type==='rumor.spread')return `${e.actor_id||''} → ${p.listener_id||p.target_id||''}`;if(e.event_type==='goal.created')return `${e.actor_id||p.owner_id||''} · ${p.goal_type||''}`;if(e.event_type==='observation.created')return `${p.observer_id||e.actor_id||''} · ${p.fact_type||''}`;if(e.event_type==='belief.updated')return `${p.observer_id||e.actor_id||''} · ${p.fact_type||''}`;return e.actor_id||e.subject_ids?.join(', ')||''}
function renderEvents(events){eventsData=events;$('eventsRaw').textContent=fmt(events);const ordered=[...events].reverse();$('eventList').innerHTML=ordered.map(e=>`<div class="event"><span class="seq">#${e.sequence}<br>Tick ${e.tick}</span><span class="event-type">${esc(eventLabel(e.event_type))}</span><span class="event-main">${esc(eventSummary(e))}</span></div>`).join('')||`<div class="empty">${t('none')}</div>`}
function renderNarrative(n){narratorData=n;$('narratorRaw').textContent=fmt(n);const mode=n.mode==='actor'?t('perspective'):t('omniscient');const events=n.events||[];$('narrativeBox').innerHTML=`<div class="hint" style="margin-bottom:8px">${mode}${n.perspective_actor_id?' · '+esc(n.perspective_actor_id):''}</div>`+(events.length?events.slice(-40).reverse().map(e=>`<div class="narrative-event"><span class="tag">Tick ${e.tick}</span><strong>${esc(eventLabel(e.event_type))}</strong> · ${esc(eventSummary(e))}</div>`).join(''):`<div class="empty">${t('none')}</div>`)}
function listSection(title,items,render){return `<div class="section-title">${title}</div><div class="item-list">${items?.length?items.map(render).join(''):`<div class="item">${t('none')}</div>`}</div>`}
function renderActor(a){const e=a.entity||{};const c=e.components||{};const identity=c.identity||{};const needs=c.needs||c.survival||{};const health=c.health||{};const job=c.job||{};const inv=c.inventory||{};const name=identity.name||a.actor_id;const invText=Object.entries(inv).map(([k,v])=>`${resourceLabel(k)} ${v}`).join(' · ')||t('none');let html=`<div class="profile-title">${esc(name)}</div><div class="profile-id">${esc(a.actor_id)}</div><div class="stat-row"><div class="mini"><span>${t('location')}</span><strong>${esc(placeLabel(c.position?.location_id||'—'))}</strong></div><div class="mini"><span>${t('health')}</span><strong>${valueOrDash(health.current)} / ${valueOrDash(health.maximum)}</strong></div><div class="mini"><span>${t('wallet')}</span><strong>${valueOrDash(c.wallet)}</strong></div><div class="mini"><span>${t('hunger')}</span><strong>${valueOrDash(needs.hunger)}</strong></div><div class="mini"><span>${t('fatigue')}</span><strong>${valueOrDash(needs.fatigue)}</strong></div><div class="mini"><span>${t('job')}</span><strong>${esc(resourceLabel(job.resource||'—'))}${job.rate?` ×${job.rate}`:''}</strong></div></div><div class="section-title">${t('inventory')}</div><div class="item">${esc(invText)}</div>`;
 html+=listSection(t('goals'),a.goals,g=>`<div class="item"><span class="tag">${esc(g.status)}</span><strong>${esc(g.goal_type)}</strong><br><span class="hint">priority ${g.priority} · ${esc(fmt(g.parameters||{}))}</span></div>`);
 html+=listSection(t('plans'),a.plan_steps,s=>`<div class="item"><span class="tag">${esc(s.status)}</span><strong>${esc(s.action_type)}</strong><br><span class="hint">${esc(fmt(s.arguments||{}))}</span></div>`);
 html+=listSection(t('beliefs'),a.beliefs,b=>`<div class="item"><strong>${esc(b.fact_type)}</strong> · ${Math.round((b.confidence??0)*100)}%<br><span class="hint">${esc(fmt(b.data||{}))}</span></div>`);
 html+=listSection(t('memories'),a.memories,m=>`<div class="item"><span class="tag">${esc(m.kind)}</span><strong>Tick ${m.tick}</strong> · ${Math.round((m.confidence??0)*100)}%<br><span class="hint">${esc(fmt(m.content||{}))}</span></div>`);
 html+=listSection(t('observations'),a.observations,o=>`<div class="item"><strong>${esc(o.fact_type)}</strong> · Tick ${o.tick}<br><span class="hint">${esc(fmt(o.data||{}))}</span></div>`);
 html+=`<details><summary>${lang==='zh'?'查看该居民原始 JSON':'Raw resident JSON'}</summary><pre>${esc(fmt(a))}</pre></details>`;$('actorPanel').className='';$('actorPanel').innerHTML=html;$('actorPanelHint').textContent=name}
async function loadActor(id){if(!id)return;selectedActor=id;try{document.body.classList.add('loading');const q=encodeURIComponent(timeline());const actor=await get('/api/actor/'+encodeURIComponent(id)+'?timeline='+q);const narrative=await get('/api/narrative?timeline='+q+'&actor='+encodeURIComponent(id));renderActor(actor);renderNarrative(narrative);if(overviewData)renderActors(overviewData.actors||[])}catch(e){showToast(t('loadError')+': '+e.message)}finally{document.body.classList.remove('loading')}}
async function loadCompare(){const right=$('compareTimeline').value.trim();if(!right)return;try{const data=await get('/api/compare?left='+encodeURIComponent(timeline())+'&right='+encodeURIComponent(right));$('compareRaw').textContent=fmt(data);$('compareResult').innerHTML=`<div class="${data.same_world?'same':'different'}"><strong>${data.same_world?t('sameWorld'):t('differentWorld')}</strong></div>${data.changed_entities?.length?`<div style="margin-top:6px">${t('changedActors')}: ${data.changed_entities.map(esc).join(', ')}</div>`:''}`}catch(e){showToast(t('loadError')+': '+e.message)}}
async function loadAll(){selectedActor=null;try{document.body.classList.add('loading');const q=encodeURIComponent(timeline());const [o,e,n]=await Promise.all([get('/api/overview?timeline='+q),get('/api/events?timeline='+q+'&limit=200'),get('/api/narrative?timeline='+q)]);renderOverview(o);renderEvents(e);renderNarrative(n);$('actorPanel').className='empty';$('actorPanel').textContent=t('actorEmpty');$('actorPanelHint').textContent=t('actorPanelHint');$('compareResult').innerHTML=''}catch(e){showToast(t('loadError')+': '+e.message)}finally{document.body.classList.remove('loading')}}
setLang();loadAll();
</script>
</body></html>"""


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
        bundle = self.inspector.bundle(timeline_id)
        world = bundle.world
        actors: list[dict[str, Any]] = []
        locations: dict[str, list[str]] = {}
        relationships: dict[str, Any] = {}
        for entity_id, entity in sorted(world.entities.items()):
            components = entity.components
            position = components.get("position", {})
            location_id = position.get("location_id") if isinstance(position, dict) else None
            if entity.kind == "human" or any(key in components for key in ("needs", "health", "memory")):
                identity = components.get("identity", {})
                health = components.get("health", {})
                needs = components.get("needs", components.get("survival", {}))
                actors.append(
                    {
                        "actor_id": entity_id,
                        "name": identity.get("name", entity_id) if isinstance(identity, dict) else entity_id,
                        "kind": entity.kind,
                        "location_id": location_id,
                        "active": entity.active,
                        "health": health if isinstance(health, dict) else {},
                        "needs": needs if isinstance(needs, dict) else {},
                        "wallet": components.get("wallet"),
                        "job": components.get("job", {}),
                    }
                )
            if location_id:
                locations.setdefault(str(location_id), []).append(entity_id)
            if "relationships" in components:
                relationships[entity_id] = components["relationships"]
        timeline = self.store.timeline(timeline_id)
        current_tick = bundle.events[-1].tick if bundle.events else 0
        return {
            "summary": {
                "timeline": timeline,
                "timeline_id": timeline_id,
                "through_sequence": bundle.through_sequence,
                "event_count": bundle.through_sequence,
                "current_tick": current_tick,
                "world_hash": world.canonical_hash(),
                "world_name": world.flags.get("world_name") or world.flags.get("name"),
                "flags": world.flags,
                "entity_count": len(world.entities),
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
