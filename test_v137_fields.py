#!/usr/bin/env python3
"""Check v13.7 settings fields."""
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

        # Open settings for v13.7
        gear = await eval_obj("""
            (() => {
                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                for (const ind of indicators) {
                    const txt = ind.textContent;
                    if (txt.includes('v13.7') || txt.includes('v13.6') || txt.includes('Friday 13th')) {
                        let el = ind;
                        while (el && !el.className.includes('item') && !el.className.includes('study')) { el = el.parentElement; }
                        if (el) {
                            const btns = el.querySelectorAll('button');
                            for (const b of btns) {
                                if (b.getAttribute('aria-label') === 'Settings') {
                                    const r = b.getBoundingClientRect();
                                    return {x: r.x + r.width/2, y: r.y + r.height/2};
                                }
                            }
                        }
                    }
                }
                return null;
            })()
        """)
        if gear:
            await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
            await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
            await asyncio.sleep(3)
            print("Settings opened")

        # Dump ALL visible fields in the settings dialog
        r = await eval_obj("""
            (() => {
                // Find the wrapper-b8SxMnzX (settings dialog container)
                const container = document.querySelector('[class*=\"wrapper-b8SxMnzX\"]');
                if (!container) return 'no wrapper found';
                
                // Get all text (leaf elements) inside
                const all = container.querySelectorAll('*');
                const texts = [];
                for (const el of all) {
                    if (el.children.length === 0) {
                        const txt = (el.textContent || '').trim();
                        if (txt) texts.push({tag: el.tagName, text: txt.substring(0, 80), cls: (el.className||'').substring(0,40)});
                    }
                }
                return texts;
            })()
        """)
        if isinstance(r, list):
            print(f"Fields in v13.7 settings ({len(r)}):")
            for item in r:
                print(f"  {item['text']}")
        else:
            print(f"Result: {r}")

asyncio.run(main())
