---
name: easylens
description: Build, inspect, publish, and push Snapchat camera and Web Lenses with the `easylens` CLI. Use when the user asks to create/build/iterate-on/publish a lens or effect, wants to browse lens blocks, generators, or asset collections, or wants a lens pushed to their phone.
---

# EasyLens CLI

`easylens` drives the EasyLens backend: the whole lens-authoring surface — blocks,
generators, and asset collections; recipe authoring and validation; builds and iteration;
plus publish status, deletion, and a live event stream. You bring the model; the CLI is
the transport.

Scope is building and publishing lenses. There are no feed/discovery commands.

## Choose the installed command

The examples use `easylens` as shorthand for the installed executable.
For a standalone download, use its full path, such as `./easylens/easylens` or `.\easylens\easylens.exe`.
Keep the executable beside its bundled libraries. Standalone builds need neither Node nor Python.
If the user runs an npm package, use the package launcher they selected instead.
Use the same executable for sign-in, guide installation, validation, and builds.
Do not replace a standalone binary with an npm command or install a different distribution during a task.

## Choose the build workflow

Use Web Lenses for every use case that does not involve the camera, including games, tools, and interactive experiences.
Read `easylens docs web-lenses` before building the local HTML, CSS, and JavaScript project.
If the experience involves the camera, use a recipe-based Lens instead. Do not use a Web Lens.
Camera use includes displaying or processing live camera input, face or body tracking, and effects on the camera view.
For camera experiences, follow the recipe workflow below and read `easylens docs recipe-spec`.

## Publication requires explicit authorization

Building, creating, fixing, or testing a lens does not authorize publishing it.
Finish the build and validation, show the result, and stop unless the user explicitly requests or approves publication of that lens.
Hidden publication and publishing into a folder require the same authorization.
Design approval, authentication, and a request to push to a phone do not authorize publication.
Existing explicit authorization for that submission is sufficient; do not ask for it again.

For Web Lenses, `lens upload --zip` saves a draft and `lens push` sends it to Snapchat without publishing.
Only `lens publish --conversation ID` submits publication.
For a local build request, deliver the tested project and ZIP, with any requested icon or preview.
For a draft update or device-test request, complete that workflow without requiring publication approval.

## Finish each iteration in EasyLens

When the user asks to keep a Web Lens draft updated, finish each implementation cycle with a saved EasyLens revision.
Complete the edits, local tests, and visual review first.
Run `easylens lens upload --zip ./web-lens.zip --conversation "$CONV" --json` to replace the draft ZIP without publishing.
For a recipe lens, build the revision in the same conversation with the supported CLI command.
Reuse assets where possible, wait for completion, and report the returned conversation and checkpoint IDs.
A local ZIP alone does not complete a requested EasyLens update.

Authorization to keep the draft updated continues across iterations in that task.
It does not authorize creating replacement lenses or publishing the draft.
A published Web Lens takes a ZIP revision in its conversation, and `lens publish --conversation ID --name NAME --republish` sends it as the Lens's next version.
`lens publish --conversation ID --republish` submits the saved Lens, not edited local files.
If the server rejects an update, preserve the local package and report the reason.
Do not create a replacement Lens or publish old content to claim success.
Run `easylens docs web-lenses` for the upload, revision, retry, device-test, and publication workflows.

## Contract you can rely on

- **Piped output is JSON.** `easylens blocks list` in a terminal prints a table; the same
  command piped or captured emits JSON. Never parse the table — capture stdout.
- **stdout is data, stderr is progress.** `easylens lens get $CP > lens.json` is always a
  clean capture.
- **Exit codes are meaningful.** Branch on them instead of scraping text:

  | code | meaning |
  |---|---|
  | 0 | success |
  | 1 | recipe validation failed, or an unexpected error |
  | 2 | bad arguments, or Lens build preflight rejected the recipe |
  | 3 | auth problem — tell the user to run `easylens auth login` |
  | 4 | not found (bad id, or you lack access) |
  | 5 | the lens build failed, or a watch timed out |
  | 6 | rate limited — back off |
  | 7 | upstream/server error — retry later |

