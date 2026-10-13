# 브라우저에서 조각(<<i>>…)으로 받은 결과 파일들을 이어 붙여 JSON으로 저장
import json, sys, glob, os, re
out, n = sys.argv[1], int(sys.argv[2])
D = '/root/.claude/projects/-home-claude/95942618-9c18-534a-b02d-1eb51c8e54c8/tool-results/'
files = sorted(glob.glob(D + 'mcp-remote-devices-Claude_Browser__javascript_tool-*.txt') + glob.glob(D + 'toolu_*.json'), key=os.path.getmtime)[-n:]
parts = {}
for f in files:
    t = json.load(open(f))[0]['text']
    if 'truncated: content too large' in t: sys.exit('잘림: ' + f)
    cut = t.find('\n\n(captured at origin')
    s = json.loads(t[:cut] if cut > 0 else t)
    m = re.match(r'<<(\d+)>>', s)
    parts[int(m.group(1))] = s[m.end():].rstrip(' ')
assert sorted(parts) == list(range(len(parts))), sorted(parts)
d = json.loads(''.join(parts[i] for i in sorted(parts)))
if d.get('compact'):
    def dec(x):
        if len(x) == 5: return {'x': x[0], 'y': x[1], 't': x[2], 'n': x[3], 'road': x[4]}
        return {'n': x[0], 'c': x[1], 'g': x[2], 'a': x[3], 'ra': x[4], 'x': x[5], 'y': x[6], 'id': x[7]}
    d['out'] = [None if r is None else {'s': r[0], 'r': [dec(x) for x in r[1]]} for r in d['out']]
json.dump(d, open(out, 'w'), ensure_ascii=False)
print(out, 'parts', len(parts), d.get('status'), len(d.get('out', [])))
