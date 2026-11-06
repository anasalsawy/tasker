# Browser Automation — operator-grade reference for driving browsers programmatically

Scope: picking a backend, targeting without brittleness, waiting on state instead of time, surviving walls (login / captcha / 2FA), session persistence, iframe and shadow-DOM limits per harness, dialogs and popups, downloads, the native Save-As path, cookie banners, verify-after-action loops, form-filling traps, file inputs, automation detection, concurrency lanes, and the screenshot trap. Each section states the decision first, then the idiom.

## 1. Choosing the backend per task

| Task shape | Best layer | Why |
|---|---|---|
| Structured interaction where targets are real DOM nodes | **Playwright** (or Puppeteer) | Actionability auto-wait, role/text locators, frames, downloads, isolated contexts, tracing built in. |
| A capability the locator API lacks: raw input events, device metrics, profiling, target/session management, `Page.printToPDF`, `Browser.grantPermissions`, attaching to an already-running Chrome | **CDP directly** | You make the exact domain call. Cost: you write all the waiting and error handling yourself. |
| The user's own open browser — real profile, extensions, existing logins | **CDP attach** (launch with `--remote-debugging-port=9222`, then `connect_over_cdp`) | You cannot zero-state someone's profile. Operate in place, touch only the tab you were given, never close other tabs. |
| Cross-browser incl. Safari/Firefox, long-lived suites, locked-down enterprise stacks | **Selenium / WebDriver** | Standardised W3C protocol; Playwright cannot drive Safari on Windows. Cost: no web-first auto-wait, weaker download/print control, you own the flake. |
| The UI is a canvas / WebGL scene (maps, Figma, sheets, games) | **Vision + coordinate injection** via CDP `Input.dispatch*`, i.e. the desktop model | There is no selector to write. DOM targeting is dead on arrival. |
| Export a page as a real document | `Page.printToPDF` (Chromium, headless-capable) | Honours `@page`, `preferCSSPageSize`, headers/footers, vector text. Stitched screenshots lose the text layer and scale badly. |
| Static content at volume | No browser: `curl` + parser | A browser costs 10–1000× a plain GET. Use one only when JS execution is genuinely required. |

Rule: **locator API first, CDP when the API lacks the capability, screenshots last.**

## 2. Selector discipline: user-facing names beat structure

Target what the *human sees*. Visible names are contractual with users; generated class names are build artifacts that churn.

Preference order, most robust first:
1. Role + accessible name: `page.get_by_role("button", name="Save changes")`, `get_by_role("dialog").get_by_role("textbox", name="Quantity")`.
2. Visible text: `page.get_by_text("Order #1", exact=False)`, CSS pseudo `:text("Sign in")`.
3. Stable test hooks: `[data-testid=checkout-total]` — ask the app authors for these when possible.
4. Label / placeholder association: `get_by_label("Password")`, `get_by_placeholder("Search…")`, `get_by_alt_text`, `get_by_title`.
5. Semantic attribute predicates: `[aria-expanded=true]`, `[href^="/orders/"]`, `input[name=qty]`.
6. Structural CSS only as a last resort, and then **anchored to a named landmark**: `dialog:has-text("Filters") >> button:has-text("Apply")`.

Anti-patterns that survive until the first redesign:
- `.btn.btn-primary:nth-of-type(2)`; XPath full paths `/html/body/div[3]/div/span[1]`; anything containing framework hashes (`.css-1x2y3z`) or auto-numbered ids (`id="react-aria-39481"` changes every render).
- `.first()` used to silence a strict-mode multi-match. The error is *information*: scope to the enclosing `dialog` / `row` / `listitem`. Grabbing an arbitrary match is the classic "deleted the wrong customer" bug.
- A frame-internal locator written from the top document — see §6.

## 3. Wait for STATE, never sleep

A fixed `sleep(n)` is simultaneously too short (flake) and too long (wasted turns). Poll a named condition.

Conditions in order of preference:
- **Actionability**: attached + visible + stable (bounding box unchanged across consecutive frames) + enabled + not covered + receives pointer events. Playwright enforces this before each action; Selenium and raw CDP do not, so you implement it.
- **The specific network response** carrying the data, then the DOM consequence:

```python
with page.expect_response(lambda r: "/api/orders" in r.url and r.status == 200) as info:
    page.get_by_role("button", name="Load more").click()
orders = info.value.json()          # structured truth beats scraping the table
page.locator("tr.order-row").first.wait_for(state="visible")
```

- **A DOM predicate** when there is no observable request:

```python
page.wait_for_function(
    "() => document.querySelector('#status')?.textContent === 'Ready'", timeout=15_000)
```

- **`networkidle` is a trap** and is deprecated in Playwright for cause: long-poll, SSE, websocket and beacon-heavy pages never go idle, while quiet-but-not-finished pages go idle early. Wait for *the one thing that means success*.

After every state-changing action, assert its **consequence** (`expect(page.get_by_text("Saved")).to_be_visible()`), not merely that the click dispatched. That assertion doubles as the wait and as the retry guard — without it, a retry silently re-posts the record. Long tail: when you must retry a mutation, first re-read the server state; prefer an idempotency key on your own API surface.

Animation breaks both stability checks and coordinate math. Let the actionability-stable check absorb most of it; for the rest:

```python
page.add_style_tag(content="*,*::before,*::after{animation:none!important;transition:none!important}")
# or new_context(reduced_motion="reduce")
```

Bounded shell-side polling — the shape to copy:

```python
deadline = time.monotonic() + 20
while time.monotonic() < deadline:
    state = page.evaluate("() => window.__checkoutState")
    if state == "ready":
        break
    if state == "failed":
        raise RuntimeError("checkout failed")
    page.wait_for_timeout(250)      # polling INTERVAL only — never a wait-for-load
else:
    raise TimeoutError("deadline exceeded; state=" + repr(state))
```

`wait_for_timeout` survives only as the interval inside a condition loop. Give every wait an explicit deadline; unbounded waits compound into a blown session budget and look identical to a hang.

## 4. Login walls, captchas, 2FA: hand back vs. constants

Classify the gate before acting; the category determines the move.

- **Already authenticated** — do not re-login. Reuse the session (§5). Re-login attempts are a common cause of lockouts and of silently switching account context.
- **Operator-provided credentials** (env var, config file, secret manager) — automate the login. Never echo the secret into logs, screenshots, traces, or `.storage_state` files committed to disk. Make **one** attempt unless the error text is specifically actionable ("incorrect password" vs "too many requests"); respect lockout counters — password spam damages the account, not just the run.
- **CAPTCHA / bot challenge / device approval / push prompt / biometric / WebAuthn security key** — not automatable, and not to be routed round a solving service. **Pause and hand back** with an actionable request.
- **TOTP or emailed code** — automatable only if the operator explicitly authorised it *and* you have a legitimate programmatic read path (a TOTP secret in config, an inbox in scope). Implement it as a credential dependency, not as DOM scraping of a mailbox that will break silently. Without explicit authorisation, treat it as a captcha: hand back.

- **Paywall, ToS-gated action, geo-block, someone else's account, destructive follow-on work** — stop and ask. Gates frequently encode consent, not inconvenience.

Handoff etiquette that keeps a human fast:
1. Name the tab and URL, and the exact control that needs the click.
2. Say what will happen after they act and how you will verify it.
3. **Stop issuing input while they work** — automation keystrokes landing during a manual solve produce second-order failures that are hard to attribute.
4. Go headful for the gated stretch; a human cannot solve an invisible window.
5. Wait on a post-handoff condition with a *minutes-scale* deadline rather than declaring failure at 10 seconds.
6. After the handoff, re-snapshot and verify the authenticated state before continuing. A user saying "done" is a hint, not an assertion.

What counts as a legitimate constant: operator-supplied username/password, operator-supplied TOTP secret, an already-saved profile or `storageState`. What does not: cookies lifted from another person's browser, credential lists, fingerprint-mutating bypass kits, and "solve services".
## 5. Session persistence vs. clean boot