- **`--help` is authoritative.** `easylens <group> <action> --help` documents every flag.

## Load this guide

After `easylens agent init`, start a new agent session to load the installed guide.
Guide installation never overwrites an existing destination, including `AGENTS.md` or a symlink, even with `--force`.
Folder symlinks are allowed. If the guide file already exists, use `easylens agent print` without writing a file.
For the current session, run `easylens agent print` and read its output directly.
CLI upgrades do not update installed guide files.
If an older guide stops on `expired: true`, replace its auth section with the "First: check auth" section below.
Do not assume that installing a skill makes its slash command available in an existing session.

## Reserve the sign-in port

Reserve `127.0.0.1:8766` for EasyLens sign-in.
Do not use port `8766` for preview servers or development tools.
Use another port, such as `8000`, and check that it is available before starting a server.
If another application uses port `8766`, ask the user to move or stop it before signing in.
Do not stop another application automatically.

## First: check auth

```bash
easylens auth status --check --no-browser --json
```

This command tests API access and renews expired access tokens when a refresh token is available.
`--no-browser` prevents interactive sign-in but allows automatic renewal.
If the command exits `0`, continue with the task, even if `expired` is true.
`state: "expired_renewable"` means that a refresh token is stored.
The expiry fields describe the token before the API checks, so they can remain stale after successful renewal.

If `signed_in` is false, or renewal fails because the refresh token is missing or rejected, stop and ask the user to run
`easylens auth login` themselves. Interactive sign-in opens a browser and needs a human at the keyboard.
Do not start browser sign-in from an agent session.
If an API check fails, read its detail before requesting sign-in.
Network errors, rate limits, server errors, and API access restrictions do not prove that the login expired.
Report these errors without requesting sign-in. Do not retry in a loop.

## Build a camera Lens: edit the recipe directly

**You are a coding agent — author and edit the recipe yourself.** The CLI has no
server-side chat agent; it is transport for recipes you compose. Direct editing is one
deterministic pass: fetch → edit → validate → build.

```bash
# 1. See what exists
easylens blocks list --json
easylens blocks info "Face Mask" "Background Image" --json
easylens generators list --json

# 2. Read the recipe format before writing one — it is the source of truth
easylens docs recipe-spec
easylens docs coding-instructions   # REQUIRED before writing controller JS

# 3. Write (or edit) recipe.json, then validate it (catches silent-drop mistakes)
easylens recipe validate recipe.json --online

# 4. Build and follow it to completion
easylens lens build recipe.json --watch --json
```

`lens build` validates first and refuses to build on errors (`--force` overrides).

## Generate a face effect

Long generation creates preview samples, then trains and assembles a Lens after explicit approval.
Use this path for a supported FaceGen provider.
Do not put a long-generation provider in an ordinary Lens recipe or increase the ordinary build timeout to start training.

```bash
easylens generators list --long-generation --json
easylens conversation new --json
easylens generation preview --conversation CONVERSATION_ID \
  --generator "Face Enhanced ML Effect" --prompt "Give my face soft blue star face paint" --watch --json
easylens generation previews CONVERSATION_ID --generation-id GENERATION_ID --dir ./previews --json
```

Use the catalog's available provider name and parameter schema.
The first release supports FaceGen providers only.
Pass other documented parameters as a JSON object with `--parameters FILE`.
Use the conversation UUID returned by `conversation new` and the `generation_id` returned by preview submission.
Show the preview images to the user before training unless the user already authorized that step.

```bash
easylens generation train CONVERSATION_ID --generation-id GENERATION_ID --json
easylens generation watch CONVERSATION_ID --generation-id GENERATION_ID --until lens --wait-timeout 14400 --json
```

