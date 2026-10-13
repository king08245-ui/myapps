# 카카오 조회 결과 캐시: (종류, 질의, x, y, 반경) → 결과
import json, os, glob
def key(q): return json.dumps([q['t'], q['q'], round(q.get('x', 0), 5), round(q.get('y', 0), 5), q.get('r', 0), q.get('n', 0), q.get('sort', '')], ensure_ascii=False)
def load():
    C = {}
    for qf, rf in [('qa1_old.json', 'ra1.json')] + [(f'q{n}.json', f'r{n}.json') for n in 'bcdefghijklmnopqrstuvwxyz']:
        if not (os.path.exists(qf) and os.path.exists(rf)): continue
        Q = json.load(open(qf)); R = json.load(open(rf))['out']
        if len(Q) != len(R): continue
        for q, r in zip(Q, R):
            if r and r.get('s') in ('OK', 'ZERO_RESULT'): C[key(q)] = r
    return C
