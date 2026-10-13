#!/bin/bash
# 사용: push_round.sh f  → q_next.json 을 qf.json 으로 저장하고 작업 브랜치 w/qf.json 으로 올림
set -e
n=$1
cd /home/claude/work && cp q_next.json q$n.json
cd /home/claude/myapps && git checkout -q matjip-work && cp /home/claude/work/q$n.json w/q$n.json && git add w/q$n.json \
 && git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit -qm "작업용: 카카오 조회 ($n, 임시)" && git push -q origin matjip-work 2>&1 | grep -v '^remote' || true
git checkout -q main
python3 -c "import json;print(len(json.load(open('/home/claude/work/q$n.json'))),'queries')"