Training can take hours.
Commands return after acceptance unless `--watch` or `--wait` is set.
`generation watch` stops at `PREVIEW_READY` by default and never approves training.
Use `--until lens` after training approval.
Success requires `stage: "SUCCEEDED"` and a checkpoint ID, not merely an accepted action or completed preview.
Continue with existing `lens get`, `lens download`, `lens render`, `lens push`, and `lens publish` commands.

If waiting times out, retain the handle and use the returned `watch_command`.
Stopping the CLI does not cancel generation.
Exit code 5 with `timed_out: true` means that waiting stopped, not that the server failed.
`approval_required: true` means that preview review and an explicit `generation train` command remain necessary.
`FAILED` and `CANCELLED` are terminal failure stages.

If submission fails after dispatch, its receipt still contains the action ID, original expected version, and status command.
Read that status before retrying.
Retry identical inputs with `--action-id` and the original `--expected-version` together.
For a training retry, preserve its separate training action ID and the original preview `generation_id`.
Do not start a new generation to recover from a network error or watch timeout.

## Recipe rules that bite

The backend applies a recipe **verbatim** — no normalisation. These mistakes build
"successfully" while silently producing nothing:

1. **Collection generators need embedded `urls`.** If `easylens generators list "<name>"`
   shows `type: Asset Collection`, a `prompt` alone is ignored and the asset is dropped.
   Search first and embed the result:
   ```bash
   easylens collections search "Particles" "sparkles" --recipe-snippet
   ```
   That prints a paste-ready `asset_providers` entry with `urls`/`outputs` split correctly.
2. **Wire every asset-bearing input explicitly.** Never leave a texture/glb/splat input
   empty hoping it resolves:
   `{"type": "asset_provider", "value": {"id": "gen_background", "output_idx": 0}}`.
3. **Iterating? Reuse assets.** Pass `--parent-checkpoint <id> --from-cache` so unchanged
   generators don't re-run.
4. **Never trust `checkpoint_id` as "done".** It is assigned at kickoff. Completion is
   `asset_statuses.lens.status == "SUCCESS"`; `"ERROR"` means stop. `--watch` handles this.

## Generator prompts: no IP content

Every generator prompt is checked for intellectual property before the generator runs. A prompt
that asks for a brand, a logo, a licensed character, or other protected content is rejected.
Do not ask a generator for things like "a Spider-Man t-shirt" or "a Nike logo". Some generators
also take an image (`upload_uid`); the prompt that goes with it is checked the same way.

## Using the user's own files

```bash
easylens conversation new --json                       # get a conversation_id
easylens upload ./cat.png --conversation $CONV --json  # upload + bind, one step
```

The returned `filename` is what you reference in the recipe. It is a canonical server
name (e.g. `user_asset_1.png`) that differs from your local filename — and it is the
only valid reference:

```json
{"type": "user_provided_asset", "value": {"id": "user_asset_1.png", "type": "texture"}}
```

Or pass it to a generator as `"upload_uid": "user_asset_1.png"` when you want the
generator to produce something *from* the file.

## Upload and revise a local Web Lens

Use this workflow for experiences that do not involve the camera.
For a build-only request, deliver the tested local artifacts.
Upload or push when requested; publication requires explicit authorization.

Read `easylens docs web-lenses` before writing a Web Lens.
It provides a minimal static project, runtime rules, ZIP structure, and publication requirements.
The guide is bundled with the CLI and needs no network access or sign-in.
Use standard web tooling to build and test the project. Recipe commands do not build or validate Web Lens ZIPs.

Use `easylens lens open --conversation ID` to open its page, or add `--no-browser` to print the URL.
Web Lenses have no recipe. Use `lens get` without `--recipe` to read their metadata.

```bash
easylens lens upload --zip ./web-lens.zip --icon ./icon.png --preview ./preview.mp4 --name "My Web Lens" --json
# Set CONV to the returned conversation_id. Edit locally and rebuild the ZIP.
easylens lens upload --zip ./web-lens.zip --conversation "$CONV" --json
easylens lens publish --conversation "$CONV" --name "My Web Lens" --wait --json
```

Push a local ZIP before publication:

