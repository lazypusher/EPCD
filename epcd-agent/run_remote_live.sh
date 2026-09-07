#!/usr/bin/env bash
# ============================================================================
# EPCD 单轮仿真复核 v3 ▸ 远端 SSH CLI（适配 2026-08-21 服务端二次更新）
#   · 服务器端通知 job result 已可返回 targetValues → 本脚本实证复核
#   · 配置姿势=官方实测校正（em/Local P0 默认 + 顶层 sweeps 字符串）
#   · 全新 request-id（verify-final-* 前缀），不复用任何旧 job
#   · 重点展示打分产出：[RESULT] 表/数据行数、targetValues、objectiveCost、
#     target-values.json 内容与 sha256（对比旧 stub 714907cb… 是否变化）
# ============================================================================
set -u
echo "===== EPCD 单轮仿真复核 ▸ 实时 SSH CLI $(date '+%Y-%m-%d %H:%M:%S %Z') ▸ host=$(hostname) ====="
echo

P="/package/eda9cube-d2026.06.6092-2026_06_sp1-g317a9fd-NINECUBE-2026-08-07-linux-x86-64-default/user.bashrc.ePCD"
PROJ="/home/zhubo/epcd-runs/inductor"
INST="20260820090223000"
RID="verify-final-1"                    # 全新 request-id（避免幂等命中旧 job）
STUB_SHA="714907cb2401b745af456e0e526b42f53394d0af3a1531146e260b3de5633d92"
CAND='{"schemaVersion":"epcd-candidate/v1","parameters":{"trackWidth":10,"trackSpace":3,"numOfTurns":3,"innerRadius":50}}'

source "$P" >/dev/null 2>&1
[ -f ~/.epcd-env ] && source ~/.epcd-env

step() { echo; echo "############################################################"; echo "## $1"; echo "############################################################"; }
cmd()  { echo; echo "\$ $*"; }
digest() { epcd-cli config get --instance-id "$INST" --project "$PROJ" --path / 2>/dev/null \
             | sed -n 's/.*"configDigest":"\([^"]*\)".*/\1/p' | head -1; }

# ---------------------------------------------------------------- STEP 1
step "1. 健康检查"
cmd "epcd-cli version"
epcd-cli version 2>/dev/null
cmd "epcd-cli health"
epcd-cli health 2>/dev/null

# ---------------------------------------------------------------- STEP 2
step "2. 工程与器件现状"
cmd "epcd-cli project describe --project $PROJ"
epcd-cli project describe --project "$PROJ" 2>/dev/null
cmd "epcd-cli project device list --project $PROJ"
epcd-cli project device list --project "$PROJ" 2>/dev/null

# ---------------------------------------------------------------- STEP 3
step "3. 配置三段（仿真设置齐全性）"
cmd "epcd-cli config get --instance-id $INST --project $PROJ --path /synthesisTargets"
epcd-cli config get --instance-id "$INST" --project "$PROJ" --path /synthesisTargets 2>/dev/null
cmd "epcd-cli config get --instance-id $INST --project $PROJ --path /sweeps"
epcd-cli config get --instance-id "$INST" --project "$PROJ" --path /sweeps 2>/dev/null
cmd "epcd-cli config get --instance-id $INST --project $PROJ --path /simulation"
epcd-cli config get --instance-id "$INST" --project "$PROJ" --path /simulation 2>/dev/null

# ---------------------------------------------------------------- STEP 4
step "4. 启动全新候选仿真 run (request-id=$RID)"
D=$(digest)
echo "configDigest=$D"
cmd "epcd-cli run --instance-id $INST --project $PROJ --task simulation-evaluation --input - --if-match $D --request-id $RID"
OUT=$(printf '%s' "$CAND" | epcd-cli run --instance-id "$INST" --project "$PROJ" \
        --task simulation-evaluation --input - --if-match "$D" --request-id "$RID" 2>/dev/null)
echo "$OUT"
JOBID=$(printf '%s' "$OUT" | sed -n 's/.*"jobId":"\([^"]*\)".*/\1/p')
[ -n "$JOBID" ] || { echo "!! 未取到 jobId"; exit 1; }
echo "jobId=$JOBID"

# ---------------------------------------------------------------- STEP 5
step "5. 查看状态（轮询 job get，每 10s）"
for i in $(seq 1 90); do
  G=$(epcd-cli job get --id "$JOBID" 2>/dev/null)
  ST=$(printf '%s' "$G" | sed -n 's/.*"state":"\([^"]*\)".*/\1/p')
  STT=$(printf '%s' "$G" | sed -n 's/.*"status":"\([^"]*\)".*/\1/p')
  printf "  [%02d] %s  state=%-10s status=%s\n" "$i" "$(date '+%H:%M:%S')" "${ST:-?}" "${STT:-?}"
  case "${STT:-}" in succeeded|failed|canceled) break ;; esac
  sleep 10
done

# ---------------------------------------------------------------- STEP 6
step "6. 单轮结果 job result（重点：打分产出）"
cmd "epcd-cli job result --id $JOBID"
epcd-cli job result --id "$JOBID" 2>/dev/null | python3 -c '
import sys, json
try:
    d = sys.stdin.read().strip()
    env = json.loads(d)["data"]
except Exception as e:
    print("(解析失败, 原文如下)", e)
    print(d[:4000]); raise SystemExit
print("status       :", env.get("status"))
print("targetValues :", env.get("targetValues"))
print("objectiveCost:", env.get("objectiveCost"))
print("warnings     :", env.get("warnings"))
print("artifacts    :", [a["type"] for a in env.get("artifacts", [])])
if env.get("targetValues"):
    print("___ SCORING PRESENT (目标值已产出) ___")
else:
    print("___ targetValues 仍为空 ___")
'
echo
echo "--- run.log: [RESULT] 表头 / 数据行数（打分输入） ---"
RLOG="/home/zhubo/epcd-runs/inductor/devices/$INST/runs/$JOBID/run.log"
grep -n "\[RESULT\]" "$RLOG" 2>/dev/null || echo "(无 RESULT 行)"
echo "RESULT 数据行数(除表头): $(grep -c '^\[RESULT\][[:space:]][1-9]' "$RLOG" 2>/dev/null)"
grep -niE "objective|target|scor|cost" "$RLOG" 2>/dev/null | grep -v "^.*\[RESULT\]" | tail -8 || true
echo
echo "--- target-values.json 内容 + sha256（旧 stub=$STUB_SHA）---"
TV="/home/zhubo/epcd-runs/inductor/devices/$INST/runs/$JOBID/artifacts/target-values.json"
cat "$TV" 2>/dev/null || echo "(文件不存在)"
sha256sum "$TV" 2>/dev/null
NEWSHA=$(sha256sum "$TV" 2>/dev/null | cut -d' ' -f1)
if [ "$NEWSHA" = "$STUB_SHA" ]; then
  echo ">>> sha 与旧 stub 一致：打分未产出";
elif [ -n "$NEWSHA" ]; then
  echo ">>> sha 已变化（$NEWSHA vs $STUB_SHA）：打分可能已生效！"
fi

echo
echo "===== [ALL DONE] 复核结束；本窗口可继续敲任意 epcd-cli 命令 ====="