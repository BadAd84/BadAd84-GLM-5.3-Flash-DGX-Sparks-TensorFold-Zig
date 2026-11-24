---
name: diagnose-a-carveout-nodae-mon-from-a-blank-env-value
description: "Use when a TensorFold/GB10 serve dies with display-carveout NoDaemon while dispramd is live: test the socket from inside the serve image, then check the env for blank assignments that shadow engine defaults"
---

# NoDaemon with a live daemon: suspect the env, not the daemon

A serve that reports `display carveout of N MiB from the daemon at /run/dispram/dispram.sock: NoDaemon` can have a perfectly healthy daemon. In the carveout client, `NoDaemon` comes from `connect()`; an empty socket path or an unreachable one both land there, and so does a path that the container cannot see.

## Order of checks (cheapest first, each measured)

1. **Is the daemon alive, and has it lent recently?** `systemctl is-active dispramd` and `journalctl -u dispramd -n 20`. Lines like `lent 0x... + 2046 MiB` prove it works and takes clients.
2. **Is the socket visible inside the serve image?** `docker run --rm -v /run/dispram:/run/dispram IMAGE ls -l /run/dispram`. A missing mount is a launcher question (the mount is usually added only when the carveout switch is set in the env file the launcher reads).
3. **Does a raw connect succeed, and with which socket type?** From inside the image:
   `python3 -c "import socket;s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET);s.connect('/run/dispram/dispram.sock');print('ok')"`
   The daemon takes `SOCK_SEQPACKET` and refuses `SOCK_STREAM` with `EPROTOTYPE`; that refusal is correct behaviour, not a fault.
4. **Read the env the launcher will actually pass.** `grep -n CARVEOUT <env-file>`. A line `TF_CUDA_CARVEOUT_SOCKET=` is the usual culprit: an empty assignment is a value (`""`), not absence, so the client dials a zero-length path and `connect()` fails with `NoDaemon` while the engine's default `/run/dispram/dispram.sock` never applies.

## The fix

Do not patch the one variable. A complete env generator must distinguish three states:

- **set** to a value (write `NAME=value`);
- **absent** because no value is the decision (write a comment such as `# absent NAME=` and record an `absent` verdict in the settings register, and do NOT emit `NAME=`);
- **computed by the launcher** (leave it out of the env and let the launcher pass it).

Then re-run the generator and gate, and prove it with one boot that reaches serving. Aim the same rule at every path, key, socket and optional-string setting, because they share the failure: a reader that takes the string as a path sees `""` and fails at a stage far from the variable's name.

## The diagnostic generalisation

When a client reports "no daemon/no service" while the service demonstrably works, the difference is in what the client used (path, key, socket type, namespace) rather than the service. Prove the service from the client's own container before changing anything on the host.