```bash
easylens lens push --zip ./web-lens.zip --name "My Web Lens" --json
# Set CONV to the returned conversation_id. Push later edits into the same draft.
easylens lens push --zip ./web-lens.zip --conversation "$CONV" --json
easylens lens push --conversation "$CONV" --json
```

Push reuses upload preparation and the existing device API. It never submits publication.
An icon is optional. No preview video is required for device testing.
Each push requires an explicit command. Active builds wait up to 900 seconds, configurable with `--wait-timeout SECS`.
A failed build or timeout sends no Lens. Open Snapchat on the same account as the CLI.
Success confirms backend acceptance, not that the Lens opened on the phone.
Supply missing publication media later with `lens publish --conversation ID --preview FILE --icon FILE --name NAME`.
The backend returns `publish_request` only when a publication preview exists. Upload never submits it.

Upload saves without publishing. Revisions keep the same conversation and any omitted icon or preview.
The first upload requires a name and ZIP with `index.html` at its root. A PNG or JPEG icon and MP4 preview are optional.
A published Web Lens takes another upload, which `lens publish --republish` then sends as its next version. Use publication settings such as `--tags` and `--hidden` on the publish command.
Replace the old `lens publish --zip` syntax with the separate upload and publish commands above.

The upload prints an action ID. Revisions also print the expected conversation version.
Retry identical inputs with `--action-id ID`; revision retries also require the original `--expected-version N`.
Use a new action ID for intentional edits or after terminal failure. Concurrent edits or publication reject stale revisions.
`--prepare-timeout` limits waiting without cancelling preparation. JSON returns operation, conversation, checkpoint, and action IDs.
You can continue native CLI Lens conversations in the web app.
Uploaded Web Lenses require the CLI for editing.
Drafts without a saved preview URL need `--preview FILE` at publication.

## Shipping a lens

```bash
easylens lens push --conversation $CONV                     # to the user's Snapchat app
easylens lens publish --conversation $CONV --name "Neon Cat" --wait --json
easylens lens download $CP --dir ./out --icon               # verified .lns + icon
easylens lens render $CP -o preview.mp4                     # server-side MP4
```

Native publication automatically reuses the checkpoint's server-rendered preview or renders one when needed.
You do not need to download the MP4 and upload it again.
Use `--preview FILE` only for a custom video, or `--icon FILE` for a custom icon.
Web Lenses use a preview recorded in the editor and do not support native rendering.
The preview must be a complete vertical 9:16 MP4 with H.264 video, at most 32 MiB. The icon must be PNG or JPEG.
The server prepares a round 320×320 RGBA PNG icon with transparent corners and the publication ring.
Use `easylens lens icon input.jpg -o icon.png` to inspect a prepared icon locally.
Invalid previews return the problem and required format. The CLI does not convert videos.
These flags also work with `--republish`.

`--story my_story` or `--story spotlight` also posts the preview to a Story. Repeat it for both.
Add `--story` only when the user asks for a Story post.
Where Story posting is off, a Web Lens publish fails with `story_unsupported_for_web_lens`: publish again without `--story`.
`easylens lens status $CP --json` lists each destination's result under `story_posts`.
A Web Lens publishes as `LensStudioWeb` unless `--source-application` says otherwise.
`easylens lens download --conversation $CONV` saves a Web Lens as its verified `.zip`.
Before publishing, `easylens lens requirements $CP --json` lists what the publish requires,
and `easylens lens quotas --json` shows the submissions left in each pool.
A required phone verification does not apply once the user's phone is verified.
A null pool is not enforced, not zero. Never add the two pools together.

`publish --wait` polls until the lens is live and resolves the integer
`unlockable_lens_id` used by `snapchat://unlock/?lensId=…` deeplinks. Without `--wait`,
that id is not yet assigned — read it later from `easylens lens list --json`.

