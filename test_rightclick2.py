#!/usr/bin/env python3
"""Open indicator settings via right-click, then check all input types."""
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

        # Right-click the indicator name
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
        # Right-click
        await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "right", "clickCount": 1})
        await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "right", "clickCount": 1})
        await asyncio.sleep(1.5)

        # Find "Settings..." (with ellipsis) and click
        pos = await safe_eval("""
            JSON.stringify((() => {
                const menus = document.querySelectorAll('[class*="menu"], [role="menu"], [class*="popup"]');
                for (const m of menus) {
                    if (m.offsetParent !== null) {
                        const items = m.querySelectorAll('button, [role="menuitem"], [class*="item"]');
                        for (const it of items) {
                            if ((it.textContent || '').trim() === 'Settings\u2026' || (it.textContent || '').trim() === 'Settings...') {
                                const r = it.getBoundingClientRect();
                                return {x: r.x + r.width/2, y: r.y + r.height/2};
                            }
                        }
                    }
                }
                return null;
            })())
        """)
        if pos and pos != "null":
            pt2 = json.loads(pos)
            print(f"Clicking 'Settings...' at ({pt2['x']:.1f}, {pt2['y']:.1f})")
            await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt2["x"], "y": pt2["y"], "button": "left", "clickCount": 1})
            await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt2["x"], "y": pt2["y"], "button": "left", "clickCount": 1})
            await asyncio.sleep(3)

            # Check for ALL input types in visible elements
            state = await safe_eval("""
                JSON.stringify((() => {
                    // Check all input types
                    const inputs = document.querySelectorAll('input, textarea, select');
                    const info = Array.from(inputs).map(el => ({
                        tag: el.tagName,
                        type: el.type || '',
                        id: el.id || '',
                        placeholder: el.placeholder || '',
                        value: (el.value || '').substring(0, 40),
                        visible: el.offsetParent !== null,
                        parentText: ((el.closest('[class*="row"]') || el.parentElement)?.textContent || '').trim().substring(0, 80)
                    }));
                    // Also check visible dialogs content
                    const dialogs = Array.from(document.querySelectorAll('[class*="dialog"], [class*="overlay"], [class*="sidebar"], [class*="panel"]'));
                    const visibleDialogs = dialogs.filter(d => d.offsetParent !== null).map(d => ({
                        cls: d.className.substring(0, 60),
                        text: d.textContent.substring(0, 100),
                        inputs: d.querySelectorAll('input, textarea, select').length
                    }));
                    return {inputs: info, dialogs: visibleDialogs};
                })())
            """)
            print(f"Result: {state[:2000]}")
        else:
            print("Settings... not found in context menu")

asyncio.run(main())
