# A consumer skin declares its own panels

A design for removing the per-station hand edit a consumer skin needs
before its Celestial panels go live.  Written 2026-08-30, after the
weewx-liveseasons conversion — the design's acceptance test — reported
it as blocking.  Nothing is built; this is for review first.

## The problem, exactly

`celestial_panels` says which panels a page embeds.  Today it lives only
in the report's `weewx.conf` stanza, and the only thing that acts on it
is weewx-celestial's installer, which writes that report's `satellites`
and `comets` groups.  So bringing up a consumer skin on a station takes:

1. hand-edit `weewx.conf` to add `celestial_panels` to that report
2. run weewx-celestial's installer again, so it reads the key
3. install the consumer skin
4. restart weewxd

Steps 1 and 2 are per station, for every consumer, for ever.  The first
consumer has seven stations.

That is a regression against what weewx-loopdata 7.0 bought skins, and
this extension's own manual draws the contrast without noticing it: the
static half of the declaration is "a skin's own business: skin.conf
deploys with the skin, so this is one edit, not one per machine" — and
the other half is one per machine, every machine.

**What is NOT wrong.**  The satellite and comet fields cannot ship in a
skin file: they follow the station's `[Skyfield] [[Satellites]]` and
`[[Comets]]`, which no shipped file can know.  And one writer for those
two groups is right.  Neither changes here.

**What is wrong** is that the *intent* is treated as station
configuration.  Which panels a page embeds is a property of the skin's
templates: identical on every station, changing only when the skin
changes.  That is a `skin.conf` fact.

## The design: two halves, each small

### 1. The key may live in the consuming skin's skin.conf

`panels_value(config, report)` — already "the ONE reader of the key, for
the installer, the verbs and the page alike" — gains a second place to
look.  The report's `weewx.conf` stanza is consulted first, and then the
skin's own `skin.conf`, resolved the way WeeWX resolves it:
`WEEWX_ROOT` + `[StdReport] SKIN_ROOT` + that report's `skin`, read with
ConfigObj.  No such file, or no key in it, means no key.

Precedence follows the platform's own merge order, where a report's
stanza beats `skin.conf`, so a station keeps a per-report override
without editing the skin.

**The invariant this must not break.**  There is one reader and both
sides use it.  Step 5 of the drop-in work created exactly the divergence
this invites: the page read the key from the MERGED skin dict while the
installer read `weewx.conf`, so a key in `skin.conf` satisfied the page
and declared nothing.  The fix then was to make the page ask the
installer's reader on the installer's file.  That still holds: the page
keeps asking `report_groups`, which keeps asking `panels_value`, and the
new lookup happens inside `panels_value` where both sides inherit it.

### 2. The consumer's installer calls celestial's writer

A consumer's `configure(engine)` ends with:

    try:
        import user.celestial
        user.celestial.declare_page_fields(engine.config_dict,
                                           pending=self['config'])
    except ImportError:
        print('weewx-celestial is not installed; install it and re-run '
              'this installer to declare the panels\' fields.')
    return True

That is celestial's own writer, on the station's config — the same code
path the installer and the `--add-`/`--remove-` verbs use, so there is
no second implementation to drift.

**`pending` is not decoration; a fresh install needs it.**  Measured in
`weecfg/extension.py` on the 5.13 wheel:

    197:  self._install_files(...)              # the skin lands on disk
    228:  save_config |= installer.configure(self)
    232:  save_config |= self._inject_config(installer['config'], ...)

`configure()` runs at 228 and the report's stanza is created at 232.  So
on a FRESH install the consumer's report does not exist yet when its own
`configure()` runs: a bare call would walk `[StdReport]`, find no report
using that skin, and correctly write nothing — leaving the state John
ruled broken, on the fresh path.  It works on an upgrade, where the
stanza is already there, which is every existing station and therefore
every test either side would naturally have run.  Found by the
liveseasons session reading weectl rather than trusting the happy path.

