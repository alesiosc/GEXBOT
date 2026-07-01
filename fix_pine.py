#!/usr/bin/env python3
"""Fix Pine Script semicolons in v13.9 file."""
import re

path = r"D:\MyPythonProjects_2\Friday 13th  NQ+ES-SET 1-3+BKBrown - v13.5 (Color Coded-2)\Friday 13th NQ+ES+YM SET 1-8 - v13.9 (Single Input+Zulu).txt"

with open(path, 'r') as f:
    content = f.read()

# Replace multi-assignment lines with semicolons
# Pattern: "pickC := volLoColor; pickW := volLoWidth; pickS := volLoLineConst"
def fix_semicolons(m):
    line = m.group(0)
    indent = re.match(r'^(\s*)', line).group(1)
    parts = line.strip().split(';')
    result = []
    for p in parts:
        p = p.strip()
        if p:
            result.append(indent + '    ' + p)
    return '\n'.join(result)

# Match lines that have multiple assignments separated by semicolons
lines = content.split('\n')
new_lines = []
for line in lines:
    if 'pickC :=' in line and ';' in line:
        # Split on semicolons
        indent = re.match(r'^(\s*)', line).group(1)
        parts = line.strip().split(';')
        for p in parts:
            p = p.strip()
            if p:
                new_lines.append(indent + '    ' + p)
    else:
        new_lines.append(line)

with open(path, 'w') as f:
    f.write('\n'.join(new_lines))

print(f"Fixed {sum(1 for l in new_lines if 'pickC :=' in l)} lines")
