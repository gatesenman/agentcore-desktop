#!/usr/bin/env bash
# 工具兼容性审计：对每个后端逐项触发 ZCode 工具，记录模型发出的工具名（网关 toollog）+ 副作用校验。
# 用法：audit/run_audit.sh <backend> [model]   需要 agent-service/.env 中的 SiliconFlow 变量
set -u
B=$1; MODEL=${2:-Qwen/Qwen2.5-72B-Instruct}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
NODE=${NODE:-node}
W=/tmp/audit-$B; rm -rf $W; mkdir -p $W; cd $W; git init -q
echo "口令：紫色大象42" > hello.txt; printf 'line1\nTODO_REPLACE\n' > edit.txt
PORT=$((18900 + RANDOM % 50)); LOG=/tmp/audit-$B.toollog; : > $LOG
OUT=$ROOT/audit/result-$B.tsv; printf 'case\tpass\ttools\tevidence\n' > $OUT
run() { # name prompt check_cmd
  local name=$1 prompt=$2 check=$3; local before=$(wc -l < $LOG)
  if [ -n "$ONLY" ] && ! echo ",$ONLY," | grep -q ",$name,"; then return; fi
  AGENT_GATEWAY_TOOLLOG=$LOG AGENT_GATEWAY_CONFIG=/tmp/audit-$B.json SILICONFLOW_MODEL=$MODEL AGENT_BACKEND=$B \
  AGENT_GATEWAY_PORT=$PORT ZCODE_DATA_BASE_DIR=/tmp/zc-audit-$B timeout 240 $NODE $ROOT/bridge/agent-bridge.mjs \
    --mode yolo --json --prompt "$prompt" > /tmp/audit-$B-$name.json 2>/tmp/audit-$B-$name.err
  local resp=$(python3 -c "import json,sys;print(json.load(open('/tmp/audit-$B-$name.json')).get('response','').replace('\n',' ')[:160])" 2>/dev/null)
  local tools=$(tail -n +$((before+1)) $LOG | cut -f2 | sort -u | tr '\n' ',' )
  if RESP="$resp" TOOLS="$tools" bash -c "$check" >/dev/null 2>&1; then p=PASS; else p=FAIL; fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$p" "$tools" "$resp" | tee -a $OUT
}
run chat      "1+1等于几？只回答数字" '[[ "$RESP" == *2* ]]'
run Read      "用 Read 工具读取 hello.txt，告诉我口令" '[[ "$RESP" == *紫色大象42* ]]'
run Write     "用 Write 工具创建 out.txt，内容为 hello-audit" 'grep -q hello-audit out.txt'
run Edit      "用 Edit 工具把 edit.txt 中的 TODO_REPLACE 替换为 DONE_OK" 'grep -q DONE_OK edit.txt'
run Bash      "用 Bash 工具执行：echo \$((6*7)) > bash.txt" 'grep -q 42 bash.txt'
run BashBg    "用 Bash 工具在后台运行 'sleep 1; echo bg-ok > bg.txt'，然后用 TaskOutput 工具查看该后台任务输出" '[[ "$TOOLS" == *TaskOutput* ]]'
run TodoWrite "用 TodoWrite 工具创建两条待办：写代码、写测试，然后用 TodoRead 读取并列出" '[[ "$TOOLS" == *TodoWrite* ]]'
run WebFetch  "用 WebFetch 工具抓取 https://example.com 并告诉我页面标题" '[[ "$RESP" == *Example* ]]'
run Agent     "使用 Agent 工具启动一个子代理，让它读取 hello.txt 并返回口令" '[[ "$TOOLS" == *Agent* && "$RESP" == *紫色大象42* ]]'
run NodeRepl  "使用 mcp__node_repl__js 工具执行 JavaScript：2**10，告诉我结果" '[[ "$TOOLS" == *node_repl* && "$RESP" == *1024* ]]'
run Skill     "使用 Skill 工具调用任意一个可用技能（例如 skill-creator），并简要说明它的用途" '[[ "$TOOLS" == *Skill* ]]'
run PlanMode  "先调用 EnterPlanMode 进入计划模式，制定一个创建 plan.txt 的计划，再调用 ExitPlanMode" '[[ "$TOOLS" == *PlanMode* ]]'
echo "done: $OUT"