| Need | Mechanism | Carries | Does NOT carry |
|---|---|---|---|
| Reproducible isolation per task | Fresh **browser context** (Playwright) or temp profile: `--user-data-dir=$(mktemp -d)` | a clean slate | everything, by design |
| Real-world continuity: logins, extensions, granted permissions | Named persistent profile dir (`launch_persistent_context(user_data_dir=…)`) | cookies incl. HttpOnly, localStorage, IndexedDB, service workers, extension state, permission grants | — |
| Log in once, then start cheap and parallel | `storageState` JSON | cookies (incl. HttpOnly) + localStorage origin snapshots | sessionStorage, IndexedDB (unless opted in), SW caches, granted permissions, extensions, HTTP-basic headers, device-bound tokens |
| Act inside the user's browser right now | CDP attach (`connect_over_cdp("http://127.0.0.1:9222")`) | whatever that profile already holds | nothing — and you must not reset it |

```python
context = browser.new_context()            # after a login flow
context.storage_state(path="auth.json")    # capture
ctx = browser.new_context(storage_state="auth.json")   # replay: already logged in
page = ctx.new_page()
```

Failure modes:
- A **stale** `storageState` produces *partially-logged-in* pages that look like app bugs (header renders, data calls 401). Always assert identity — hit `/me`, or read the username in the header — never cookie *presence*.
- Context-scoped state leaks: attaching to the user's browser means a popup you opened is reachable as `context.pages[-1]` — but so is *their* unrelated tab if they open one. Filter by URL pattern instead of "last page". Prefer owning targets you created.
- Separate contexts share nothing but the executable. That is the isolation lever; use it instead of log-out/login-in cycles.
- Attaching over CDP inherits the real profile's proxy, extensions and history: dangerous for automated mutation. Prefer an owned context for anything that changes state.

Selective clearing beats a full reset when you only need one origin tidy: `context.clear_cookies()`, `page.evaluate("localStorage.clear()")`, and CDP `Storage.clearDataForOrigin({origin, storageTypes: "cookies,local_storage,indexeddb,cache_storage,service_workers"})`. Note `Network.clearBrowserCache` (HTTP cache) and `Browser.resetPermissions` (prompts) are different knobs — conflating them causes hours of "I cleared it and nothing changed".

## 6. iframes and shadow DOM: what each harness can actually reach

- **Playwright.** `page.frame_locator("iframe#pay").get_by_label("Card number")` auto-waits for the frame and chains into it; nest frame locators for frame-in-frame, or use `page.frame(url=…)` / `frame_handle` when you need the object. Cross-origin frames are reachable — Playwright goes through the browser's frame tree, not through page JS. Locators pierce **open** shadow roots automatically. **Closed** shadow roots are opaque: `el.shadowRoot === null`, no selector engine can enter, and nothing you add to the page will help. Fall back to CDP (below) or to the component's own public API/keyboard interaction.
- **Selenium.** Explicit context switching: `driver.switch_to.frame(element_or_name_or_index)` … `driver.switch_to.parent_frame()` / `default_content()`. Every locator after a switch is scoped to that document; a navigation or another switch invalidates cached handles → `StaleElementReferenceError`. Re-locate after every switch. Shadow via `el.shadow_root` (W3C-native, Chromium/Firefox recent) then search inside it; `execute_script("return el.shadowRoot")` returns null for **closed** roots — same hard limit as everywhere else at the JS layer.
- **Raw CDP.** Everything is **per execution context**. Get `Page.getFrameTree`, obtain each frame's `contextId` (`Runtime.enable` → `executionContextCreated` events, or `Page.createIsolatedWorld`), then `Runtime.evaluate({expression, contextId})`. Omitting `contextId` silently evaluates in the **top** frame and reports "not found" for perfectly good elements — this is the single most common CDP iframe bug. For shadow DOM, `DOM.describeNode({pierce: true})` and `DOM.getFlattenedDocument({pierce: true})` see inside **both open and closed** roots (that is how DevTools does it), so you can act through `DOM.*` node ids even where JS cannot. Remember `DOM.setFileInputFiles` needs the node id from the *right* document.

Cross-cutting traps:
- Iframe `sandbox` attributes can block popups, top-navigation, form submission and downloads — so dev works and prod dies purely from an attribute. Read it: `el.getAttribute("sandbox")`.
- React/Angular **portals** append dialogs at `document.body`, so DOM ancestry lies: `dialog >> button` is correct, "button under the trigger's parent" is not.
- Coordinate clicks on iframe content must add the frame's offset. Element-based clicks compute it for you; hand-rolled CDP coordinate clicks do not — that is the "click landed on the page behind" bug.
- Sticky headers and fixed cookie overlays cause `element is not interactable` / `intercepted by <div id=onetrust>` Playwright failures — read the error, it names the interceptor. Fix: `scrollIntoViewIfNeeded()`, then close the interceptor, then act. Do not "fix" this with forces clicks.

