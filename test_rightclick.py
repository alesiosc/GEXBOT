#!/usr/bin/env python3
"""Click indicator settings via right-click context menu -> Settings."""
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

        async def safe_eval(js):
            r = await cdp("Runtime.evaluate", {"expression": js, "returnByValue": True})
            return r.get("result",{}).get("result",{}).get("value")

        await cdp("Page.enable")
        await asyncio.sleep(1)

        # Right-click the indicator NAME
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
        if not rect_str or rect_str == "null":
            print("No v13.8 indicator")
            exit(1)

        pt = json.loads(rect_str)
        print(f"Right-clicking at ({pt['x']:.1f}, {pt['y']:.1f})")

        await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt["x"], "y": pt["y"], "button": "right", "clickCount": 1})
        await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt["x"], "y": pt["y"], "button": "right", "clickCount": 1})
        await asyncio.sleep(2)

        items = await safe_eval("""
            JSON.stringify((() => {
                const menus = document.querySelectorAll('[class*="menu"], [class*="context"], [role="menu"], [class*="popup"]');
                const found = [];
                for (const m of menus) {
                    if (m.offsetParent !== null) {
                        const items = m.querySelectorAll('button, [role="menuitem"], [class*="item"]');
                        for (const it of items) {
                            const t = (it.textContent || '').trim();
                            if (t) found.push({text: t.substring(0, 50)});
                        }
                    }
                }
                return found;
            })())
        """)
        print(f"Context menu: {items[:500]}")

        if items and items != "null":
            items_list = json.loads(items)
            target_text = None
            for it in items_list:
                t = it.get("text", "").lower()
                if "input" in t or "setting" in t or "parameters" in t:
                    target_text = it["text"]
                    break
            if target_text:
                print(f"Clicking '{target_text}'")
                escaped = target_text.replace("'", "\\'").replace('"', '\\"')
                pos = await safe_eval(f"""
                    JSON.stringify((() => {{
                        const menus = document.querySelectorAll('[class*="menu"], [class*="context"], [role="menu"], [class*="popup"]');
                        for (const m of menus) {{
                            if (m.offsetParent !== null) {{
                                const items = m.querySelectorAll('button, [role="menuitem"], [class*="item"]');
                                for (const it of items) {{
                                    if (it.textContent.trim() === '{escaped}') {{
                                        const r = it.getBoundingClientRect();
                                        return {{x: r.x + r.width/2, y: r.y + r.height/2}};
                                    }}
                                }}
                            }}
                        }}
                        return null;
                    }})())
                """)
                if pos and pos != "null":
                    pt2 = json.loads(pos)
                    print(f"Clicking at ({pt2['x']:.1f}, {pt2['y']:.1f})")
                    await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": pt2["x"], "y": pt2["y"], "button": "left", "clickCount": 1})
                    await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": pt2["x"], "y": pt2["y"], "button": "left", "clickCount": 1})
                    await asyncio.sleep(3)

                    state = await safe_eval("""
                        JSON.stringify({
                            textareas: document.querySelectorAll('textarea').length,
                            zuluTas: Array.from(document.querySelectorAll('textarea')).filter(ta => {
                                const pt = (ta.closest('[class*="row"]') || ta.parentElement)?.textContent || '';
                                return pt.includes('ZULU') || pt.includes('Zulu');
                            }).length,
                            okBtns: Array.from(document.querySelectorAll('button')).filter(b => b.textContent.trim() === 'OK' || b.textContent.trim() === 'Apply').length,
                        })
                    """)
                    print(f"Result: {state}")

asyncio.run(main())
