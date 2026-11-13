#!/bin/bash
# GLM serve on the upstream MiaAI-Lab recipe v1.10 (~/mia110, @ 549fdc5) at TP=3 on :8888. The settings come from
# ~/v110.env, a symlink to the arm being served: ~/v110stock.env (upstream as shipped plus our deployment settings,
# the baseline) or ~/v110ots.env (the OTS image and its settings). glm-stack.env GLM_START. OTS_SERVE_ARGS (extra
# `tensorfold serve` flags) go to every rank through start-tp3.sh. GPU clocks run unlocked (owner 2026-10-07).
. ~/v110.env
export PORT=8888
# shellcheck disable=SC2086  # OTS_SERVE_ARGS is a list of flags: split on purpose
cd ~/mia110 && exec ./start-tp3.sh ${OTS_SERVE_ARGS:-} </dev/null