Two things that ordering settles in our favour: `_install_files` is line
197, so the consumer's `skin.conf` IS on disk when `configure()` runs and
the key lookup of half 1 is safe; and celestial already solves this exact
problem for itself with `declare_page_fields(..., ensure_default=True)`,
which exists because `[[CelestialReport]]` does not exist yet when
celestial's own `configure()` runs.  `pending` is that same mechanism
generalised: the caller hands over the stanza it is about to have
injected, celestial reads which report it names and which skin it runs,
writes the groups under that report name, and `_inject_config` then fills
`skin`, `HTML_ROOT` and the rest in around them, because
`conditional_merge` only fills what is absent.

**Why not have the consumer merge its own stanza first.**  That was the
first proposal, and the reason it loses does not depend on any
particular stanza: weectl's install ordering is knowledge belonging to
the repo that owns the report stanza, and a consumer that reproduces
`_inject_config`'s behaviour is copying a private implementation detail
that can change under it.  Six lines and no ordering knowledge outside
celestial beats a correct hand-merge.  The consumer passes no report NAME
either — the stanza carries it, so a station with two reports needs no
second call.

There is a concrete hazard as well, and it is worth recording precisely
because it is easy to dismiss.  `_inject_config` deep-copies the stanza
and runs `prepend_path(cfg, 'HTML_ROOT', ...)` (line 361) before merging,
so `HTML_ROOT = public_html` becomes the installation's real path; a
consumer that hand-merges first either duplicates that or lands an
unprefixed `HTML_ROOT`, which nothing repairs, since the later merge
never rewrites a key that is present.  **It does not bite the first
consumer**, whose stanza deliberately carries no `HTML_ROOT` — its pages
are the site rather than a subdirectory of it — so a hand-merge there
would have produced a correct config and passed every test that consumer
would have written.  That makes it worse, not better: the trap is
invisible to the only skin exercising the path today and would surface
for whichever skin adopted the panels next and did set an `HTML_ROOT`.
It is a reason to keep the merge out of consumers, not the reason.

The precedent is in this repo: celestial's own `loader()` does
`from user.loopdata import LOOP_DATA_VERSION`, one extension's installer
importing another's installed module, because `weectl` puts `USER_ROOT`
on `sys.path` for the install.

### Why the two halves need each other

