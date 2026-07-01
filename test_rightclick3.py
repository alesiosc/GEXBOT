#!/usr/bin/env python3
"""Open indicator settings via right-click -> Indicator inputs, then diagnose."""
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
                if r.get("id") == rid: return r

        async def safe_eval(js):
            r = await cdp("Runtime.evaluate", {"expression": js, "returnByValue": True})
            return r.get("result",{}).get("result",{}).get("value")

        await cdp("Page.enable")
        await asyncio.sleep(1)

        # Right-click v13.8 name
        rect_str = await safe_eval("""
            JSON.stringify((() => {
                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                for (const ind of indicators) {
                    if (ind.textContent.includes('v13.8')) {
                        const r = ind.getBoundingClientRect();
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                    }
                }
                return null;
            })())
        """)
        pt = json.loads(rect_str)
        await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "right", "clickCount": 1})
        await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "right", "clickCount": 1})
        await asyncio.sleep(1)

        # Find "Indicator inputs" and click it
        pos = await safe_eval("""
            JSON.stringify((() => {
                const menus = document.querySelectorAll('[class*="menu"], [role="menu"], [class*="popup"]');
                for (const m of menus) {
                    if (m.offsetParent !== null) {
                        const items = m.querySelectorAll('button, [role="menuitem"], [class*="item"]');
                        for (const it of items) {
                            const t = (it.textContent || '').trim();
                            if (t.includes('Indicator inputs') || t === 'Inputs') {
                                const r = it.getBoundingClientRect();
                                return {x: r.x + r.width/2, y: r.y + r.height/2};
                            }
                        }
                    }
                }
                return null;
            })())
        """)
        if not pos or pos == "null":
            print("Indicator inputs not found")
            return

        pt2 = json.loads(pos)
        print(f"Clicking Indicator inputs at ({pt2['x']:.1f}, {pt2['y']:.1f})")
        await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt2["x"], "y": pt2["y"], "button": "left", "clickCount": 1})
        await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt2["x"], "y": pt2["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(4)

        # FULL DOM dump of the right panel area
        state = await safe_eval("""
            JSON.stringify((() => {
                // Find the right sidebar / trading panel
                const panels = document.querySelectorAll('[class*="trading-panel-content"], [class*="layout__area--tradingpanel"], [class*="sourceProperties"]');
                const info = [];
                for (const p of panels) {
                    if (p.offsetParent !== null) {
                        const txt = p.textContent.substring(0, 500);
                        const childInputs = p.querySelectorAll('input, textarea, select').length;
                        // Get the first level children with their class names
                        const children = Array.from(p.children).slice(0, 5).map(c => ({
                            tag: c.tagName,
                            cls: c.className.substring(0, 60),
                            text: c.textContent.substring(0, 100)
                        }));
                        info.push({cls: p.className.substring(0, 80), children, childInputs, text: txt});
                    }
                }
                // Also check ALL textareas for Zulu content
                const tas = Array.from(document.querySelectorAll('textarea'));
                const zuluTas = tas.map(ta => ({
                    visible: ta.offsetParent !== null,
                    parentText: (ta.parentElement?.textContent || '').substring(0, 100),
                    id: ta.id,
                    value: ta.value.substring(0, 40)
                }));
                return {panels: info, allTextareas: zuluTas};
            })())
        """)
        print(f"State: {state[:3000]}")

asyncio.run(main())