To list a lens group, use `easylens lens list --filter payouts --json`.
The filters are `published`, `in_review`, `submitted`, and `payouts`.
The API filters before pagination. Do not fetch all pages to filter them locally.
`submitted` includes published and in-review lenses. `payouts` covers the 2,000 most recent lenses.
Use `--page` and `--page-size` to request a page from that group. Omit `--filter` to include drafts.

The wait ends after 900 seconds by default. Set `--wait-timeout SECS` to change that limit.
Status messages appear on changes and every 30 seconds after a successful poll.
A repeated `processing` status confirms a server response, not progress. The API does not expose a detailed publish stage.
On timeout, JSON includes `timed_out: true`, `waited_seconds`, and `status_command`; the command exits with code 5.
Publishing continues on the server. Run the returned `status_command` to check again.
Do not submit the lens again while it is pending.

## Iterating on something that exists (the direct-edit loop)

`recipe validate` checks structure locally by default. Use `--online` for catalog checks.
Online `recipe validate --online` and the preflight check in `lens build` check the recipe with EasyLens.
Recipe validation errors return exit code 1. Build preflight errors return exit code 2. Warnings permit a build unless validation uses `--strict`.
HTTP failures stop online validation. Use `recipe validate --offline` for local structure checks.
If online validation is unavailable, report the error. Offline structure checks do not establish that a build will succeed.
Online validation uses `POST /api/v1/cli/recipe/resolve`. Report an unavailable route as an API limitation.

To obtain catalog IDs for local Lens Studio assembly, run:

```bash
easylens blocks info "Background Image" --catalog-client Desktop
easylens generators list "Background Image" --catalog-client Desktop
easylens recipe resolve recipe.json --catalog-client Desktop -o resolved.json
```

Use the same client on discovery and resolution calls. The default client is `Web`.
Resolution creates no build or draft. It returns an enriched recipe only when validation succeeds.
On failure, it returns exit code 1 and leaves the output file untouched.
Controller compilation, asset generation, and local assembly remain separate steps.

```bash
easylens lens get $CHECKPOINT_ID --recipe > recipe.json   # the parent recipe, on disk
CONV=$(easylens lens get $CHECKPOINT_ID --json | jq -r .conversation_id)
# edit recipe.json (see the round-trip rules below), then:
easylens recipe validate recipe.json --online
easylens lens build recipe.json --conversation $CONV \
  --parent-checkpoint $CHECKPOINT_ID --from-cache --watch --json
```

- **Fetch the recipe by checkpoint id, not conversation.** Only checkpoint-addressed
  `lens get` returns the recipe (and it includes the full controller code).
- **Reuse the lens's own conversation** for iteration builds — uploaded files
  (`user_provided_asset`) are bound per-conversation, so building in a fresh conversation
  silently orphans them.
- `--parent-checkpoint` ties the build to the lens you're iterating on; `--from-cache`
  means unchanged generators don't re-run.

**Round-trip normalisation (will bite you):** a fetched recipe comes back in the
backend's *enriched* dialect, which the input schema does not accept verbatim. Before
resubmitting: rename input types `boolean`→`bool`, `float`→`number`, `vec4`→`color`, and
drop the `_upa_providers` key. `easylens recipe validate` surfaces the type renames and
the leftover key as *warnings* — they don't block the build, so read the findings, not
just the exit code. Run it after every edit, not just the first. A fetched recipe also
carries metainfo fields the server sets itself after a build; `lens build` removes them
before sending and says which, and `recipe validate` names them.

**Recovering a stuck conversation:** if builds in a conversation keep failing at lens
load (e.g. `LensExecutionError` before the first frame) and edits don't fix it, branch a
fresh conversation from the last good checkpoint and continue there:

```bash
easylens conversation new --from-checkpoint $GOOD_CHECKPOINT --json
```

## Writing controller code

- **Read `easylens docs coding-instructions` first, every time.** The runtime is not
  standard JS: no `setTimeout` (use `DelayedCallbackEvent`), custom vector types, only
  three creatable event types.
- **Syntax-check before building** — a parse error costs a full build round-trip:
  `node --check controller.js`.
