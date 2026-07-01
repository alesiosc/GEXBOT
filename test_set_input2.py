#!/usr/bin/env python3
"""Set Zulu levels via TV API - proper nested value."""
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
            val = r.get("result",{}).get("result",{}).get("value")
            return val

        await cdp("Page.enable")

        test_val = "NQ - Zulu Vol Lo 11111; Zulu Vol Hi 22222; Zulu OI Lo 33333; Zulu OI Hi 44444; ES - Zulu Vol Lo 5555; Zulu Vol Hi 6666; Zulu OI Lo 7777; Zulu OI Hi 8888"
        test_val_esc = test_val.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')

        raw = await safe_eval(f"""
            (() => {{
                try {{
                    const widget = widgetbar.chartWidgetCollection.activeChartWidget.value();
                    const model = widget.model();
                    const ds = model.dataSources();
                    const source5 = ds[5];
                    const result = {{}};

                    // Method 1: set in_52.v directly via _changeInputsImpl
                    try {{
                        source5._changeInputsImpl({{
                            'in_52': {{'v': '{test_val_esc}', 'f': true, 't': 'text'}}
                        }});
                        result.m1 = 'OK';
                    }} catch(e) {{
                        result.m1 = 'error: ' + e.message;
                    }}

                    // Method 2: Set on properties object
                    try {{
                        const props = source5.properties();
                        if (props && props.in_52) {{
                            props.in_52.v = '{test_val_esc}';
                            result.m2 = 'set on props';
                        }} else {{
                            result.m2 = 'no props.in_52';
                        }}
                    }} catch(e) {{
                        result.m2 = 'error: ' + e.message;
                    }}

                    // Method 3: Modify inputs object directly
                    try {{
                        const inputs = source5.inputs();
                        if (inputs && inputs.in_52) {{
                            inputs.in_52.v = '{test_val_esc}';
                            result.m3 = 'set on inputs obj';
                        }} else {{
                            result.m3 = 'no inputs.in_52, keys: ' + Object.keys(inputs || {{}}).slice(0,5).join(',');
                        }}
                    }} catch(e) {{
                        result.m3 = 'error: ' + e.message;
                    }}

                    return JSON.stringify(result);
                }} catch(e) {{
                    return JSON.stringify({{error: e.message}});
                }}
            }})()
        """)
        print(f"Result: {raw[:1000]}")

        await asyncio.sleep(2)

        r2 = await safe_eval("""
            JSON.stringify((() => {
                try {
                    const widget = widgetbar.chartWidgetCollection.activeChartWidget.value();
                    const model = widget.model();
                    const ds = model.dataSources();
                    const source5 = ds[5];
                    const inp = source5.inputs();
                    const raw = inp.in_52;
                    return {in_52_v: typeof raw === 'object' ? raw.v?.substring(0, 80) : String(raw).substring(0, 80)};
                } catch(e) {
                    return {error: e.message};
                }
            })())
        """)
        print(f"After: {r2}")

asyncio.run(main())
