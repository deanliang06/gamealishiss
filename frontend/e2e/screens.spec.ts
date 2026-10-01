import { test, expect, type Page } from '@playwright/test';
import path from 'node:path';
import type { Creature, Snapshot } from '../src/types';

const mon: Creature = { id:'a0',name:'Sapphire fox',types:['water'],sprite:'/fixture.png',renderer_version:'1',catalog_version:'1',level:50,current_hp:90,max_hp:140,status:'poison',sleep_actions:0,
  base_stats:{hp:80,attack:80,defense:80,special_attack:80,special_defense:80,speed:80},battle_stats:{attack:85,defense:85,special_attack:85,special_defense:85,speed:85},
  moves:[0,1,2,3].map(i=>({name:['Tidal strike','Dream dust','Venom touch','Renew'][i],type:'water',category:i===1||i===3?'status':'physical',power:i===1||i===3?0:80,accuracy:95,sleep_chance:i===1?50:0,paralysis_chance:0,poison_chance:i===2?40:0,healing_percent:i===3?35:0})) };
function state(changes: Partial<Snapshot> = {}): Snapshot {
  return {game_id:'fixture',code:'ABC123',player_id:'you',players:['you','opponent'],phase:'actions',turn:4,state_version:10,attempt_id:'attempt',ready_version:5,start_ready:['you','opponent'],ready:['you','opponent'],description_count:2,generation:{},teams:{you:[mon,{...mon,id:'a1',name:'Leaf guardian',current_hp:140,status:null}],opponent:[{...mon,id:'b0',name:'Ember lizard',status:'sleep',sleep_actions:2},{...mon,id:'b1',name:'Stone spirit',status:null}]},active:{you:0,opponent:0},required:['you','opponent'],own_pending:null,submission_ack:null,deadline:1060,server_time:1000,terminal_version:null,terminal_acks:[],result:null,events:['Turn 3','Sapphire fox gained poison.'],resolution_order:['you','opponent'],...changes};
}
async function fixture(page:Page,snapshot:Snapshot) {
  await page.route('**/api/games/fixture',route=>route.fulfill({json:snapshot}));
  await page.route('**/api/games/fixture/mutations',async route=>{
    const request=route.request().postDataJSON();
    if(request.kind==='terminal_ack') snapshot.terminal_acks.push('you');
    await route.fulfill({json:{request_id:request.request_id,accepted:true,state_version:snapshot.state_version}});
  });
  await page.route('**/fixture.png',route=>route.fulfill({contentType:'image/png',path:path.resolve(import.meta.dirname,'../../docs/sprites/preview.png')}));
  await page.routeWebSocket('**/api/games/fixture/ws',ws=>ws.send(JSON.stringify(snapshot)));
  await page.goto('/game/fixture');
}
for(const width of [360,768,1280]) test(`battle fits ${width}px and exposes accessible HP and move effects`,async({page})=>{
  await page.setViewportSize({width,height:900});await fixture(page,state());
  await expect(page.getByRole('heading',{name:'Your next move'})).toBeVisible();
  await expect(page.locator('.sprite-stage img').first()).toHaveJSProperty('naturalWidth',64);
  await expect(page.getByRole('progressbar',{name:'Sapphire fox HP'})).toHaveAttribute('aria-valuenow','90');
  await expect(page.getByRole('button',{name:/Dream dust/})).toContainText('50% sleep');
  await expect(page.getByRole('button',{name:/Renew/})).toContainText('Heal 35%');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('button',{name:/Tidal strike/}).focus();await expect(page.getByRole('button',{name:/Tidal strike/})).toBeFocused();
  await page.screenshot({path:`../docs/screenshots/battle-${width}.png`,fullPage:true});
});

for (const [reason,winner,message,title] of [
  ['generation_failure',null,'Could not complete sprite generation. Please start a new lobby.','Match ended.'],
  ['timeout','opponent','Action deadline expired.','You lost this battle.'],
  ['timeout',null,'Both players missed the deadline.','A draw.'],
  ['battle','you','Your team won.','Victory is yours.'],
  ['battle',null,'Both teams fainted.','A draw.'],
  ['abandonment',null,'Preparation was inactive for five minutes.','Match ended.'],
] as const) test(`terminal screen: ${reason} / ${winner || 'no winner'} / ${message}`,async({page})=>{
  await fixture(page,state({phase:'terminal',terminal_version:10,deadline:null,required:[],result:{reason,winner,message},...(reason==='generation_failure'?{teams:{}}:{})}));
  await expect(page.getByRole('heading',{name:title})).toBeVisible();
  await expect(page.getByText(message)).toBeVisible();await expect(page.getByRole('button',{name:'Exit to lobby'})).toBeVisible();
  await expect(page.getByRole('button',{name:/Tidal strike/})).toHaveCount(0);
});

test('replacement hides attacks and disables fainted/active choices',async({page})=>{
  const s=state({phase:'replacement',required:['you']});s.teams.you[0]!.current_hp=0;
  await fixture(page,s);await expect(page.getByRole('heading',{name:'Choose your replacement'})).toBeVisible();
  await expect(page.getByRole('button',{name:/Switch to Sapphire fox/})).toBeDisabled();
  await expect(page.getByRole('button',{name:/Switch to Leaf guardian/})).toBeEnabled();
  await expect(page.getByRole('button',{name:/Tidal strike/})).toHaveCount(0);
});

test('expired URL returns to lobby with a recoverable message',async({page})=>{
  await page.route('**/api/games/fixture',route=>route.fulfill({status:410,json:{error:{code:'game_expired',message:'This game expired.'}}}));
  await page.routeWebSocket('**/api/games/fixture/ws',ws=>ws.send(JSON.stringify({error:{code:'game_expired',message:'This game expired.'}})));
  await page.goto('/game/fixture');await expect(page.getByRole('alert')).toContainText('expired');await expect(page.getByRole('button',{name:'Create a lobby'})).toBeVisible();
});

test('WebSocket reconnect retains pending choice and discards old snapshots',async({page})=>{
  const s=state({own_pending:{kind:'move',index:2}});let connections=0;
  await page.route('**/api/games/fixture',route=>route.fulfill({json:s}));
  await page.routeWebSocket('**/api/games/fixture/ws',ws=>{
    connections++;ws.send(JSON.stringify(s));
    if(connections===1)setTimeout(()=>ws.close({code:1012,reason:'restart connection'}),300);
    else ws.send(JSON.stringify({...s,state_version:9,own_pending:null,turn:3}));
  });
  await page.goto('/game/fixture');await expect(page.getByRole('status')).toContainText('Choice locked');
  await expect.poll(()=>connections).toBeGreaterThan(1);
  await expect(page.getByRole('status')).toContainText('Choice locked');await expect(page.getByRole('button',{name:/Tidal strike/})).toBeDisabled();await expect(page.getByText('Turn 4',{exact:false}).first()).toBeVisible();
});
