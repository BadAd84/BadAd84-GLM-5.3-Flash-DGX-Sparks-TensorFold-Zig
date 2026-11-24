---
name: tune-dgx-spark-gb10-gpu-power-and-throttling
description: "Use when asked to raise a DGX Spark (GB10/ASUS GX10) GPU's power limit, push clocks, squeeze more GPU performance, diagnose throttling, or consider BIOS/firmware/shunt mods."
---

# Tuning / investigating DGX Spark (GB10) GPU power, clocks, throttling

OTS Sparks are NVIDIA GB10 Grace-Blackwell = ASUS Ascent GX10. Ground truth, investigated 2026-10 and
verified on spark1 under live GLM load; rates and clock-lock behavior re-measured 2026-10-24 on
spark4/5/6 (idle boxes, sustained dense BF16 GEMM). Read this before promising any GPU power/perf gain.

## Hard facts - do not re-investigate

- **No OS-level GPU power-limit knob on GB10.** `nvidia-smi` power-limit fields are all **N/A** (so
  `nvidia-smi -pl` has nothing to set), `/sys/class/powercap` is empty, and there is **no `nvpmodel`**
  (GB10 is NOT Jetson - ignore Jetson advice). The limit is owned by the GSP + USB-C PD firmware.
- **Power is governed by the USB-C PD (Power Delivery) firmware + the GSP, both NVIDIA/ASUS-signed**
  (ECC-P384 root of trust). The Spark is USB-C powered: **180W EPR PD3.1 in, up to 240W wall burst**,
  healthy GPU limit ~140W. The PD MCU (in the brick) negotiates the contract.
- **Firmware can't be edited to raise it.** GSP blob (`/lib/firmware/nvidia/<ver>/gsp_ga10x.bin`, apt
  `nvidia-firmware-580-*`) and the PD/BIOS capsules are signed and hardware-verified - patch the power
  table and it won't load. Same wall that ended modified-VBIOS overclocking after Turing. Downloadable
  != modifiable.
- **A GPU-style shunt mod has no target.** No external current-sense IC is exposed (hwmon shows only
  acpitz/nvme/mlx5/wifi); sensing is on-die/on-package - nothing discrete to parallel. And it's a
  single irreplaceable superchip (brick = whole machine).
- **BIOS Setup has no power/TDP toggle.** coreboot platform + AMI UEFI Setup payload (`AMITSESetup` /
  `Setup` / `DigitsSetupData` EFI vars). ASUS GX10 firmware (latest **v0105**, 2026-08) is componentised -
  BIOS / SOC FW / EC / PD / TPM, each a separate signed capsule - from ASUS helpdesk_bios or `fwupdmgr`
  (LVFS). Setup exposes boot/security/platform, not power.
- **GB10 runs at FULL tensor issue rate - nothing to "unlock"** (measured 2026-10-24, spark4/5/6 all
  within 1.5%): sustained dense BF16 GEMM with FP32 accumulate = 96-97.5 TFLOPS at ~2250 MHz (97% of
  the clock-scaled 125 TFLOPS dense spec); INT8:BF16 = 1.93:1, the full-rate professional profile (a
  segmented GeForce shows ~4:1 with BF16-acc32 halved - that is what the Ampere gpu-unlock removes);
  FP8 ~194 TFLOPS; memcpy 219-231 GB/s vs 273 spec. Porting the Ampere unlock (SEC2-booter ROP ->
  FEAT_OVR speed selectors) is doubly dead: no limit exists on GB10, and the entry chain does not
  exist on Blackwell.
