---
name: build-gitea-issue-to-pr-agent
description: "The OTS \"label an issue - local-GLM aider fixes it - PR - review panel\" loop on Gitea. Covers the DEPLOYED org-wide webhook service (CT107, zero per-repo setup) and the per-repo Gitea Actions alternative, with all the gotchas. Use to operate/redeploy/extend it or add issue-fixing to a new setup."
---

## What this is

Add the label **`agent-fix`** to a Gitea issue -> [aider](https://aider.chat) driven by
**local GLM-5.3-Flash** (router model `local-glm`, thinking-OFF) investigates, makes a
minimal fix on `agent/issue-<n>`, opens a PR (`Closes #<n>`) and posts `/review` to fire
the pr-agent panel. Nothing auto-merges.

Two implementations. **B is DEPLOYED and is the primary one.**

## Fleet facts

- Gitea + Actions runner + pr-agent panel on **CT107** (`gitea.ots-int.net`, org `ots`).
  Runner label `ubuntu-latest` -> `catthehacker/ubuntu:act-latest`.
- LiteLLM router on **CT105** `http://10.20.0.105:4000`, model `local-glm` -> `spark1:8889`
  GLM, thinking forced off. Reachable from CT107 containers.
- Admin ops: `ssh root@proxmox.ots-int.net` (YubiKey) then `pct exec 107 ...`. Mint token:
  `docker exec -u git gitea gitea admin user generate-access-token --username Adam --token-name X --scopes all --raw`;
  REVOKE via DB: `docker exec -u git gitea sqlite3 /data/gitea/gitea.db "DELETE FROM access_token WHERE name LIKE 'X%'; SELECT changes();"`.
- Drive/poll from the harness with NON-interactive single-shot ssh (`ssh root@proxmox... "pct exec 107 -- ..."`);
  a long-lived PTY wedges under runner load. No `jq` on CT107 host - use `python3`.

## B. DEPLOYED: org-wide webhook service (zero per-repo setup)

Mirrors how the review panel works: subscribe once to org webhooks; every repo (incl.
future) is covered with NO per-repo files. Deployed on CT107:

- Docker service `agent-fix` at `/root/agent-fix` (Dockerfile + app.py + docker-compose.yml + .env),
  port **8620->3000**, `extra_hosts: gitea.ots-int.net:172.17.0.1`, `restart: unless-stopped`.
  Image `python:3.12-slim` + `pip install aider-chat flask requests gunicorn` + git.
  Run: `gunicorn -b 0.0.0.0:3000 -w 1 --threads 8 --timeout 0 app:app`.
- **Bot user `ots-agent-fixer`** (Gitea id 14) in **org team `fixer`** (id 3, `includes_all_repositories=true`,
  write) -> can push/PR on every org repo automatically. Its PAT (scopes `write:repository,write:issue`)
  is in `/root/agent-fix/.env`.
- **Org label `agent-fix`** (id 4) -> usable on any repo, no per-repo label creation.
- **Org webhook** (id 18) -> `http://172.17.0.1:8620/webhook`, events `issues`, HMAC secret.
- `.env`: GITEA_URL, GITEA_TOKEN(bot PAT), WEBHOOK_SECRET, OPENAI_API_BASE, OPENAI_API_KEY(router key),
  FIXER_MODEL=openai/local-glm, FIX_LABEL=agent-fix, BOT_USER=ots-agent-fixer. Secrets live ONLY here.

app.py = Flask: `/webhook` verifies HMAC (`X-Gitea-Signature` = hex HMAC-SHA256 of raw body),
logs event, and if `X-Gitea-Event in (issues,issue_label)` and `action==label_updated` and the
`agent-fix` label is present, spawns a daemon thread and returns 202. The worker clones with the
bot token in the URL (`https://ots-agent-fixer:<PAT>@gitea.ots-int.net/...`, `GIT_SSL_NO_VERIFY=1`),
runs aider with `OPENAI_API_BASE/OPENAI_API_KEY` + a `/tmp/meta.json` giving `openai/local-glm`
110k ctx and `HOME=<tmpdir>`, checks `git rev-list --count origin/<default>..HEAD`>0, pushes, opens
the PR via API, posts `/review`. Dedup: skips if an open PR for the branch already exists.

### Review -> revise loop (automatic, DEPLOYED)

The service also closes the loop: when the panel (or a human) comments/reviews an agent PR, the
fixer pulls that feedback and revises the same branch. Wiring:
- Org webhook subscribes to `issues,issue_comment,pull_request_review,pull_request_comment`.
- On an `issue_comment`/`pull_request_comment` where `issue.pull_request` is set (or a
  `pull_request_review`), by anyone EXCEPT the bot, on a branch `agent/issue-*`, the handler
  DEBOUNCES: a per-PR `threading.Timer(DEBOUNCE=150s)` is reset on each event, so the ~9 staggered
  panel comments collapse into ONE revise pass instead of nine.
- `worker_revise` (per-PR non-blocking lock so passes never overlap): counts the bot's `/review`
  comments as the round number; if > `CAP_ROUNDS` (3) it posts a "revision cap" note once and stops;
  else gathers all non-bot PR comments + reviews, `git clone --branch <agent branch>`, runs aider on
  the feedback, and if HEAD changed pushes + posts `/review` (which re-triggers the panel = next
  round); if aider made NO change it comments "no further changes were needed" and does NOT re-post
  `/review`, so the loop terminates naturally. `CAP_ROUNDS`/`DEBOUNCE_SECONDS` are env-tunable.
- Trigger model is AUTOMATIC (owner's call - local GLM is free); the cap + the no-change stop bound it.
- VERIFIED end-to-end: initial fix committed `fix: correct average denominator`; panel flagged an
  empty-list `ZeroDivisionError`; round 1 auto-committed `fix: guard average against empty list
  division` and re-requested review. So the bot actions reviewer improvements, not just the first fix.

### B gotchas (each cost a cycle)

1. **Org-label events don't populate `changes.added_labels`.** A repo label add fills
   `changes.added_labels[]`, but an ORG label add (label_updated) left it empty -> strict check
   silently ignored the event (no worker, no error). FIX: also accept the label via
   `issue.labels[]`. Dedup (open-PR-for-branch check) makes the looser trigger safe.
2. **`X-Gitea-Event` for label changes is `issues`** (action `label_updated`), but subscribe to
   both `issues` and `issue_label` to be safe.
3. **slim image has no `ps`** - can't check running procs that way; rely on in-app logging
   (print with `flush=True`; gunicorn shows worker stdout).
4. Webhook handler MUST return fast (202) and do aider work in a background thread, else Gitea
   times out the delivery.
5. Reach the router at the mesh IP `10.20.0.105:4000` and Gitea via the `172.17.0.1` extra_host,
   exactly like the pr-agent containers.

### Operate / redeploy B

- Logs: `pct exec 107 -- docker logs --tail 50 agent-fix` (worker lines are `[worker o/r#n] ...`).
- Redeploy after editing app.py: base64 the file over ssh into `/root/agent-fix/app.py`, then
  `cd /root/agent-fix && docker compose build && docker compose up -d`.
- Health: `curl http://127.0.0.1:8620/healthz` inside CT107.
- Full teardown is in CT107 `/root/INVENTORY.md` (container+image+dir, bot user, team 3, label 4, hook 18).

### Panel access: org-wide via read-only team (DONE)

The pr-agent review bots (`ots-rev-*`) need repo access or `/review` 404s ("Failed to get git
provider"). This is now granted org-wide by team `reviewers` (id 4, `includes_all_repositories=true`,
units code/issues/pulls = **read**), containing all `ots-rev-*` bots + `ots-reviewer`. So `/review`
works on every repo incl. future ones with NO per-repo collaborator adds. The owner OK'd broad access
(the panel models are deliberately no-train).

VERIFIED: read is sufficient - with the team at read-only, the bots posted both "PR Reviewer Guide"
reviews AND "PR Code Suggestions" (bot log: `Comment published`, no 403/404). Reviewers never need
write; only the fixer bot (`ots-agent-fixer`, team `fixer`) needs write, to push its branch.

GOTCHA: creating a team via API with a `units_map` sets the base `permission` field to `none` (real
access comes from `units_map`), and `GET /repos/{o}/{r}/collaborators/{u}/permission` reports only the
base field - so it shows `none` even when unit-level team access is live. Verify access by an actual
action (or `GET /teams/{id}/repos`), not that endpoint.

## A. Alternative: per-repo Gitea Actions workflow

Use when you want it scoped to specific repos with no extra service. Needs, per repo: the workflow
file below on the default branch, the org secret `ROUTER_API_KEY`, and the `agent-fix` label (org
label works). Gotchas: Gitea's Actions label event is `action==label_updated` with the label in
`github.event.changes.added_labels[]` (gate with a python step reading `$GITHUB_EVENT_PATH`, NOT
`github.event.label`); the runner image Python is PEP-668 externally-managed so install aider in a
**venv** (never `pip install --upgrade pip`; fallback `pip install --break-system-packages --ignore-installed`);
Gitea action logs are `.zst` under `/data/gitea/actions_log/<o>/<r>/a<N>/<taskid>.log.zst` (docker cp
out, `apt-get install -y zstd` to read then purge).

```yaml
name: agent-fix
on:
  issues:
    types: [labeled]
jobs:
  gate:
    if: ${{ github.event.action == 'label_updated' }}
    runs-on: ubuntu-latest
    outputs:
      go: ${{ steps.g.outputs.go }}
    steps:
      - id: g
        run: |
          GO=$(python3 - <<'PY'
          import json, os
          e = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
          added = (e.get("changes") or {}).get("added_labels") or []
          labs  = (e.get("issue") or {}).get("labels") or []
          hit = any((l or {}).get("name")=="agent-fix" for l in added+labs)
          print("1" if hit else "0")
          PY
          )
          echo "go=$GO" >> "$GITHUB_OUTPUT"
  fix:
    needs: gate
    if: ${{ needs.gate.outputs.go == '1' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Install aider
        run: |
          if python3 -m venv /tmp/av 2>/dev/null && /tmp/av/bin/pip install --quiet aider-chat; then
            echo "/tmp/av/bin" >> "$GITHUB_PATH"; /tmp/av/bin/aider --version
          else
            python3 -m pip install --break-system-packages --ignore-installed --quiet aider-chat; aider --version
          fi
      - name: Model metadata
        run: |
          echo '{"openai/local-glm":{"max_input_tokens":110000,"max_output_tokens":8192,"litellm_provider":"openai","mode":"chat"}}' > /tmp/aider.metadata.json
      - name: Branch
        run: |
          git config user.name ots-agent-fixer; git config user.email ots-agent-fixer@ots-int.net
          BRANCH="agent/issue-${{ github.event.issue.number }}"; git switch -c "$BRANCH"; echo "BRANCH=$BRANCH" >> "$GITHUB_ENV"
      - name: aider
        env:
          OPENAI_API_BASE: http://10.20.0.105:4000
          OPENAI_API_KEY: ${{ secrets.ROUTER_API_KEY }}
          ISSUE_TITLE: ${{ github.event.issue.title }}
          ISSUE_BODY: ${{ github.event.issue.body }}
        run: |
          aider --model openai/local-glm --model-metadata-file /tmp/aider.metadata.json \
            --no-show-model-warnings --yes-always --auto-commits --no-attribute-author \
            --no-attribute-committer --message "Fix bug #${{ github.event.issue.number }}: ${ISSUE_TITLE}

          ${ISSUE_BODY}"
      - name: PR + review
        env: { GT: "${{ github.token }}", T: "${{ github.event.issue.title }}", N: "${{ github.event.issue.number }}", B: "${{ github.event.repository.default_branch }}" }
        run: |
          [ "$(git rev-list --count origin/$B..HEAD)" -eq 0 ] && exit 0
          git push origin "$BRANCH"
          A="${{ github.server_url }}/api/v1/repos/${{ github.repository }}"
          python3 - <<'PY' > /tmp/pr.json
          import json,os
          n=os.environ["N"];print(json.dumps({"head":os.environ["BRANCH"],"base":os.environ["B"],"title":"Fix #%s: %s"%(n,os.environ["T"]),"body":"Automated fix. Closes #%s"%n}))
          PY
          P=$(curl -sk -X POST "$A/pulls" -H "Authorization: token $GT" -H "Content-Type: application/json" --data-binary @/tmp/pr.json | python3 -c "import sys,json;print(json.load(sys.stdin).get('number',''))")
          curl -sk -X POST "$A/issues/$P/comments" -H "Authorization: token $GT" -H "Content-Type: application/json" -d '{"body":"/review"}'
```
