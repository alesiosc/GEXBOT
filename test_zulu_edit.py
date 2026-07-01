#!/usr/bin/env python3
"""Test: click ZULU edit icon, find input, set value."""
import asyncio, json, urllib.request, sys
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

        # 1. Open settings
        gear = await eval_obj("""
            (() => {
                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                for (const ind of indicators) {
                    const txt = ind.textContent;
                    if (txt.includes('v13.8') || txt.includes('v13.7') || txt.includes('v13.6') || txt.includes('Friday 13th')) {
                        let el = ind;
                        while (el && !el.className.includes('item') && !el.className.includes('study')) {
                            el = el.parentElement;
                        }
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
        if not gear:
            print("No gear")
            return
        await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
        await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(3)
        print("Settings opened")

        # 2. Find ZULU cell and click its inner-slot
        slot_pos = await eval_obj("""
            (() => {
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if ((el.textContent || '').trim() === 'ZULU Levels' && el.children.length === 0) {
                        let cell = el.parentElement;
                        while (cell && !cell.className.includes('cell-RLntasnw') && cell !== document.body) {
                            cell = cell.parentElement;
                        }
                        if (cell) {
                            const next = cell.nextElementSibling;
                            if (next) {
                                const slot = next.querySelector('[class*="inner-slot"]');
                                if (slot) {
                                    const r = slot.getBoundingClientRect();
                                    return {x: r.x + r.width/2, y: r.y + r.height/2};
                                }
                                // Try icon wrapper
                                const icon = next.querySelector('[class*="icon-wrapper"]');
                                if (icon) {
                                    const r = icon.getBoundingClientRect();
                                    return {x: r.x + r.width/2, y: r.y + r.height/2, icon: true};
                                }
                            }
                        }
                        break;
                    }
                }
                return null;
            })()
        """)
        if not slot_pos:
            print("No ZULU input slot found")
            # Try finding it by cell index instead
            return

        print(f"Clicking ZULU input at ({slot_pos['x']:.1f}, {slot_pos['y']:.1f})")
        await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": slot_pos["x"], "y": slot_pos["y"], "button": "left", "clickCount": 1})
        await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": slot_pos["x"], "y": slot_pos["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(2)

        # 3. Check if a text input appeared
        result = await eval_obj("""
            (() => {
                // Find ZULU cell and look for visible text inputs
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    if ((el.textContent || '').trim() === 'ZULU Levels' && el.children.length === 0) {
                        let cell = el.parentElement;
                        while (cell && !cell.className.includes('cell-RLntasnw') && cell !== document.body) {
                            cell = cell.parentElement;
                        }
                        if (cell) {
                            const next = cell.nextElementSibling;
                            if (next) {
                                const inputs = next.querySelectorAll('input, textarea');
                                const info = [];
                                for (const inp of inputs) {
                                    info.push({
                                        tag: inp.tagName,
                                        type: inp.type || '',
                                        visible: inp.offsetParent !== null,
                                        value: (inp.value || '').substring(0, 60)
                                    });
                                }
                                // Also check the full HTML content of this cell
                                return {
                                    inputs: info,
                                    cellText: (next.textContent || '').trim().substring(0, 100),
                                    cellHTML: (next.innerHTML || '').substring(0, 300)
                                };
                            }
                        }
                        break;
                    }
                }
                return null;
            })()
        """)
        print(f"ZULU cell after click: {json.dumps(result, indent=2)[:1500]}")

asyncio.run(main())