## 7. Dialogs: JS alert/confirm/prompt, file choosers

A JS modal **blocks the renderer's main thread**: while an `alert()` is open, `Runtime.evaluate`, `waitForSelector` and any DOM read hang forever — which looks like a page hang, not a dialog.

- **Playwright**: register the handler *before* the triggering action. `page.on("dialog", lambda d: d.accept())`. **If no handler is registered, Playwright auto-dismisses** — i.e. your confirm silently becomes "Cancel", and logic behind it never runs. `dialog.type()`, `dialog.message()`, and for prompt: `d.accept("typed text")`.
- **Puppeteer**: `page.on("dialog", d => d.accept())`; unlike Playwright, an unhandled dialog **hangs the page indefinitely**. This asymmetry is why porting scripts between them produces mystery timeouts.
- **Selenium**: no auto-handling, no persistent listener. `driver.switch_to.alert` then `.text`, `.accept()`, `.dismiss()`, `.send_keys()` for prompt. Any *other* command while a dialog is up raises `UnexpectedAlertPresent`, whose message carries the dialog text — so a stray alert surfaces as a crash with diagnostic value rather than a silent hang. There is no listener that fires proactively, so the robust shape is a wrapper that catches `UnexpectedAlertPresent`, inspects `.text`, decides accept/dismiss, and retries the original command.
- **Raw CDP**: `Page.enable`, listen for `Page.javascriptDialogOpening` (payload gives `type`, `message`, `url`, `frameId`), then reply `Page.handleJavaScriptDialog({accept, promptText})`. There is no implicit handling — if you do not answer, the renderer stays blocked forever, which is exactly what makes unattended CDP scripts look "hung" on a site that pops a newsletter confirm. For `beforeunload`, either suppress it (`Page.setBypassCSP` will not help; use `Page.handleJavaScriptDialog` on `type === "beforeunload"`, or navigate via a fresh target instead of closing).

## 8. New tabs, popups, window.open

Register the waiter **before** the click. Playwright offers two capture levels:

```python
with page.expect_popup() as info:            # the popup caused by exactly this action
    page.get_by_role("link", name="Open in new tab").click()
new_page = info.value

context.on("page", on_new_page)              # global: every new tab in this context
```

Facts worth internalising:
- `window.open()` and `<a target=_blank>` both surface as new **pages** in the same context. `expect_popup` catches the one your action caused; `context.on("page")` catches all of them, which is the reliable monitor for multi-window flows.
- With `noopener`, `window.open` returns `null` to the opener, so page JS can no longer script the new tab — but automation still sees it via `context.on("page")`, and still must address it as a separate `Page` object, not by referrer relationships from the DOM.
- Popup never appears? Check in order: (1) popup blocker, (2) user-activation requirement — the handler needed a trusted gesture; use the library's real click rather than `element.click()` via `evaluate`, (3) the locator matched the wrong node (assert by pulling its `innerText`).
- Multiple windows share cookies/storage within one context but are separate targets. Enumerate with `context.pages` and select by URL or title pattern; never by index — a human can open a tab underneath you mid-run.
- `page.bring_to_front()` raises a tab inside its window. It does not unlock OS foreground rules, and it will not satisfy a *user-activation* gate; for those, dispatch a trusted click through the automation protocol instead of faking focus.

## 9. Downloads: accept the destination instead of driving the dialog

Preferred path — Playwright hands you a download **object**, so the OS is never involved:

```python
page = context.new_page()                 # accept_downloads defaults to true
with page.expect_download() as dl_info:
    page.get_by_role("link", name="Statement.csv").click()
d = dl_info.value
print(d.suggested_filename, d.url)
d.save_as(os.path.join(OUT, d.suggested_filename))
assert d.failure() is None                 # None => completed
```

- `suggested_filename` comes from `Content-Disposition` or the URL; it can be empty or collide, so sanitise before writing.
- `d.path()` is a temp file that is deleted when the context closes — copy it out immediately, don't hand the path to a later stage.
- `context.on("download", handler)` is the global capture for downloads you did not deliberately trigger (and for ones killed by an intervening navigation).

