import { test, expect, type Page } from '@playwright/test';
import type { Snapshot } from '../src/types';

async function snapshot(page: Page): Promise<Snapshot> {
  return page.evaluate(async () => (await fetch(`/api/games/${location.pathname.split('/')[2]}`)).json());
}
async function submitDescription(page: Page, text: string) {
  await page.getByLabel('Creature description').fill(text);
  await page.getByRole('button', { name: 'Create creature' }).click();
}
test('StrictMode bootstrap establishes one guest identity',async({page})=>{
  let calls=0;
  await page.route('**/api/session',async route=>{calls++;await route.continue();});
  await page.goto('/');await expect(page.getByRole('button',{name:'Create a lobby'})).toBeEnabled();
  expect(calls).toBe(1);
});
test('two sessions play a complete match, recover an accepted action, and play again', async ({ browser }) => {
  const aContext = await browser.newContext(); const bContext = await browser.newContext();
  const a = await aContext.newPage(); const b = await bContext.newPage();
  const consoleErrors: string[] = [];
  for (const page of [a,b]) page.on('pageerror', e => consoleErrors.push(e.message));
  await a.goto('/'); await b.goto('/');
  await a.getByRole('button', { name: 'Create a lobby' }).click();
  await expect(a.getByRole('heading', { level: 1 })).toHaveText(/^[A-Z2-9]{6}$/);
  const code = (await a.getByRole('heading', { level: 1 }).textContent())!;
  await b.getByLabel('Lobby code').fill(code); await b.getByRole('button', { name: 'Join lobby' }).click();
  await a.getByRole('button', { name: 'Start creating' }).click(); await b.getByRole('button', { name: 'Start creating' }).click();
  await expect(a.getByRole('heading', { name: 'Describe your first pokemon' })).toBeVisible();
  let releaseAck:()=>void=()=>{};
  const delayedAck=new Promise<void>(resolve=>{releaseAck=resolve;});let delayed=false;
  await a.route('**/api/games/*/mutations',async route=>{
    if(route.request().postDataJSON().kind==='describe' && !delayed){
      delayed=true;const response=await route.fetch();await delayedAck;await route.fulfill({response});
    } else await route.continue();
  });
  await submitDescription(a, 'A fire fox captain');
  await expect(a.getByRole('heading', { name: 'Describe your second pokemon' })).toBeVisible();
  await a.getByLabel('Creature description').fill('A fire fox reserve');releaseAck();
  await expect(a.getByRole('button',{name:'Create creature'})).toBeEnabled();
  await expect(a.getByLabel('Creature description')).toHaveValue('A fire fox reserve');
  await submitDescription(a, 'A fire fox reserve');
  await submitDescription(b, 'A normal cat captain');
  await expect(b.getByRole('heading', { name: 'Describe your second pokemon' })).toBeVisible();
  await submitDescription(b, 'A normal cat reserve');
  await expect(a.getByRole('button', { name: 'Ready to battle' })).toBeEnabled();
  await a.getByRole('button', { name: 'Ready to battle' }).click(); await b.getByRole('button', { name: 'Ready to battle' }).click();
  await expect(a.getByRole('heading', { name: 'Your next move' })).toBeVisible();
  for(const img of await a.locator('.arena img').all()) await expect(img).toHaveJSProperty('naturalWidth',64);
  await a.screenshot({path:'../docs/screenshots/demo-battle.png',fullPage:true});
  await a.getByRole('button', { name: /Wild strike/ }).click();
  await expect(a.getByRole('status')).toContainText('Choice locked');
  const before = await snapshot(a); await a.reload();
  await expect(a.getByRole('status')).toContainText('Choice locked');
  const after = await snapshot(a); expect(after.own_pending).toEqual(before.own_pending);expect(after.deadline! - before.deadline!).toBeLessThan(.1);
  expect((await snapshot(b)).own_pending).toBeNull();
  await b.getByRole('button', { name: /Wild strike/ }).click();
  await expect.poll(async () => (await snapshot(a)).turn).toBe(2);
  // Both voluntary switches consume turn 2.
  await expect(a.getByRole('button', { name: /Switch to A fire fox reserve/ })).toBeEnabled();
  await a.getByRole('button', { name: /Switch to A fire fox reserve/ }).click();
  await b.getByRole('button', { name: /Switch to A normal cat reserve/ }).click();
  await expect.poll(async () => (await snapshot(a)).turn).toBe(3);
  let forced = false;
  for (let i=0; i<30; i++) {
    const s=await snapshot(a); if (s.phase==='terminal') break;
    if (s.phase==='replacement') {
      forced=true;
      for (const page of [a,b]) {
        const own=await snapshot(page);
        if (s.required.includes(own.player_id)) {
          const reserve=own.teams[own.player_id].find((c,index)=>c && c.current_hp>0 && index!==own.active[own.player_id])!;
          const button=page.getByRole('button',{name:new RegExp(`Switch to ${reserve.name}`)});
          await expect(button).toBeEnabled();await button.click();
        }
      }
      await expect.poll(async ()=>(await snapshot(a)).phase).not.toBe('replacement');
    } else {
      const turn=s.turn;
      for (const page of [a,b]) { await expect(page.getByRole('button',{name:/Wild strike/})).toBeEnabled(); await page.getByRole('button',{name:/Wild strike/}).click(); }
      await expect.poll(async () => { const next=await snapshot(a); return next.turn!==turn || next.phase!=='actions'; }).toBe(true);
    }
  }
  expect(forced).toBe(true);expect((await snapshot(a)).phase).toBe('terminal');
  await expect(a.getByRole('button',{name:'Play again'})).toBeVisible();
  await expect(b.getByRole('button',{name:'Exit to lobby'})).toBeVisible();
  await a.getByRole('button',{name:'Play again'}).click(); await expect(a.getByRole('heading',{level:1})).not.toHaveText(code);
  await b.getByRole('button',{name:'Exit to lobby'}).click(); await expect(b.getByRole('button',{name:'Create a lobby'})).toBeVisible();
  expect(consoleErrors).toEqual([]);await aContext.close();await bContext.close();
});

test('invalid code and unauthorized game URLs recover to lobby', async ({ browser }) => {
  const aContext=await browser.newContext();const bContext=await browser.newContext();const a=await aContext.newPage();const b=await bContext.newPage();
  await a.goto('/');await a.getByLabel('Lobby code').fill('ZZZZZZ');await a.getByRole('button',{name:'Join lobby'}).click();
  await expect(a.getByRole('alert')).toContainText('invalid or expired');
  await a.getByRole('button',{name:'Create a lobby'}).click();await expect(a.getByRole('heading',{level:1})).toHaveText(/^[A-Z2-9]{6}$/);
  await b.goto(a.url());await expect(b.getByRole('alert')).toContainText('not a member');await expect(b.getByRole('button',{name:'Create a lobby'})).toBeVisible();
  await b.goto('/game/unknown');await expect(b.getByRole('alert')).toContainText('unavailable');
  await aContext.close();await bContext.close();
});

for (const width of [360,768,1280]) test(`landing fits ${width}px with keyboard controls`,async ({page})=>{
  await page.setViewportSize({width,height:900});await page.goto('/');await expect(page.getByRole('button',{name:'Create a lobby'})).toBeEnabled();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByLabel('Lobby code').focus();await page.keyboard.type('AAAAAA');await page.keyboard.press('Tab');await expect(page.getByRole('button',{name:'Join lobby'})).toBeFocused();
  await expect(page.locator('.landing')).toHaveCSS('opacity','1');
  await page.screenshot({path:`../docs/screenshots/landing-${width}.png`,fullPage:true});
});
