#!/usr/bin/env python3
"""After clicking ZULU slot, check what happens."""
import asyncio, json, urllib.request
BROWSER_PORT = 9223
def cdp_fetch(path):
    with urllib.request.urlopen(f'http://127.0.0.1:{BROWSER_PORT}{path}', timeout=5) as resp:
        return json.loads(resp.read().decode())
tabs = cdp_fetch('/json')
tv_tab = None
for t in tabs:
    if 'tradingview.com' in t.get('url','') and 'chart' in t.get('url',''):
        tv_tab = t; break
import websockets

async def main():
    ws_url = tv_tab['webSocketDebuggerUrl']
    async with websockets.connect(ws_url) as ws:
        async def cdp(method, params=None, rid=1):
            cmd = {"id": rid, "method": method}
            if params: cmd["params"] = params
            await ws.send(json.dumps(cmd))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == rid: return r
        async def eval_obj(js):
            r = await cdp("Runtime.evaluate", {"expression": js, "returnByValue": True})
            return r.get("result",{}).get("result",{}).get("value")
        await cdp("Page.enable")

        # Open settings
        gear = await eval_obj("""
            (() => {
                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                for (const ind of indicators) {
                    if (ind.textContent.includes('v13.8')) {
                        let el = ind;
                        while (el && !el.className.includes('item') && !el.className.includes('study')) { el = el.parentElement; }
                        if (el) {
                            const btns = el.querySelectorAll('button');
                            for (const b of btns) {
                                if (b.getAttribute('aria-label') === 'Settings') {
                                    const r = b.getBoundingClientRect(); return {x: r.x+r.width/2, y: r.y+r.height/2};
                                }
                            }
                        }
                    }
                }
                return null;
            })()
        """)
        if not gear: print("no gear"); return
        await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
        await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(3)

        # Click ZULU slot
        slot = await eval_obj("""
            (() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if ((el.textContent||'').trim() === 'ZULU Levels' && el.children.length === 0) {
                        let cell = el.parentElement;
                        while (cell && !cell.className.includes('cell-RLntasnw') && cell !== document.body) { cell = cell.parentElement; }
                        if (cell) {
                            const next = cell.nextElementSibling;
                            if (next) {
                                const s = next.querySelector('[class*="inner-slot"]');
                                if (s) { const r = s.getBoundingClientRect(); return {x: r.x+r.width/2, y: r.y+r.height/2}; }
                            }
                        }
                        break;
                    }
                }
                return null;
            })()
        """)
        if slot:
            await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": slot["x"], "y": slot["y"], "button": "left", "clickCount": 1})
            await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": slot["x"], "y": slot["y"], "button": "left", "clickCount": 1})
            await asyncio.sleep(2)
            print("Slot clicked")

        # After click - dump ZULU cell
        r = await eval_obj("""
            (() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if ((el.textContent||'').trim() === 'ZULU Levels' && el.children.length === 0) {
                        let cell = el.parentElement;
                        while (cell && !cell.className.includes('cell-RLntasnw') && cell !== document.body) { cell = cell.parentElement; }
                        if (cell) {
                            const next = cell.nextElementSibling;
                            if (next) {
                                return {
                                    active: document.activeElement ? document.activeElement.tagName + ' ' + (document.activeElement.className||'').substring(0,40) : 'none',
                                    inputs: Array.from(next.querySelectorAll('input')).map(i => ({
                                        type: i.type, visible: i.offsetParent !== null, value: i.value.substring(0,30), cls: (i.className||'').substring(0,50)
                                    })),
                                    html: next.innerHTML.substring(0, 400)
                                };
                            }
                        }
                        break;
                    }
                }
                return null;
            })()
        """)
        print(json.dumps(r, indent=2)[:1000])

asyncio.run(main())