CDP path, when a harness won't expose the object or you must own the directory:

```js
await cdp.send('Browser.setDownloadBehavior',
  { behavior: 'allow', downloadPath: OUT, eventsEnabled: true });
// Browser.downloadWillBegin {guid, url, suggestedFilename}
// Browser.downloadProgress  {guid, receivedBytes, totalBytes, state: 'completed'}
```

- `Page.setDownloadBehavior` is the older per-target domain still seen in many codebases; `Browser.setDownloadBehavior` is current and per-browser. When attaching to a shared browser, set it at browser scope or a newly created target will ignore your path.
- `allow` names the file from the server suggestion; `allowAndName` writes a GUID-named file and forces you to map `guid` → `suggestedFilename` from `downloadWillBegin` — prefer it when names collide or when you need deterministic paths.
- `deny` refuses outright; useful for a sandboxed crawler that must never write.
- Permission prompts ("Download multiple files?") are separate: `Browser.grantPermissions({origin, permissions:['autosave']})` is what suppresses the repeated-download chip.

**Verify the file, not the event.** A download "completing" is not the same as usable output:

```bash
find "$OUT" -name '*.crdownload' -o -name '*.part' | grep -q . && echo "still in progress"
test -s "$OUT/Statement.csv" && stat -c '%s %Y' "$OUT/Statement.csv"
```

Treat a file as final only when any `.crdownload`/`.part` sibling is gone and its size is unchanged across two checks; hash it if you know the expected digest. Checkers still playing on `test -s` alone accept truncated (zero-rows-header-only) files that look like successes downstream.

## 10. If you must drive the native Chrome "Save As" dialog

Some actions genuinely open an operating-system file dialog: Print-to-PDF with prompting, `showSaveFilePicker()` (File System Access API), "Save page as", or a browser configured to always ask. Then you are out of the DOM layer and inside `desktop-windows.md` rules — the normal failure is that keystrokes land in the page because the dialog was never focused.

Discipline on the crossover:
1. **Prove the dialog exists and has focus** before typing: in UIA, find the window that has a `File name` edit plus a `Save` button (Win32 dialogs class `#32770`), and assert it is foreground. Never assume Ctrl+S opened it — Chrome may have raised a permission chip or nothing at all. The "white box before typing" rule applies exactly: no verified focus, no keystrokes.
2. **Type the name directly.** Save As opens with the filename field populated *and selected*, so typing replaces it. Do not press Ctrl+A or Delete first, and do not Tab twice; Tabbing moves you into the file list where typing becomes keyboard navigation and changes the *folder* you save into.
3. **Press Alt+S** to invoke Save's access key. Enter is riskier: in the dialog it can activate the focused list item (navigating into a folder) instead of saving, so the "it looked like it worked" case is silent misnavigation.
4. Re-verify: dialog gone, expected path exists, file size stable across two checks (see §9 for the `find … -name '*.crdownload'` + `stat -c '%s %Y'` idiom). If the path is wrong, you have a stray file in an unexpected folder — do not just retry; clean it up first.



## 11. Cookie banners and overlays that intercept your click

Order of preference: prevent with a reused session -> click the real control -> strip the blocking element -> stop and report.

1. **Prevent it.** Reuse a `storageState` captured after one accept (§5): consent choices persist in a cookie or localStorage key, so the next load arrives dismissed. Where possible choose the CMP's own **reject all** rather than accept-all -- it is one click, and truly the polite default unless the task needs analytics-gated content.
2. **Click the named control.** Scope it to the container first, which is also how you kill the ambiguity trap of two "Accept" occurrences:

```python
import re
banner = page.get_by_role("dialog").or_(page.locator("#onetrust-consent-sdk"))
banner.get_by_role("button", name=re.compile(r"accept|agree|i agree|ok", re.I)).click()
```

Anchor test then `expect(banner).to_be_hidden()` (`to_have_count(0)`) before moving on. Many CMPs reject to a separate settings interaction, expose only two visible buttons (`Accept all` / `Only necessary`) or hide the negative action inside preference modal. Read text and pattern-match, do not hardcode CMP-specific ids like `#onetrust-accept-btn-handler` as sole selectors -- these get rebuilt by consent vendors, are for in-house or test only.
