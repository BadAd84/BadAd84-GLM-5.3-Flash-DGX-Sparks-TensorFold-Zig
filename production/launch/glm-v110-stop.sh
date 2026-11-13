#!/bin/bash
# Stop the GLM serve on every rank with the v1.10 recipe's stop.sh (it saves each rank's log; with SPILL_GIB set it
# also gives the spill tier its flush time). glm-stack.env GLM_STOP. Reads ~/v110.env so a spill-tier arm's settings
# reach stop.sh.
. ~/v110.env
cd ~/mia110 && exec ./stop.sh </dev/null
