from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any

from .events import NewEvent
from .modules import BaseWorldModule, ModuleContext


class SurvivalEconomyModule(BaseWorldModule):
    """Deterministic metabolism, production, scarcity feedback, trade, rumor, and conflict runtime."""

    name = "survival_economy"
    order = 20
    default_hunger_work_limit = 70
    default_fatigue_work_limit = 75

    def before_actions(self, context: ModuleContext) -> list[NewEvent]:
        actors = {entity_id: entity for entity_id, entity in sorted(context.world.entities.items()) if entity.active and entity.kind == "character"}
        staged = {entity_id: deepcopy(entity.components) for entity_id, entity in actors.items()}
        audit: list[NewEvent] = []; health_events: list[NewEvent] = []; resource_modifiers = self._active_resource_shocks(context)
        self._consume_information_stimuli(context, staged, audit)
        for actor_id in sorted(staged):
            components=staged[actor_id]; survival=dict(components.get("survival",{})); needs=dict(components.get("needs",{})); metabolism=dict(components.get("metabolism",{}))
            hunger=self._clamp(needs.get("hunger",survival.get("hunger",0))+metabolism.get("hunger_per_tick",1),0,100); fatigue=self._clamp(needs.get("fatigue",survival.get("fatigue",0))+metabolism.get("fatigue_per_tick",1),0,100)
            needs.update({"hunger":hunger,"fatigue":fatigue}); survival.update({"hunger":hunger,"fatigue":fatigue}); components["needs"]=needs; components["survival"]=survival
            audit.append(self._audit(context.tick,"survival.metabolized",actor_id,{"hunger":hunger,"fatigue":fatigue}))
            if hunger>=100: health_events.append(NewEvent(tick=context.tick,phase="module",event_type="health.changed",actor_id=actor_id,subject_ids=(actor_id,),payload={"delta":-1,"reason":"starvation"}))
            if fatigue>=100: health_events.append(NewEvent(tick=context.tick,phase="module",event_type="health.changed",actor_id=actor_id,subject_ids=(actor_id,),payload={"delta":-1,"reason":"exhaustion"}))
            work_policy=components.get("work_policy",{}); hunger_limit=self._clamp(work_policy.get("max_hunger",self.default_hunger_work_limit) if isinstance(work_policy,dict) else self.default_hunger_work_limit,1,100); fatigue_limit=self._clamp(work_policy.get("max_fatigue",self.default_fatigue_work_limit) if isinstance(work_policy,dict) else self.default_fatigue_work_limit,1,100)
            job=components.get("job")
            if hunger<hunger_limit and fatigue<fatigue_limit and isinstance(job,dict) and job.get("resource") and int(job.get("rate",0))>0:
                resource=str(job["resource"]); base_quantity=int(job["rate"]); modifier=resource_modifiers.get(resource,0.0); exact_quantity=base_quantity*max(0.0,1.0+modifier); carry=dict(components.get("production_carry",{})); accumulated=round(float(carry.get(resource,0.0))+exact_quantity,9); quantity=max(0,int(accumulated)); carry[resource]=round(accumulated-quantity,9); components["production_carry"]=carry; inventory=dict(components.get("inventory",{})); inventory[resource]=int(inventory.get(resource,0))+quantity; components["inventory"]=inventory
                audit.append(self._audit(context.tick,"resource.produced",actor_id,{"resource":resource,"quantity":quantity,"base_quantity":base_quantity,"stimulus_modifier":modifier,"exact_quantity":exact_quantity,"production_carry":carry[resource]}))
        self._update_food_security(context,staged,audit); self._scarcity_market(context,staged,audit); self._spread_rumors(context,staged,audit); self._scarcity_conflicts(context,staged,audit); self._process_trades(context,staged,audit); self._resolve_conflicts(context,staged,audit,health_events)
        changes:list[NewEvent]=[]
        for actor_id in sorted(staged):
            original=actors[actor_id].components; current=staged[actor_id]
            for component in sorted(set(original)-set(current)): changes.append(NewEvent(tick=context.tick,phase="module",event_type="entity.component_removed",actor_id=actor_id,subject_ids=(actor_id,),payload={"component":component}))
            for component,value in sorted(current.items()):
                if original.get(component)!=value: changes.append(NewEvent(tick=context.tick,phase="module",event_type="entity.component_set",actor_id=actor_id,subject_ids=(actor_id,),payload={"component":component,"value":value}))
        damage_by_actor:dict[str,int]={}
        for event in health_events:
            if len(event.subject_ids)==1: damage_by_actor[event.subject_ids[0]]=damage_by_actor.get(event.subject_ids[0],0)+max(0,-int(event.payload.get("delta",0)))
        deactivations=[]
        for actor_id,damage in sorted(damage_by_actor.items()):
            if actor_id not in actors: continue
            health=actors[actor_id].components.get("health",{}); current_health=int(health.get("current",100)) if isinstance(health,dict) else 100
            if damage>0 and current_health-damage<=0: deactivations.append(NewEvent(tick=context.tick,phase="module",event_type="entity.deactivated",actor_id=actor_id,subject_ids=(actor_id,),payload={"reason":"health_depleted"}))
        return changes+health_events+deactivations+audit

    @staticmethod
    def _active_resource_shocks(context: ModuleContext)->dict[str,float]:
        modifiers={}
        for event in context.history:
            if event.event_type!="world.stimulus.resource_shock": continue
            resource=str(event.payload.get("resource") or "").strip()
            if not resource: continue
            duration=max(1,int(event.payload.get("duration_ticks",1)))
            if not (event.tick<context.tick<=event.tick+duration): continue
            magnitude=max(-1.0,min(1.0,float(event.payload.get("magnitude",0.0)))); modifiers[resource]=max(-1.0,min(1.0,modifiers.get(resource,0.0)+magnitude))
        return modifiers

    def _consume_information_stimuli(self,context,staged,audit):
        for event in context.history:
            if event.event_type!="world.stimulus.spread_information": continue
            message=str(event.payload.get("message") or "").strip()
            if not message: continue
            actor_filter={str(item) for item in event.payload.get("actor_ids",[])}; location_filter=str(event.payload.get("location_id") or "").strip()
            for actor_id in sorted(staged):
                if actor_filter and actor_id not in actor_filter: continue
                if location_filter and staged[actor_id].get("position",{}).get("location_id")!=location_filter: continue
                rumors={str(item) for item in staged[actor_id].get("rumors",[])}
                if message in rumors: continue
                rumors.add(message); staged[actor_id]["rumors"]=sorted(rumors); audit.append(self._audit(context.tick,"rumor.seeded",actor_id,{"rumor":message,"stimulus_event_id":event.event_id}))

    def _update_food_security(self,context,staged,audit):
        for actor_id in sorted(staged):
            c=staged[actor_id]; inventory=c.get("inventory",{}); food=int(inventory.get("food",0)) if isinstance(inventory,dict) else 0; needs=c.get("needs",{}); hunger=int(needs.get("hunger",0)) if isinstance(needs,dict) else 0; rumors=[str(i) for i in c.get("rumors",[])]; rumor_pressure=min(3,len(rumors)); risk_bias=self._stable_score(context,actor_id,"scarcity-risk")%4; strategy=c.get("adaptive_strategy",{}); reserve_bonus=int(strategy.get("reserve_bonus",0)) if isinstance(strategy,dict) else 0; target=2+hunger//25+rumor_pressure+risk_bias+reserve_bonus; shortage=max(0,target-food); pressure=self._clamp(shortage*20+hunger//2+rumor_pressure*10,0,100); previous=c.get("food_security",{}); previous_ticks=int(previous.get("scarcity_ticks",0)) if isinstance(previous,dict) else 0; scarcity_ticks=previous_ticks+1 if pressure>=55 else 0; current={"food":food,"target_reserve":target,"shortage":shortage,"pressure":pressure,"rumor_pressure":rumor_pressure,"scarcity_ticks":scarcity_ticks,"adaptive_reserve_bonus":reserve_bonus}; c["food_security"]=current
            if previous!=current: audit.append(self._audit(context.tick,"scarcity.perceived",actor_id,current))
            if pressure>=55:
                rumor="粮食可能会短缺"; known={str(i) for i in c.get("rumors",[])}
                if rumor not in known: c["rumors"]=sorted(known|{rumor}); audit.append(self._audit(context.tick,"rumor.generated",actor_id,{"rumor":rumor,"reason":"food_security","pressure":pressure}))

    def _scarcity_market(self,context,staged,audit):
        for buyer_id in sorted(staged):
            buyer=staged[buyer_id]; security=buyer.get("food_security",{}); shortage=int(security.get("shortage",0)) if isinstance(security,dict) else 0
            if shortage<=0 or int(buyer.get("wallet",0))<=0: continue
            strategy=buyer.get("adaptive_strategy",{}); preferred=set(strategy.get("preferred_partners",[])) if isinstance(strategy,dict) else set(); avoided=set(strategy.get("avoided_partners",[])) if isinstance(strategy,dict) else set(); candidates=[]
            for seller_id in sorted(staged):
                if seller_id==buyer_id or seller_id in avoided or not self._same_location(buyer,staged[seller_id]): continue
                si=staged[seller_id].get("inventory",{}); seller_food=int(si.get("food",0)) if isinstance(si,dict) else 0; ss=staged[seller_id].get("food_security",{}); reserve=int(ss.get("target_reserve",2)) if isinstance(ss,dict) else 2; surplus=seller_food-reserve
                if surplus>0: candidates.append((0 if seller_id in preferred else 1,-surplus,seller_id))
            if not candidates: continue
            _,_,seller_id=sorted(candidates)[0]; seller=staged[seller_id]; price=1+min(4,int(security.get("pressure",0))//25)
            if int(buyer.get("wallet",0))<price: continue
            si=dict(seller.get("inventory",{})); bi=dict(buyer.get("inventory",{})); si["food"]=int(si.get("food",0))-1; bi["food"]=int(bi.get("food",0))+1; seller["inventory"]=si; buyer["inventory"]=bi; seller["wallet"]=int(seller.get("wallet",0))+price; buyer["wallet"]=int(buyer.get("wallet",0))-price; self._change_relationship(seller,buyer_id,1); self._change_relationship(buyer,seller_id,1)
            audit.append(NewEvent(tick=context.tick,phase="module",event_type="scarcity.purchase",actor_id=buyer_id,subject_ids=(buyer_id,seller_id),payload={"buyer_id":buyer_id,"seller_id":seller_id,"resource":"food","quantity":1,"price":price,"reason":"target_reserve","pressure":security.get("pressure",0),"adaptive_preference":seller_id in preferred})); audit.append(self._audit(context.tick,"decision.evidence",buyer_id,{"decision":"hoard_food","because":{"shortage":shortage,"pressure":security.get("pressure",0),"rumors":list(buyer.get("rumors",[])),"adaptive_strategy":strategy},"seller_id":seller_id}))

    def _spread_rumors(self,context,staged,audit):
        actor_ids=sorted(staged)
        for source_id in actor_ids:
            source_rumors=sorted({str(i) for i in staged[source_id].get("rumors",[])})
            if not source_rumors: continue
            relationships=staged[source_id].get("relationships",{})
            for target_id in actor_ids:
                if target_id==source_id or not self._same_location(staged[source_id],staged[target_id]): continue
                target_rumors={str(i) for i in staged[target_id].get("rumors",[])}; missing=[r for r in source_rumors if r not in target_rumors]
                if not missing: continue
                trust=int(relationships.get(target_id,0)) if isinstance(relationships,dict) else 0; ts=staged[target_id].get("adaptive_strategy",{}); skepticism=int(ts.get("rumor_skepticism",0)) if isinstance(ts,dict) else 0; required=-20+(self._stable_score(context,target_id,"rumor-trust")%41)+skepticism; rumor=missing[0]
                if trust<required: audit.append(NewEvent(tick=context.tick,phase="module",event_type="rumor.rejected",actor_id=source_id,subject_ids=(source_id,target_id),payload={"source_id":source_id,"target_id":target_id,"rumor":rumor,"trust":trust,"required_trust":required,"adaptive_skepticism":skepticism})); continue
                staged[target_id]["rumors"]=sorted(target_rumors|{rumor}); audit.append(NewEvent(tick=context.tick,phase="module",event_type="rumor.spread",actor_id=source_id,subject_ids=(source_id,target_id),payload={"source_id":source_id,"target_id":target_id,"rumor":rumor,"trust":trust,"required_trust":required,"adaptive_skepticism":skepticism}))

    def _scarcity_conflicts(self,context,staged,audit):
        for aggressor_id in sorted(staged):
            aggressor=staged[aggressor_id]; security=aggressor.get("food_security",{}); pressure=int(security.get("pressure",0)) if isinstance(security,dict) else 0; scarcity_ticks=int(security.get("scarcity_ticks",0)) if isinstance(security,dict) else 0
            if pressure<75 or scarcity_ticks<3 or isinstance(aggressor.get("conflict"),dict): continue
            strategy=aggressor.get("adaptive_strategy",{}); caution=int(strategy.get("conflict_caution",0)) if isinstance(strategy,dict) else 0; avoided=set(strategy.get("avoided_partners",[])) if isinstance(strategy,dict) else set(); candidates=[]
            for target_id in sorted(staged):
                if target_id==aggressor_id or not self._same_location(aggressor,staged[target_id]): continue
                inventory=staged[target_id].get("inventory",{}); food=int(inventory.get("food",0)) if isinstance(inventory,dict) else 0; relationship=int(aggressor.get("relationships",{}).get(target_id,0)) if isinstance(aggressor.get("relationships",{}),dict) else 0
                if food>=3: candidates.append((0 if target_id in avoided else 1,-food,relationship,target_id))
            if not candidates: continue
            _,target_food_neg,relationship,target_id=sorted(candidates)[0]; threshold=80+max(0,relationship)+caution
            if pressure<threshold: continue
            severity=self._clamp(20+pressure-threshold,10,60); aggressor["conflict"]={"target_id":target_id,"severity":severity,"reason":"food_scarcity"}; audit.append(self._audit(context.tick,"decision.evidence",aggressor_id,{"decision":"resource_conflict","because":{"pressure":pressure,"scarcity_ticks":scarcity_ticks,"relationship":relationship,"target_food":-target_food_neg,"adaptive_caution":caution},"target_id":target_id,"severity":severity}))

    def _process_trades(self,context,staged,audit):
        for seller_id in sorted(staged):
            offer=staged[seller_id].get("trade_offer")
            if not isinstance(offer,dict): continue
            buyer_id=str(offer.get("buyer_id",""))
            if buyer_id not in staged or not self._same_location(staged[seller_id],staged[buyer_id]): continue
            resource=str(offer.get("resource","")); quantity=max(0,int(offer.get("quantity",0))); price=max(0,int(offer.get("price",0))); si=dict(staged[seller_id].get("inventory",{})); bi=dict(staged[buyer_id].get("inventory",{})); sw=int(staged[seller_id].get("wallet",0)); bw=int(staged[buyer_id].get("wallet",0))
            if not resource or quantity<=0 or int(si.get(resource,0))<quantity or bw<price: continue
            si[resource]=int(si.get(resource,0))-quantity; bi[resource]=int(bi.get(resource,0))+quantity; staged[seller_id]["inventory"]=si; staged[buyer_id]["inventory"]=bi; staged[seller_id]["wallet"]=sw+price; staged[buyer_id]["wallet"]=bw-price; staged[seller_id].pop("trade_offer",None); self._change_relationship(staged[seller_id],buyer_id,2); self._change_relationship(staged[buyer_id],seller_id,2); audit.append(NewEvent(tick=context.tick,phase="module",event_type="trade.completed",actor_id=buyer_id,subject_ids=(seller_id,buyer_id),payload={"seller_id":seller_id,"buyer_id":buyer_id,"resource":resource,"quantity":quantity,"price":price}))

    def _resolve_conflicts(self,context,staged,audit,health_events):
        for aggressor_id in sorted(staged):
            conflict=staged[aggressor_id].get("conflict")
            if not isinstance(conflict,dict): continue
            target_id=str(conflict.get("target_id","")); severity=self._clamp(conflict.get("severity",1),1,100)
            if target_id not in staged or target_id==aggressor_id or not self._same_location(staged[aggressor_id],staged[target_id]): continue
            damage=max(1,severity//20); health_events.append(NewEvent(tick=context.tick,phase="module",event_type="health.changed",actor_id=aggressor_id,subject_ids=(target_id,),payload={"delta":-damage,"reason":"conflict","aggressor_id":aggressor_id})); self._change_relationship(staged[aggressor_id],target_id,-severity); self._change_relationship(staged[target_id],aggressor_id,-severity); staged[aggressor_id].pop("conflict",None); audit.append(NewEvent(tick=context.tick,phase="module",event_type="conflict.resolved",actor_id=aggressor_id,subject_ids=(aggressor_id,target_id),payload={"aggressor_id":aggressor_id,"target_id":target_id,"severity":severity,"damage":damage,"reason":conflict.get("reason","configured_conflict")}))

    @staticmethod
    def _stable_score(context,actor_id,channel):
        seed=str(context.world.flags.get("seed","worldos")); digest=hashlib.sha256(f"{seed}:{actor_id}:{channel}".encode("utf-8")).digest(); return int.from_bytes(digest[:4],"big")
    @staticmethod
    def _same_location(left,right): return left.get("position",{}).get("location_id")==right.get("position",{}).get("location_id")
    @staticmethod
    def _change_relationship(components,other_id,delta):
        relationships=dict(components.get("relationships",{})); relationships[other_id]=SurvivalEconomyModule._clamp(relationships.get(other_id,0)+delta,-100,100); components["relationships"]=relationships
    @staticmethod
    def _clamp(value,minimum,maximum): return max(minimum,min(maximum,int(value)))
    @staticmethod
    def _audit(tick,event_type,actor_id,payload): return NewEvent(tick=tick,phase="module",event_type=event_type,actor_id=actor_id,subject_ids=(actor_id,),payload=payload)