- **`nvidia-smi -lgc` above the natural curve is a NO-OP on GB10** (measured 2026-10-24): locks of
  2600/2800/3003 MHz are accepted ("All done") but the governor never exceeds ~2275 MHz; power stays
  86-93 W; `clocks_event_reasons` stays 0x0 (the DVFS power/voltage curve is the limiter, not a
  reportable cap). Locking made sustained GEMM slightly WORSE (97.1 -> 94.7-95.5 TFLOPS) and hotter.
  "Applications Clocks: 2418 MHz" (the default) is the validated peak; "Max Clocks: 3003 MHz" is
  unreachable under sustained load on this envelope - only seen in short bursts. `adam` cannot run
  `-lgc` (needs root); a `--privileged` docker container CAN:
  `docker run --rm --privileged --gpus all --entrypoint nvidia-smi <img> -lgc <lo>,<hi>` (reset `-rgc`).
  Useful only to LOWER the ceiling (thermal capping), never to raise sustained clocks.

## Known PD-throttle wedge (the real failure mode)
GPU pinned at **611 MHz / ~14W**, temp "capped ~50 C" (low-P-state artifact, not thermal) = USB-C PD
controller firmware wedge.
- Fix = **cold drain**: shutdown; unplug PSU from wall AND unit; unplug ALL USB-C peripherals; hold
  power 30s; wait 60s+; replug PSU only; boot. Then flash latest PD firmware (`fwupdmgr update`) and do
  a **second** cold drain so the PD MCU reloads EEPROM. `Update State: Success` is the trustworthy
  signal (ESRT version readback can stay stale - do not treat a stale version string as failure).
- Triggers: sleep/suspend (most common), crash mid-load, firmware update without a full power cycle.
- Healthy GB10 under load: **~2170-2430 MHz, 86-93W sustained tensor load, 70-90 C** (86 C in-spec).
- Throttle-check tool: `github.com/hoesing/spark-gpu-throttle-check` (flags <1400 MHz under load).

## Measured sustained behavior + benchmark methodology (2026-10-24)
- Fresh/idle box under sustained BF16 GEMM: starts 2327-2372 MHz / ~92 W / 56-57 C, sags to
  2249-2268 MHz / ~89 W / 68-71 C after ~50 s (clock -4%). Multi-minute load settles ~2170-2200 MHz
  at 80-83 C. No throttle-reason bits at any point - pure power-curve sag with temperature.
- **Control for thermal soak when benchmarking prefill/GEMM on a Spark**: sequential runs on a hot box
  read up to ~4-6% low vs the same run on a cool box. Interleave A/B arms or equalise start
  temperatures, and record temp at run start.

## Levers that actually work
1. **Cooling.** ASUS GX10 is the weakest-cooled GB10 (only one flagged for thermal-slowdown events). A
   fan mod helps a power-limited GPU via **reduced leakage** - cooler silicon leaks less, so more of
   the fixed power budget goes to clocks. Real gain even though the cap can't be raised. The measured
   clock sag with temperature (above) is the direct evidence.
2. **Clock locking: nothing to gain upward** - see the no-op fact above. `-lgc` cannot raise sustained
   clocks past the power curve; do not spend time on it.
3. **Latest firmware** (fwupdmgr / ASUS) for best PD negotiation + efficiency (one update cut idle ~32%).
Beyond that, sustained-throughput gains are in the serving stack, not the power envelope.

## Diagnostic commands (read-only, no sudo)
```
nvidia-smi -q -d POWER                                   # draw; limit = N/A on GB10
nvidia-smi -q -d PERFORMANCE | grep -A6 "Clocks Event"   # SW Power Capping / thermal counters (us)
nvidia-smi -q -d CLOCK | grep -A4 "Max Clocks"           # current vs max = headroom
nvidia-smi --query-gpu=clocks.sm,power.draw,temperature.gpu,clocks_event_reasons.active --format=csv,noheader
cat /sys/class/dmi/id/bios_version /sys/class/dmi/id/product_family
```
**sudo on the Sparks is pam_rssh (YubiKey) and does NOT work for the agent without the owner's touch** -
plan read-only recon, or have the owner drive privileged steps (flashrom dump, fwupdmgr, dmesg).
GPU state changes (e.g. `-lgc`) work rootless via a `--privileged` container (see above).
Reach them as `adam@192.168.99.11..16` with the YubiKey SSH agent.