Half 1 alone still leaves the groups unwritten until celestial's
installer next runs — the step John ruled unacceptable ("if it requires
reinstalling celestial after installing liveseasons, it is broken").

Half 2 alone leaves the key in `weewx.conf`, written by the consumer's
own installer through `conditional_merge`, which fills absent keys and
never rewrites.  Every station already carrying the key would freeze on
today's panel set, and a skin that later embeds a fourth panel would
under-declare on every machine it was already installed on — the new
panel first-painting and never moving.  Read from `skin.conf`, the value
arrives with the skin that changed.

## More than one report on one skin is required

John's ruling, after the liveseasons session reported that all seven of
its stations run the skin under a single report and offered that as a
reason the per-report override had no real case: "base nothing on
liveseasons running on only one report, I could add a metric report
tomorrow, I will not accept this limitation."  So this is a requirement,
not a case to be discovered later.  A snapshot of today's stations is not
a design constraint.

It falls out of half 1 rather than needing anything: a key in a skin's
`skin.conf` is inherited by EVERY report running that skin, which is
exactly right for a metric twin — same templates, same panels, nothing
typed anywhere for the second report.  Had the key stayed in
`weewx.conf`, adding that report would have meant remembering to add the
key to its stanza too, replacing a per-station chore with a per-report
one.  The per-report override then earns its keep on a real case: it is
what lets a second report on one skin embed something different.

Two things this makes tests rather than hopes: two reports on one skin,
both declared from that skin's key; and two reports on one skin, one of
them overriding in its own stanza.  Nobody's tree exercises either today.

**A related sharp edge, for the manual rather than for code.**  Two
reports on one skin share that skin's `[CelestialFragments]`, so they
share every prefix; pointed at one `HTML_ROOT` they would overwrite each
other's fragments every cycle.  A metric twin normally has its own
`HTML_ROOT`, so it is fine by construction — and two reports running one
skin into one `HTML_ROOT` are already overwriting each other's
`index.html`, which is a self-conflict at the Cheetah level rather than
anything fragments create.  A line in the manual; not a cross-report
collision check, which would have the generator enumerating other
reports' `HTML_ROOT`s to notice a configuration broken for a more obvious
reason first.

## What it costs, in all three install orders

- **celestial first, then the consumer** — the import succeeds and the
  groups are written during the consumer's install.  One step.
- **consumer first, then celestial** — self-heals: celestial's installer
  already walks every report and writes for each one carrying the key.
- **celestial never installed** — the consumer's installer prints a line
  and finishes.  Its pages carry the panels' install hint, as they do on
  any station without an extended almanac.

## Tear-down: the groups are pruned when the skin is gone

Half 1 improves bring-up and would have quietly degraded removal, which
the liveseasons session caught by reading weectl.  There is **no
uninstall hook**: `ExtensionInstaller` has `process_args` and `configure`
and nothing else, and `uninstall_extension` calls `uninstall_files` and
then `remove_and_prune(config_dict, installer['config'])`, which prunes
only what that extension's own `config` declared.

So uninstalling a consumer skin deletes its `skin.conf`, taking the key
with it, while the `satellites` and `comets` groups celestial wrote under
that report survive — and weewx-loopdata goes on evaluating them every
packet for panels that no longer exist.  Worse, the documented remedy
becomes unavailable: it is "empty the key and re-run", and an absent key
means "not this extension's report", so celestial deliberately leaves
those groups alone.  Before this design the key lived in `weewx.conf` and
outlived the skin, so the remedy was there to use.

**Ruled (John, 2026-08-30): prune the groups when the skin cannot be
resolved.**  A report that carries no key from either place AND whose
skin's `skin.conf` cannot be read is a report that once was a consumer
and can no longer be one; celestial removes its two groups and reports
the removal, exactly as it reports one for a group no named panel reads.

The signal is deliberately the `skin.conf` being **absent** — ENOENT, the
file is not there — and not "the skin directory is missing", and not
"the file could not be read":

- weectl's uninstall removes the files it installed and may leave a
  non-empty skin directory behind (celestial's own 9.0 upgrade leaves
  twelve), so a missing directory is not reliable.
- WeeWX tolerates a skin with no `skin.conf` at all — reportengine wraps
  that read and says so — but such a skin cannot be a consumer unless its
  report carries the key in `weewx.conf`, and that case is excluded by
  the no-key-from-either-place half of the test.

**Absence is a statement; an error is a question, and you never prune on
a question.**  "Could not be read" covers at least four conditions that
are not "this skin is gone": EACCES, from a verb run by a user without
read access, a restrictive umask, or root_squash on a networked skin; a
mount or container volume not up yet; EIO or a half-written file, from an
editor that truncates before writing or an rsync mid-flight; and a parse
error from a syntax slip, an unbalanced quote being the classic.  In
every one the skin is installed and the operator's intent is unchanged,
and pruning would stop weewx-loopdata declaring the fields, kill the
panels, and say nothing until someone happened to re-run an installer.
Self-healing on the next run is true and is not much comfort when the
trigger was a permission bit.

So: ENOENT prunes, and every other failure to read is UNKNOWN — the
groups are left alone and the run says so in the log.  What that gives up
is that a skin whose `skin.conf` is unreadable for ever keeps its groups
for ever, which is the status quo, and the status quo is not what was
ruled broken.

A report whose owner simply deleted the key from a `skin.conf` that still
exists is unchanged: no key means not ours, the groups stay, and emptying
the key is still how you ask for their removal.

## Two things this design does not do

**The `ImportError` guard is unreachable in a consumer that gates on
celestial.**  A consumer whose own `loader()` refuses to install without
weewx-celestial — importing `user.celestial` to check its version, which
`loader()` does before `configure()` — can never reach it.  The guard
still belongs there, for consumers without such a gate, but the
three-orders table above describes those: a gating consumer is refused
earlier and more clearly.

**The skin path is resolved from the GLOBAL `[StdReport] SKIN_ROOT`, on
purpose.**  WeeWX ignores a `SKIN_ROOT` set on an individual report:
`reportengine.py` builds a report's skin path from `WEEWX_ROOT` +
`config_dict['StdReport']['SKIN_ROOT']` + that report's `skin`.  Honouring
a per-report override here would make celestial read a different
`skin.conf` than WeeWX does, and the two would disagree silently about
which file a report's options come from.

## Found while building it

Two things the design did not anticipate, both caught by running the code
rather than by reasoning about it.

**`WEEWX_ROOT` is not a key in `weewx.conf`.**  weewxd and weectl inject
it into the config dict they hand out, but this extension's own
`--add-`/`--remove-` verbs read the file straight off disk with
ConfigObj, where it simply is not there — so a relative `SKIN_ROOT` would
have resolved against the caller's working directory and silently found
no skin.conf at all.  `skin_conf_path` falls back to the directory of the
config file itself, which is what weecfg derives the root from.  Every
unit test set `WEEWX_ROOT`, so only a scratch station could show it.

**A broad `except` hid a missing import.**  `configobj` is imported
locally in five places in `celestial.py` and never at module level; the
first cut of `skin_conf_panels` used it without importing, and its
`except Exception` turned the `NameError` into a report that the file was
*unreadable* — a fault in this code disguised as precisely the condition
the ruling says must never cause action, which would have meant "leave
the groups alone, for ever, everywhere".  The clause now catches
`(OSError, UnicodeDecodeError, ConfigObjError)`, the conditions the
ruling calls unknown, and lets anything else surface as the bug it is.

## Alternatives considered and rejected

- **A service** that writes or injects the declaration at weewxd start.
  Correctness would depend on service ordering the user controls, and it
  re-creates the registration whose 5.x leftover already crashes weewxd
  on upgrade.  Ruled out.
- **A declaration provider in weewx-loopdata** — a config key naming a
  function loopdata imports and calls.  A plugin framework and a new
  trust surface, invented to avoid an install step.
- **Template expansion in weewx-loopdata** — `almanac.{tag}.az` expanded
  over the keys of a named config section.  Inert and smaller, but it
  makes loopdata's declaration reach into another extension's section,
  and it is a sibling-repo design cycle to solve a problem that turns out
  to be solvable here.

Both loopdata ideas were escalation: they proposed architecture in
another repo to avoid an install ordering problem that two small changes
in the two repos that actually own it solve completely.

## Scope

In weewx-celestial: `panels_value` gains the skin.conf lookup and a
helper that resolves a report's skin path; `declare_page_fields` gains
`pending`, alongside the `ensure_default` it already has for the same
reason; the docs say where the key may live, which wins, and the
one-HTML_ROOT edge above; tests cover the key in each place, in both, in
neither, a skin directory that does not exist, two reports on one skin,
two reports on one skin with an override, a fresh install with no stanza
yet (the `pending` path), and the page and installer agreeing in every
case.

One triple is the seam between the tear-down rules and is worth its own
test, because it is what a later refactor would most easily collapse.
For a report carrying no key: `skin.conf` readable keeps its groups;
`skin.conf` ABSENT loses them; `skin.conf` present but unreadable for any
other reason keeps them AND logs.  The middle case is the ruling; the
third is what stops a permission bit or an unbalanced quote looking like
an uninstall.  Deleting a key is a statement about a skin's
configuration, removing the skin is a statement that there is no consumer
at all, and a failure to read is neither.  In the consumer: an `ImportError`-guarded call and a
`celestial_panels` line — about six lines, and no merge logic.

The verification is a scratch CitySim station with a consumer skin
declaring `celestial_panels` in its `skin.conf` and NOTHING in
`weewx.conf`, installed in each of the three orders above, with the
fresh-install case run from a config that has no such report stanza at
all — before any of it is handed to the liveseasons session.