- **There is no canvas font API.** `canvas.textFont(...)` does not exist; calling it (or
  any invented font-selection API) kills the lens at load with `LensExecutionError` and
  zero rendered frames. Custom fonts are wired at the *recipe* level, on blocks that
  declare a `font` input — e.g. `Text On Screen`'s `customFont`:
  ```json
  {"type": "user_provided_asset", "value": {"id": "user_asset_1.ttf", "type": "font"}}
  ```
  (upload the `.ttf` with `easylens upload` first). Canvas-drawn text always uses the
  default font.
- **Never invent an API.** If a call isn't in `coding-instructions` or the block's
  `script_properties`/`events` from `blocks info`, it does not exist. A wrong call
  usually surfaces as a startup `LensExecutionError` with no useful stack.
- Blocks are reached from the controller as `script.<scriptName>.<property>` — the
  `scriptName` is the block's key in the recipe's `blocks` dict, and the recipe must
  actually declare that block or the reference is `undefined` at runtime.

## Watching progress in real time

```bash
easylens conversation follow $CONV --json    # newline-delimited JSON events, one per line
```

Better than polling when you want build progress as it happens.

## How publish behaves

`lens publish` is asynchronous: the command returns as soon as the server accepts the
request, and progress arrives through `conversation follow`. The CLI handles the
concurrency and retry bookkeeping itself; a retry you start is a new request, never a
replay of an earlier one. If a command reports that an action isn't allowed in the
conversation's current state, read the state name in the error — the server owns that
decision.

## Command help

Never guess at a flag:
`easylens <group> <action> --help` lists exactly what exists, and every argument there
carries help text. If a flag isn't in `--help`, it isn't real — don't suggest it to the user.

## Read insights, stats, payouts, and Lens+ rankings

These commands only read data. Personal stats and earnings require sign-in and backend access to the account or lens. Public leaderboard commands do not require sign-in.

```bash
easylens profile stats --json
easylens lens insights LENS --range 28d --json
easylens lens stats LENS --json
easylens lens lens-plus-stats LENS --json
easylens payouts status --json
easylens payouts terms --json
easylens payouts earnings --start 2026-09-01 --end 2026-09-30 --json
easylens payouts earnings --start 2026-09-01 --end 2026-09-30 --lens 12345 --json
easylens leaderboard metadata --json
easylens leaderboard lenses --tab top_overall --month 2026-09 --json
easylens leaderboard creators --metric debut --month 2026-09 --json
easylens leaderboard recent --board trending --json
easylens leaderboard categories --json
easylens leaderboard category --category MCAT_2 --json
```

Replace `LENS` with an owned numeric lens ID or checkpoint UUID. `--lens` for earnings accepts only the numeric lens ID. Dates use UTC; a date without a time means midnight. Provide the intended payout period explicitly. Enrollment and terms acceptance remain server requirements; these commands do not enroll you or accept terms.

Insights support `7d`, `28d` (default), `60d`, `90d`, and `lifetime`. Use the returned date bounds. Lifetime totals cover all time, but daily series cover the last 90 days. Do not sum daily values to recreate totals. `null` means unavailable, not zero. Account reach is unique viewers. `longPlayRatio` is a raw 0–1 ratio.

JSON preserves all backend fields and units, including payout amounts in milli-USD (1,000 milli-USD = 1 USD). Human output shows earnings in USD. Lens+ payout score is not a dollar amount.

Run `leaderboard metadata` for available months. Lens tabs are `top_overall` and `new_this_month`. Creator metrics are `debut`, `hit_rate`, and `improved`; `--month` applies only to `debut`. Recent boards are `trending` and `rolling_30`. Preserve each chart's label, caveat, and date when reporting results. Rankings do not reveal other creators' earnings. An unavailable chart is not an empty ranking; report the API error and retry later.

## Reporting back to the user

Share `ui_url` as soon as a build starts — the page shows live progress, so the user does
not have to wait on you. When a build fails, read `asset_statuses.lens.reason` and say
which generator or block failed rather than just "it failed".
