#!/usr/bin/env python3
"""Test clicking the indicator settings gear via CDP Input.dispatchMouseEvent."""
import asyncio, json, urllib.request
BROWSER_PORT = 9223

def cdp_fetch(path):
    with urllib.request.urlopen(f'http://127.0.0.1:{BROWSER_PORT}{path}', timeout=5) as resp:
        return json.loads(resp.read().decode())

tabs = cdp_fetch('/json')
tv_tab = None
for t in tabs:
    if 'tradingview.com' in t.get('url','') and 'chart' in t.get('url',''):
        tv_tab = t
        break

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
                if r.get("id") == rid:
                    return r

        async def eval_js(js):
            return (await cdp("Runtime.evaluate", {
                "expression": js, "returnByValue": True,
            }))["result"]["result"]["value"]

        await cdp("Page.enable")

        # Get the gear button bounding rect
        rect_str = await eval_js("""
            JSON.stringify((() => {
                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                for (const ind of indicators) {
                    if (ind.textContent.includes('v13.8')) {
                        let el = ind;
                        while (el && !el.className.includes('item')) { el = el.parentElement; }
                        if (el) {
                            const btns = el.querySelectorAll('button');
                            for (const b of btns) {
                                if (b.getAttribute('aria-label') === 'Settings') {
                                    const r = b.getBoundingClientRect();
                                    return {x: r.x, y: r.y, w: r.width, h: r.height};
                                }
                            }
                        }
                    }
                }
                return null;
            })())
        """)
        if not rect_str or rect_str == "null":
            print("Could not find gear button")
            return

        rect = json.loads(rect_str)
        print(f"Gear button at: x={rect['x']}, y={rect['y']}, w={rect['w']}, h={rect['h']}")

        # Wait for page to be ready
        await asyncio.sleep(1)

        # Click at the center of the gear button using CDP Input.dispatchMouseEvent
        cx = rect['x'] + rect['w'] / 2
        cy = rect['y'] + rect['h'] / 2

        print(f"Clicking at ({cx:.1f}, {cy:.1f})")

        # mousePressed
        await cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": cx,
            "y": cy,
            "button": "left",
            "clickCount": 1,
        })
        # mouseReleased
        await cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": cx,
            "y": cy,
            "button": "left",
            "clickCount": 1,
        })

        await asyncio.sleep(3)

        # Check for dialog
        state = await eval_js("""
            JSON.stringify({
                textareas: document.querySelectorAll('textarea').length,
                textareaZulu: Array.from(document.querySelectorAll('textarea')).filter(ta => {
                    const pt = (ta.closest('[class*="row"]') || ta.parentElement)?.textContent || '';
                    return pt.includes('ZULU') || pt.includes('Zulu');
                }).length,
                okBtns: Array.from(document.querySelectorAll('button')).filter(b => b.textContent.trim() === 'OK' || b.textContent.trim() === 'Apply').length,
            })
        """)
        print(f"After click: {state}")

asyncio.run(main())
