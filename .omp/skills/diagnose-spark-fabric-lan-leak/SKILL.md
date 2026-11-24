---
name: diagnose-spark-fabric-lan-leak
description: "Use when UniFi/firewall logs show Spark fabric 10.0.x traffic blocked as \"Invalid Traffic\", or Sparks appear to talk over the wrong interface; not for actual RDMA throughput problems."
---

# Diagnose a Spark fabric-to-LAN traffic leak

Symptom: the UniFi (or other) firewall logs Spark `10.0.x.x` fabric traffic blocked as "Invalid
Traffic", or the Sparks look like they are meshing over the office LAN (`192.168.99.x`) instead of the
ConnectX rails.

## The critical trap first

**Do NOT trust Linux netdev byte counters (`/sys/class/net/<if>/statistics/*_bytes`) to judge whether
the fabric is used.** RDMA/RoCE bypasses the kernel netdev stack entirely, so those counters show
almost nothing for the rails even when they carry hundreds of TB. Reading them led to a wrong "the LAN
carries 30x the fabric" conclusion. The authoritative counter is the RoCE hardware one:

```
for dev in rocep1s0f0 rocep1s0f1 roceP2p1s0f0 roceP2p1s0f1; do
  p=/sys/class/infiniband/$dev/ports/1/counters
  echo "$dev rcv=$(cat $p/port_rcv_data) xmit=$(cat $p/port_xmit_data)"  # units are x4 bytes
done
```

Balanced, large values across all four = the RDMA data plane is healthy; the fabric is NOT the problem.

## Find what actually leaks

The data plane is fine, so the leak is control traffic. Find the destinations with no fabric route:

```
for d in 10.0.133.2 10.0.156.6 10.0.145.4 10.0.46.6; do ip route get $d; done
# "via 192.168.99.1 dev enP7s7" = falls to the LAN default gateway = leaks
```

Then find the service and port generating it:

```
ss -tnp | grep ':<port>' | grep -E '10\.0\.'   # SYN-SENT/SYN-RECV to far-fabric = failing cross-fabric attempts
```

## The usual culprit: mentatd (kindling spark-os cluster daemon, :6379)

`mentatd` on `:6379` is kindling's cluster coordinator. By default (no `MENTAT_ANNOUNCE_IFACES` in
`/etc/spark/node.env`) it announces EVERY up interface, including all RoCE rail IPs, to every mesh peer
that shares the cluster key. When two fabrics are not cabled together (e.g. a spark1-3 production ring
and a spark4-6 dev triangle both in one mesh), cross-fabric peers try unroutable rail IPs that leak to
the LAN gateway.

Confirm what a node announces:
```
curl -s http://127.0.0.1:6380/status | python3 -c 'import sys,json;print(json.load(sys.stdin).get("addrs"))'
```
If that list contains `10.0.x` addresses, that is the leak.

## The fix

Set LAN-only announce on every Spark, and PERSIST it (the live `/etc/spark` is the ephemeral RAM
overlay; the boot copy is on the host disk):

1. Append `MENTAT_ANNOUNCE_IFACES=enP7s7` to BOTH `/etc/spark/node.env` AND
   `/run/sparkos/host/etc/spark/node.env`.
2. `sudo systemctl restart mentatd` on each node. **Warning: on the rank-0 box this bounces the whole
   TP serve (~83s)** - the serve is supervised through mentatd and auto-reregisters cleanly.
3. Verify every node announces only `['192.168.99.1x']` and each peer's `addr_ifaces` shows no `10.0.x`.
4. Confirm `ss -tn | grep ':6379' | grep -cE '10\.0\.'` is 0.

The mesh is LAN-native (peers discovered by broadcast, keyed by LAN IP), so LAN-only announce is
complete; the rails still carry all RDMA.

## Fleet gotchas that bit during this

- Sudo on the Sparks is `pam_rssh`: use `ssh -A -tt` (agent forwarding + tty) and `sudo <cmd> </dev/null`.
  Missing `-A` gives "a terminal is required". The YubiKey agent being healthy (`ssh-add -l` lists the
  card) does NOT mean sudo works without `-A`.
- `sudo ... | <pipe>` and `echo x | sudo tee` break under pam_rssh (stdin conflict). Stage to a user temp
  file, then `sudo cp` it into place.
- Variables do not expand reliably through ssh->base64->heredoc layers: write the exact bytes to a local
  file, `base64 -w0` it, decode on the box, `sudo cp`. Verify by hash, not by trusting the write.
- Splitting cluster keys per fabric does NOT stop the leak: mentatd discovers and liveness-probes peers
  by broadcast regardless of key, so it still announces/probes fabric addresses. Only `MENTAT_ANNOUNCE_IFACES`
  stops it.
