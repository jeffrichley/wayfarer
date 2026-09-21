---
type: reference
---
# Best practice for landing a graph of related changes

**Ticket:** [#17](https://github.com/jeffrichley/wayfarer/issues/17) — "Best practice for landing a graph of related changes" · **Map:** [#1](https://github.com/jeffrichley/wayfarer/issues/1) — Wayfarer's first running slice · Researched 2026-09-21.

Builds on [#13](https://github.com/jeffrichley/wayfarer/issues/13) (three branch levels, auto-merge by exception, resolver run on conflict) and feeds [#16](https://github.com/jeffrichley/wayfarer/issues/16) (the merge queue).

Sources are labelled throughout:
**[doc]** = a primary source states it (official docs, a man page, a peer-reviewed paper, a vendor's own reference);
**[claim]** = commonly asserted in secondary writing but not found in a primary source;
**[inf]** = my inference from the sources, marked as such.

---

## Bottom line

**The three-level design is sound, and the literature has a name for the middle level — but it is not "feature branch". It is `next`.** `gitworkflows(7)` documents a graduated integration branch that topics merge *up* into and that later work is legitimately based on, which is exactly the effort branch's job. Nothing in the trunk-based literature rules it out; what that literature rules out is an *unbounded* one with no continuous integration from trunk.

**The one thing the survey rules out hardest is stacking.** Every stacked-change tool surveyed is linear or a tree — GitHub's native stacks, `git spr`, Gerrit relation chains, Graphite (one recorded parent per branch). The only one whose edges form a real DAG, Phabricator's free-text "Depends on", cannot land along them. And while two systems can heal descendants without the author present (Gerrit's server-side **Rebase Chain**, Graphite's post-merge rebase job), **neither covers the conflict case: all four escalate a conflict to a human, with no documented automated policy.** A `/to-tickets` DAG is not a stack, and an agent that has exited is not an author. **Wayfarer's design already dodges this by construction**, and should say so explicitly: a dependent ticket is cut from the effort branch *after* its blockers land, so no parent is ever amended underneath a child, so nothing ever needs restacking. That property is load-bearing and must be protected.

**On re-testing: order the writes *and* re-validate, or the queue is nothing.** Waystation's lock already serialises the write (ADR-0005). The entire documented value of every gating system since the Not Rocket Science Rule is testing each change *as it will be merged* — which is the part the lock does not do. But **do not build speculative execution.** Uber's own follow-up paper cut CI resource usage ~53% by speculating *less*. At effort scale (single digits of tickets, bursty) serial re-validation against the effort-branch head is the right answer, and the literature's speculation machinery is justified at Google/Uber volumes, not this one.

**On independence: yes, disconnected parts of a DAG can land without serialising — but the ticket DAG is not the right signal for deciding that.** Every tool that skips serialisation decides it from *file or build-graph overlap* (Mergify scopes, Zuul shared queues, Google's Rosie sharding), never from an author-declared dependency. Two tickets with no "blocked by" edge can still touch the same file.

---

## 1. Stacked changes

### What they are

A **stack** is a chain of changes where each targets the one below it. The point is to let a dependency chain of small changes be reviewed and landed in order.

**[doc]** GitHub shipped this natively in public preview on 2026-07-30 ([changelog](https://github.blog/changelog/2026-07-30-stacked-pull-requests-are-now-in-public-preview/)), defined as: *"A stack is a series of pull requests in the same repository where each pull request targets the branch of the pull request below it, forming an ordered chain that lands on a single branch."* ([docs](https://docs.github.com/en/pull-requests/reference/stacked-pull-requests))

### A DAG breaks the model. This is documented, not inferred.

**[doc] GitHub:** *"a fully linear history between every branch in the stack is a strict requirement for merging."* Also: *"Stacked pull requests require all branches to be in the same repository. Cross-fork stacks are not supported."* ([reference](https://docs.github.com/en/pull-requests/reference/stacked-pull-requests))

**[doc] `git spr`** (github.com/ejoffe/spr) is even more explicitly linear: the model is *one commit = one PR* over a single local branch, with a per-PR status bit "*stack: all PRs below are ready*". A commit series cannot branch. ([repo](https://github.com/ejoffe/spr))

**[doc] Gerrit** has two distinct mechanisms and only one of them is a chain:
- A **relation chain** is parent/child between changes — linear.
- A **topic** is the set mechanism. With `submitWholeTopic` enabled, *"submitting a change within a topic causes all of the changes in the topic to be submitted together"* — and this **is** a set, not a chain, and can span repositories. But the submittability rule is transitively closed: *"a change with a topic is submittable when all changes in the topic are submittable and all of the changes' dependent changes (and their topics!) are also submittable."* ([cross-repository-changes](https://gerrit-review.googlesource.com/Documentation/cross-repository-changes.html))
  **[doc]** Atomicity across repos is *not* guaranteed: the docs say it "simply triggers submission of all changes" with no other guarantees, so partial submission is possible.
  **[inf]** This makes a topic an *all-or-nothing gate over the transitive closure* — which is precisely the "one bad ticket stalls the whole effort" failure that Wayfarer's per-ticket landing exists to avoid. A topic is the right shape for a DAG and the wrong policy for a burst.

**[doc] Graphite is a tree, not a DAG.** Its unit is a *branch* with exactly one recorded parent — *"keeping track of the 'parent' of a given branch"* — with metadata in `.git`. `gt branch up` *"Switch to the child of the current branch. Prompts if ambiguous"*, so many children are fine; nothing anywhere expresses two parents, and `gt upstack onto` only *moves* a branch to a different single parent. ([withgraphite docs](https://github.com/withgraphite/docs/blob/main/guides/graphite-cli/restacking-branches.md), [command reference](https://github.com/withgraphite/docs/blob/main/guides/graphite-cli/command-reference.md)) **[inf]** So Graphite is a forest rooted at trunk; a diamond is outside the model.
**[claim]** Its merge-queue blog nonetheless describes *"dependency graph"* modelling and states that on failure *"we evict only the failing PR and its dependents, leaving the rest of the queue intact."* ([graphite.com blog](https://graphite.com/blog/the-first-stack-aware-merge-queue)) That eviction rule is the single most reusable idea in this section, and it is a vendor blog rather than reference documentation — hence **[claim]**.

**[doc] Phabricator is the one tool whose dependency edge is a genuine DAG** — because it is free text, not topology. *"Create a dependency between revisions by writing 'Depends on Dxxx' in your summary"* ([epriestley, Q396](https://secure.phabricator.com/Q396)), and LLVM's manual documents the multi-parent form: *"If you want a single review to have multiple parent reviews then add more with 'and', for example: 'Depends on D12344 and D12345'"* ([LLVM Phabricator guide](https://releases.llvm.org/18.1.6/docs/Phabricator.html)). But the price is that the review graph and the VCS graph can disagree, and nothing reconciles them; `arc land` lands *by working-copy ancestry*, not by "Depends On" edges. **[inf]** A DAG you can *declare* but not *land* is not a landing mechanism — which is the same split Wayfarer has between GitHub's blocking edges and git.

### Restacking is the crux, and it is almost always an author's job

This is the finding that decides the ticket.

**[doc] GitHub — no automatic restacking.** When linear history is lost, the author restores it: `gh stack rebase` then `gh stack push`, or "Rebase stack" in the merge box. The troubleshooting page enumerates nine failure modes and **every single remedy is a command the author runs**: rebase conflict (`gh stack rebase --continue` / `--abort`), sync conflict (all branches restored, author re-runs), interrupted modify session (`gh stack modify --abort`), *"if a pull request is removed or ejected from the queue, all pull requests above it in the stack are also ejected"* (author re-adds), *"closing a pull request in the middle of a stack blocks all pull requests above it from being mergeable"* (author unstacks or restructures). ([troubleshooting](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-stacked-pull-requests))

**[doc] GitHub's own AI-agent guidance still routes through the author.** The Copilot tutorial: *"Ask Copilot to revise the layer a reviewer flagged. The agent moves to the right branch, makes the change, and commits it there. Then, it rebases the layers above so they pick up the fix."* and *"run `gh stack rebase --upstack` to carry changes up the stack."* ([tutorial](https://docs.github.com/en/copilot/tutorials/stack-ai-generated-code-in-pull-requests)) The agent does the rebase — but only because a person is present, in session, telling it to. That is not Wayfarer's regime: a Wayfarer ticket agent runs unattended in print mode and has exited by the time its parent changes.

**[doc] `git spr` automates it — by owning the working copy.** It rebases dependents automatically (`git spr update`; `--no-rebase` to opt out), keeps PR identity stable across amends via a generated `commit-id` appended to the commit message rather than the hash, and `git spr merge` *"finds the top mergeable PR in the stack, combines all commits up to it into a single PR, merges it, and closes the intermediate PRs"* — explicitly *"This avoids triggering redundant CI runs."* ([README](https://github.com/ejoffe/spr), [git/commit.go](https://github.com/ejoffe/spr/blob/master/git/commit.go)) It can do this only because the whole stack is one linear commit series in one working copy belonging to one live author. Wayfarer has neither. And on conflict it stops dead: *"Rebase conflict detected. Resolve conflicts and run 'git spr edit --done' again."*

**[doc] Two tools can heal descendants without the original author — and they are worth studying.**
- **Gerrit's Rebase Chain is a server-side REST action**, callable by anyone with permission, not something that needs the author's working copy: *"If the chain is outdated, i.e., there's a change that depends on an old revision of its parent, the result is the same as individually rebasing all outdated changes on top of their parent's latest revision."* On failure it returns `409 Conflict` — *"The change could not be rebased due to a path conflict during merge"* — naming the failing change and the conflicting files. It *"Requires a linear ancestry relation (single parenting throughout the chain)."* ([REST API](https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html#rebase-chain))
- **Graphite's server auto-rebases upstack branches after a merge.** *"Graphite now runs a job that automatically rebases the remote branches corresponding to the PRs 'upstack' of the one(s) you merged"*, using temporary `graphite-base/*` branches for atomic retargeting. **[claim]** (vendor blog + docs page, not reference docs) — and it covers *merges only*, not mid-stack amends. A conflict bounces straight back to the author: *"run `gt sync && gt restack && gt submit --stack`… then… click Merge one more time to re-queue."* ([graphite.com/docs](https://graphite.com/docs/merge-pull-requests))

**[doc] Universal across all four: a conflict is the escape hatch to a human.** None of Graphite, Gerrit, `git spr` or Arcanist documents an automated conflict policy; each halts and waits for interactive resolution. Graphite additionally warns that recovery is not clean — *"Graphite does not currently provide its own abort command — `git rebase --abort` is safe to use to abort a single rebase in progress, but will not undo prior restack operations if your command already completed them."*

**[doc] Gerrit's submit types are the one place the trade Wayfarer already made is written down.** *Rebase If Necessary* *"fast-forwards the target branch if possible, and otherwise does a rebase automatically"*; *Cherry Pick* *"always performs a cherry pick of the current patch set when a change is submitted. **This ignores the parent lineage**."* The docs recommend *Rebase Always* over *Cherry Pick* because it *"respects change dependencies"*, and the submitted-together closure is computed *"for each change whose submit type is not CHERRY_PICK"*. ([project config](https://gerrit-review.googlesource.com/Documentation/config-project-config.html)) **[inf]** ADR-0015 has the resolver run replay by cherry-pick to keep the series linear (ADR-0006). Gerrit's warning is that cherry-pick drops the dependency relation — harmless for Wayfarer, because by the time a ticket lands its blockers are already *in* the target, so there is no lineage left to respect. Worth recording as a checked assumption rather than an accident.

**[doc] What merging does to the rest.** GitHub: *"The selected pull request and all unmerged pull requests below it land on the base branch together as a single operation, ordered from the bottom up,"* after which *"the next unmerged pull request is automatically rebased to target the stack base directly."* And *"every pull request in a stack is evaluated against rules for the base of the stack — typically `main`."*

### Does anything re-test after a restack?

**[doc]** Nothing in the stacking layer itself. Restacking rewrites branches; re-validation is whatever the repo's checks do on the new push. **Landing safety in all four tools comes from the queue underneath, not from the stack.** GitHub's stack/queue interaction is documented only as sizing: *"the merge queue allows the merge group to exceed its configured maximum size by up to 50 percent. If the stack is too large to fit within that buffer, it will automatically be split across consecutive merge groups."* ([merging stacked PRs](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-stacked-pull-requests))

**[claim] Graphite's queue is the one that is stack-aware**, using *"speculative execution, similar to branch prediction, to run CI for multiple enqueued stacks at the same time"*, bisecting a failed batch — *"the system identifies which stacks in the batch caused the failure by running CI on smaller subsets"* — and skipping redundant work on a fast-forward: *"No need for CI to run again since we have already validated the CI against that exact change."* ([merge queue optimizations](https://graphite.com/docs/merge-queue-optimizations)) That last sentence is the bors discipline restated, and it is the standard Wayfarer's queue should meet.

**[doc] Only Gerrit documents a numeric limit** on a landing set: `change.maxSubmittableAtOnce`, *"Maximum number of changes that can be chained together in the same repository to be submitted at once,"* default **32767** ([config-gerrit](https://gerrit-review.googlesource.com/Documentation/config-gerrit.html)). **[inf]** Effectively unbounded; nobody has found a size at which a set stops working, only sizes at which it stops being reviewable.

### Verdict for this shape

**Do not model the ticket DAG as a stack.** Graphite is a tree; GitHub, `git spr` and Gerrit relation chains are linear; the only tool whose edges form a real DAG (Phabricator) cannot *land* along them. **Take two ideas from it:** Graphite's *evict the failing change and its dependents*, which no flat FIFO gives; and Gerrit's *Rebase Chain* as proof that healing descendants can be a server-side operation rather than an author's.

---

## 2. Merge queues and speculative execution

The founding rule, **[claim]** (the canonical post at graydon2.dreamwidth.org returns 403; the wording is quoted identically in [huonw's writeup](https://huonw.github.io/blog/2015/03/rust-infrastructure-can-be-your-infrastructure/) and the [Gullintanni README](https://gullintanni.github.io/gullintanni/readme.html)):

> *"The Not Rocket Science Rule Of Software Engineering: automatically maintain a repository of code that always passes all the tests."*

**[doc] Zuul states the mechanism that makes that rule mean something:** *"A gating system should always test each change applied to the tip of the branch exactly as it is going to be merged."* ([gating](https://zuul-ci.org/docs/zuul/latest/gating.html))

That sentence is the answer to #16's central question. A queue that only orders writes tests nothing new; Waystation's per-repo lock already orders writes.

### What each one actually re-tests

| | Re-tests what | Speculation | Failure handling | Cost shape |
|---|---|---|---|---|
| **GitHub merge queue** | A temp branch `gh-readonly-queue/{base}/…` = base + **all PRs ahead in the queue** + this PR | Yes, cumulative FIFO, built in | **Evict** the failing PR, then **rebuild and re-test the tail's merge groups**. No bisection. | Latency bought with compute, capped by `build concurrency` (1–100) |
| **bors / bors-ng** | One `staging` branch holding a **batch** of approved PRs; on success master fast-forwards to it | No | **Bisect**: split the failing batch in half, requeue both; a single-PR batch that still fails is *"kicked back to the creator"* | *"O(E log N) … versus O(N)"* — minimal CI spend, maximal serial latency |
| **Mergify** | Temp `mergify/merge-queue/` branches representing the cumulative merge; **the original PRs are what merge** | Yes — `max_parallel_checks` (the older spelling `speculative_checks` is legacy), plus `batch_size` | **Both**: speculative parallel checks *and* bisection down to a single-PR batch, which is then *"deemed to be the culprit and is removed"* | Explicit "RCV theorem": pick two of Reliability, Cost, Velocity |
| **Zuul** | Each change tested *with the changes ahead of it applied*, across repos if needed | Yes, and the most principled | **Queue reset**: drop the failing change, re-test everything behind it against the corrected state | Adaptive TCP-style window: +1 per success, **halved** per failure, with floor and ceiling |

**[doc] GitHub specifics** ([managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)):
- A merge group contains *"the latest version of the `base_branch` as well as changes from pull requests ahead of it in the queue."* So GitHub's queue **is** speculative, cumulatively.
- CI must opt in: *"you need to update the workflows to include the `merge_group` event as an additional trigger. Otherwise, status checks will not be triggered when you add a pull request to a merge queue."* In that run `GITHUB_SHA`/`GITHUB_REF` are the merge group's, **not the PR's** — the workflow has no PR context.
- Settings that matter here: merge method; **build concurrency** (the speculation-depth knob); min/max group size; wait time to meet the minimum; *only merge non-failing pull requests*; status-check timeout.
- Failure: *"the merge queue automatically removes pull request #1 from the merge queue"* and rebuilds the groups behind it. Queue-jumping also forces a full rebuild of the tail.
- **Target branch:** it is a branch-protection / ruleset rule, so it applies to whichever branch the rule names — **not default-branch-only**. Two documented constraints bite here: a merge queue **cannot be enabled on a branch protection rule whose pattern uses wildcards**, and the "Require merge queue" ruleset rule *"is not available for rulesets created at the organization level."*
  **[inf] This is decision-relevant for #16.** Effort branches are named per effort, so using GitHub's native queue would mean **creating and deleting a branch rule per effort**, via the API, for every effort. That is real operational weight for a local-first single-user app, and it pushes toward Wayfarer ordering the landings itself.

**[doc] Zuul specifics** ([gating](https://zuul-ci.org/docs/zuul/latest/gating.html), [pipeline](https://zuul-ci.org/docs/zuul/latest/config/pipeline.html), [queue](https://zuul-ci.org/docs/zuul/latest/config/queue.html)):
- `dependent` pipeline manager: *"It ensures that every change is tested exactly as it is going to be merged into the repository."* `independent`: *"every event in this pipeline should be treated as independent of other events."* There is also `serial` — *"supports shared queues (like dependent pipelines) but only one item in each shared queue is processed at a time"* — which is the closest named analogue of what Wayfarer should start with.
- Speculation: *"it assumes that all jobs will succeed and tests them in parallel accordingly … if one fails, then changes that were expecting it to succeed are re-tested without the failed change."*
- Cross-repo dependency graph: `Depends-On: <change-url>` in a commit footer; *"changes may depend on changes in any other project, even projects not on the same system."* Cycles are opt-in and the docs call them *"an antipattern"* (`allow-circular-dependencies`, default false).
- The "nearest non-failing set" phrasing sometimes attributed to Zuul is **[claim]** — I did not find it on zuul-ci.org. The documented behaviour is drop-and-re-test-the-remainder.

**[doc] Speculation is expensive, measured.** Uber's SubmitQueue *"speculatively executes builds and only lands changes with successful outcomes"*; the ICSE 2025 follow-up reports that *"despite its effectiveness, the system faces inefficiencies in resource utilization, leading to a high rate of premature build aborts and delays in landing smaller changes blocked by larger conflicting ones,"* and that adding a **speculation threshold** plus ML build-time prediction produced *"a reduction in Continuous Integration (CI) resource usage by approximately 53%, CPU usage by 44%, and P95 waiting times by 37%."* ([arXiv:2501.03440](https://arxiv.org/abs/2501.03440)) The first-party tool README adds: on failure *"SubmitQueue isolates the offending change and retries the rest — all without human intervention."* ([github.com/uber/submitqueue](https://github.com/uber/submitqueue))

**[inf] The lesson is the opposite of the obvious one.** Speculation is what you add when serial validation cannot keep up with arrival rate. Uber and Google are landing hundreds of changes a day. A Wayfarer effort is single-digit tickets landing in bursts. **Serial re-validation against the effort-branch head is the correct starting design**, and the *only* thing that justifies speculation later is a measured queue depth (#16 already asks "how deep before it is a signal rather than a mechanism" — eight deep is the signal, and the fix is not speculation).

### Verdict for this shape

Re-validate every landing candidate against the current effort-branch head, one at a time, and land the artefact that was tested (bors's fast-forward discipline, Zuul's "exactly as it is going to be merged"). Start with speculation depth 1. Add Graphite-style **evict-the-failing-change-and-its-dependents** on failure, which no flat FIFO provides.

---

## 3. Long-lived integration branches vs trunk-based development

### What trunk-based literature actually says

**[doc] DORA's numbers are these two, and no others** ([dora.dev](https://dora.dev/capabilities/trunk-based-development/)): *"Have three or fewer active branches in the application's code repository,"* *"Merge branches to trunk at least once a day,"* *"Don't have code freezes and don't have integration phases."* The 2016 State of DevOps wording, quoted by Fowler: *"having branches or forks with very short lifetimes (less than a day) before being merged into trunk, and less than three active branches in total, are important aspects of continuous delivery, and all contribute to higher performance."*

**[doc] It is correlational.** DORA's method is an annual self-reported survey analysed with PLS structural equation modelling, which *"optimizes for prediction of the dependent variable (vs. testing for model fit)"* ([dora.dev/research](https://dora.dev/research/2019/structural-equation-model/)). The language is "contribute to" and "predicts", never "causes". **[claim]** "DORA proved long-lived branches cause slow delivery" — not found in any primary text.

**[doc] trunkbaseddevelopment.com's boundary has two axes, not one.** *"the branch should only last a couple of days. Any longer than two days, and there is a risk of the branch becoming a long-lived feature branch (the antithesis of trunk-based development)"* and *"the developer count should stay at one (or two if pair-programming)"*; *"if you are grouping multiple developers on those branches or they are not deleted after a couple of days, then it is not the Trunk-Based Development branching model."* ([short-lived feature branches](https://trunkbaseddevelopment.com/short-lived-feature-branches/))

**[doc] It does permit one long-lived class: release branches** — cut just in time, *"should not receive continued development work"*, *"Release branches are not merged back into trunk"*, and fixes go on trunk and are cherry-picked *down*. ([branch for release](https://trunkbaseddevelopment.com/branch-for-release/))

### What the cost actually is

**[doc] Fowler's mechanism is the semantic conflict, not the textual one** ([branching patterns](https://martinfowler.com/articles/branching-patterns.html)):

> *"But often conflicts appear where the text merges without a problem, but the system still doesn't work. Imagine Scarlett changes the name of a function, and Violet adds some code to her branch that calls this function under its old name. This is what I call a Semantic Conflict. When these kinds of conflicts happen the system may fail to build, or it may build but fail at run-time."*

and the only defence is tests: *"semantic conflicts are much harder to deal with, and this is where Self Testing Code is very handy."* He is also explicit that pulling mainline into your branch is *not* integration: *"To finish integrating she must push her changes into the mainline."*

**[doc] The cost is variance, not mean effort:** *"The problem with big merges is not so much the work involved with them, it's the uncertainty of that work. Most of the time even big merges go smoothly, but occasionally they go very, very, badly."*

**[doc] The second-order cost he calls the biggest is refactoring suppression:** *"the biggest problem with it may be that it can deter refactoring… Feature Branching also discourages developers from making changes that aren't seen as part of the feature being built."*

**[doc] There is no published cost curve.** The strongest shape claim in the entire literature is *"branches diverge exponentially as they run without integrating"* (LeRoy's Illustration), offered as an illustration, with the actionable form *"Aim to double your integration frequency."* **Do not claim a measured cost-vs-age function; none exists.** The only hard numbers anywhere are the threshold heuristics above.

**[doc] Fowler explicitly licenses short feature branches:** *"A team that typically completes features in a day or two are able to integrate frequently enough to avoid the problems of delayed integration."* ([FeatureBranch](https://martinfowler.com/bliki/FeatureBranch.html))

### The pattern that actually fits the effort branch

**`gitworkflows(7)` is the strongest primary source for a graduated integration branch, and it is a man page, not a blog.** ([git-scm.com/docs/gitworkflows](https://git-scm.com/docs/gitworkflows))

**[doc]** *"maint tracks the commits that should go into the next 'maintenance release' … master tracks the commits that should go into the next release … next is intended as a testing branch for topics being tested for stability for master."* Plus a fourth used differently: *"seen … is an integration branch for things that are not quite ready for inclusion yet."* And: *"Conceptually, the feature enters at an unstable branch (usually next or seen), and 'graduates' to master for the next release once it is considered stable enough."*

Three rules from it that bear directly on the effort branch:

1. **[doc] Merge upwards.** *"Always commit your fixes to the oldest supported branch that requires them. Then (periodically) merge the integration branches upwards into each other."* Downward propagation needs cherry-pick and should be rare. (Independently corroborated by trunkbaseddevelopment.com's identical rule for release branches.)
2. **[doc] Fork topics at the oldest integration branch you will merge into.** *"Make a side branch for every topic… Fork it off at the oldest integration branch that you will eventually want to merge it into."* Rationale: *"Committing everything directly on the integration branches leads to many problems: Bad commits cannot be undone, so they must be reverted one by one."*
3. **[doc] The `next` / `seen` distinction is exactly the effort branch's constraint.** *"To test the interaction of several topics, merge them into a throw-away branch. **You must never base any work on such a branch!**"* — that is `seen`. Wayfarer's dependents *do* base work on the effort branch, so **the effort branch is `next`, not `seen`**, and inherits `next`'s discipline: rewinding it is exceptional and, in git.git, *"you should make a public announcement indicating that next was rewound and rebuilt"*, and only at a release boundary.

**[doc] One genuine conflict between the two literatures, worth recording.** trunkbaseddevelopment.com says to merge trunk *into* a short-lived branch to keep it current: *"merges to the short-lived feature branch are allowed to bring it closer to HEAD of main."* `gitworkflows(7)` says the opposite for topics: *"Do not merge to downstream except with a good reason: upstream API changes affect your branch; your branch no longer merges to upstream cleanly."* They optimise different things — integration frequency vs topic reviewability and revertability. **[inf]** For Wayfarer the two levels take different sides: **trunk → effort branch should be merged continuously** (TBD's rule, because the effort branch is the thing that will eventually integrate and its divergence is the risk), while **effort branch → ticket branch should not be re-merged mid-ticket** (gitworkflows' rule, because a ticket branch is short-lived and re-merging clutters the series that Waystation's `apply` mechanism wants linear, ADR-0006).

**[doc] Documented mitigations for a branch that must live longer:** merge trunk in continuously; branch by abstraction (*"make a large-scale change… in gradual way that allows you to release the system regularly while the change is still in-progress"*, [BranchByAbstraction](https://martinfowler.com/bliki/BranchByAbstraction.html)); keep the work small at source; verify commits *before* they land (*"It is best to have a human agreement (the code review), and machine agreement (CI verification) before the commit lands in the trunk"*, [TBD/continuous-integration](https://trunkbaseddevelopment.com/continuous-integration/)); feature flags; and Fowler's **Team Integration Branch** — *"Allow a sub-team to integrate with each other, before integrating with mainline"* — which is, in his own vocabulary, precisely what an effort branch is.

### Verdict for this shape

The effort branch survives the trunk-based critique, but only with three obligations attached, all documented: **(a)** continuous merge of trunk into it, because the drift cost is real even if unquantified; **(b)** it is append-only during the effort — `next`-like, never `seen`-like, because dependents are based on it; **(c)** its lifetime and size are budgeted and visible, since the only real numbers the field offers are thresholds and Wayfarer is well past the one-day one.

**[inf]** Note the honest tension: an effort branch that lives days-to-weeks with N agents committing to it is, on trunkbaseddevelopment.com's own two axes (age > 2 days, developers > 1), outside trunk-based development. The defensible position is not "we comply" but "this is a `next`-shaped integration branch, which is a different, also-documented pattern, and we pay its documented price with continuous trunk merges and per-landing re-validation."

---

## 4. Expand–contract / parallel change

**[doc]** ([ParallelChange](https://martinfowler.com/bliki/ParallelChange.html), Danilo Sato) *"Parallel change, also known as expand and contract, is a pattern to implement backward-incompatible changes to an interface in a safe manner, by breaking the change into three distinct phases: expand, migrate, and contract."*

- **Expand:** *"you augment the interface to support both the old and the new versions… Existing clients will continue to consume the old version, and the new changes can be introduced incrementally without affecting them."*
- **Migrate:** *"you update all clients using the old version to the new version. This can be done incrementally and, in the case of external clients, this will be the longest phase."*
- **Contract:** *"Once all usages have been migrated to the new version, you perform the contract phase to remove the old version."*

**The invariant:** at every commit both contracts hold, so **every intermediate state is independently green and releasable**. *"This pattern is particularly useful when practicing ContinuousDelivery because it allows your code to be released in any of these three phases."*

**The cost, stated:** *"If the contract phase is not executed you might end up in a worse state than you started, therefore you need discipline to finish the transition successfully."* The same warning appears independently in [evodb](https://martinfowler.com/articles/evodb.html) about the transition phase: *"It does add complexity, so it's important that it gets removed once downstream systems have had time to migrate."*

**It applies even with full control of all callers:** *"Even when you have control over all usages of the interface, following this pattern is still useful because it prevents you from spreading breakage across the entire codebase all at once."*

**[doc] Google does exactly this at machine scale.** The `scoped_ptr` → `std::unique_ptr` migration made the old type an alias of the new (expand), textually substituted call sites in shards (migrate), and *"eventually just remov[ed] the old scoped_ptr alias"* (contract) — *"consistently generating, testing and committing more than 700 independent changes, touching more than 15,000 files per day"* at peak. ([Software Engineering at Google, ch. 22](https://abseil.io/resources/swe-book/html/ch22.html))

### Where else it applies in Wayfarer's shape

**[inf]** `/to-tickets` already reaches for it for wide refactors. The survey says it generalises to **any seam two tickets share** — an interface, a schema, a config shape, an event payload, a CLI flag — not only to mechanical fan-out renames. The test is not "is this a rename?" but "would landing ticket A alone leave ticket B's code, or a caller, unable to compile or pass?"

**[inf] And it is the structural alternative to the effort branch, which is worth saying out loud.** Fowler's closing advice is *"make sure you understand the alternatives to branching, they are usually superior."* If every ticket in a slice can be expand–contract'd, no effort branch is needed at all: each ticket lands green on trunk. The effort branch exists precisely for the residue that cannot. **This suggests a design pressure, not a redesign:** the more `/to-tickets` uses expand–contract, the shorter and thinner the effort branch is, and the cheaper every cost in §3 becomes.

**[doc]** The DAG is the enforcement mechanism for the discipline problem. Sato's failure mode is "nobody runs the contract phase". In `/to-tickets`' prescription the contract is *a ticket blocked by every migrate batch* — so the graph makes contraction a node that Wayfarer's cascade must reach, not an intention. That is a genuinely good fit and worth keeping.

**Where it does not apply — [inf], the sources have no explicit exclusion section:** where the two states cannot coexist (a unique constraint, an exclusive lease, a singleton external resource, an invariant that dual-writing would violate), there is no valid "expanded" state, so there is no green intermediate. And where a compiler can find every caller atomically and the change is in-process, expand–contract is overhead — Sato positions it as *"an alternative to leaning on the compiler."*

---

## 5. Do independent components of a DAG need to serialise?

**The documented answer is no — and every tool decides it the same way, which is not the way Wayfarer would be tempted to.**

**[doc] Zuul** is the clearest doctrine: *"Projects that interact with each other should share a `queue`."* ([queue config](https://zuul-ci.org/docs/zuul/latest/config/queue.html)) and *"Any projects which interact with each other in tests should be part of the same shared queue in order to ensure that they don't merge changes which break the others… A given dependent pipeline may have as many shared change queues as necessary, so groups of related projects may share a change queue without interfering with unrelated projects."* ([project config](https://zuul-ci.org/docs/zuul/latest/config/project.html)) Changes in different shared queues run fully in parallel with **no serialisation at all**. Queue `type: per-branch` gives each branch its own shared queue.

**[doc] Mergify** productises the same idea as **scopes**: *"Mergify scopes describe the areas of your codebase that a pull request touches,"* derived by matching *"each pull request's changed files against your patterns"*, with `barrier_files` for files that affect every scope. Batching *"evaluates how many scopes each candidate shares… and prefers combinations with the highest overlap,"* because *"tests that run for one pull request are likely valid for the other changes in the batch."* And the strongest statement of all — **Direct Merge**: *"when a pull request is only behind the base branch by merges in scopes it does not touch, Direct Merge merges it right away, with no queue CI run at all."* ([scopes](https://docs.mergify.com/merge-queue/scopes/))

**[doc] Google's Rosie** shards by the same principle: *"Rosie takes a large change and shards it based upon project boundaries and ownership rules into changes that can be submitted atomically,"* with the one constraint that *"individual shards should be committable independently. This means that they don't have any interdependence or that the sharding mechanism can group dependent changes (such as to a header file and its implementation) together."* Validation is dependency-aware: *"We run every test that depends on the files in a given change transitively."* ([SWE at Google ch. 22](https://abseil.io/resources/swe-book/html/ch22.html))

**[doc] Uber's SubmitQueue** does conflict analysis to prune its speculation tree so non-conflicting changes are evaluated independently; the signal is the **build graph**, not a declared dependency.

### The trap, and it is a real one

**[inf, but well supported]** Every one of those systems derives independence from **what the change touches** — files, build targets, project boundaries, ownership — and **never** from an author-declared dependency edge. Wayfarer's blocking edges are a *semantic ordering* written by `/to-tickets` from a spec: "B cannot start until A exists". They are not a claim that A and B touch disjoint code, and nothing checks that they do. Two tickets with no edge between them can trivially both edit the same module.

So: **the absence of a blocking edge is not a safe licence to skip re-validation.** Using it as one would reintroduce exactly the semantic conflict Fowler names, with nothing to catch it, and #13's named risk (auto-merged code is built upon before a person reads it) would be the delivery mechanism.

**[inf] What follows for the design:**
- **One queue per effort branch.** Within a slice, all tickets came from one spec against one repo — by construction they are the "projects which interact with each other" of Zuul's rule. Serialise them.
- **Nothing serialises across efforts.** Separate effort branches are separate shared queues; two efforts landing at once need no coordination beyond Waystation's existing per-repo write lock. This is Zuul's `per-branch` queue type, documented, and it is free.
- **Use the ticket DAG for two things only:** the order to try landings in (most-unblocking first, per principle 6), and **which tickets to evict when one fails** (Graphite's rule). Not for deciding what to re-test.
- **If Wayfarer ever wants to skip re-validation for genuinely disjoint tickets, it must compute overlap from changed files, not from edges** — Mergify's `scopes.source: files` is the documented shape, and `barrier_files` is the documented escape hatch for files that touch everything.

---

## 6. Which practices assume a human author

This is the axis on which most of the surveyed practice fails, and it is worth being blunt about which parts of Wayfarer's design are therefore unsupported by precedent and which are actively supported.

**Assumes a live author — does not survive:**
- **Restacking**, in almost every tool. GitHub's nine documented stack failure modes all end in an author command; Graphite's `gt restack`, Phabricator's `arc`, and GitHub's `gh stack rebase` are interactive; `git spr` automates it only by owning one local linear series on one machine, and Arcanist's cascade rebase is *local-only, in the lander's working copy*.
  **The two partial exceptions are instructive.** Gerrit's **Rebase Chain** is a server-side REST action anyone with permission can invoke, and Graphite's server auto-rebases upstack branches after a merge. Both work because the heal happens *where the branches live*, not in someone's checkout. **[inf]** That is the shape Wayfarer would need if it ever wanted to start dependents early — and it is exactly the shape Wayfarer avoids needing by cutting dependents only after blockers land.
- **Conflict resolution.** Documented across all four stacking tools with no exception: every one halts and waits for interactive resolution, and none documents an automated policy. Gerrit's Rebase Chain returns `409 Conflict`; Graphite warns that `git rebase --abort` *"will not undo prior restack operations"*. **[inf]** Wayfarer's resolver run (ADR-0015) is therefore genuinely without precedent in this space — not wrong, but unsupported by prior art, which is worth stating rather than assuming.
- **"Kicked back to the creator"** (bors, on a single-PR batch that still fails) and **"removed from the queue"** (GitHub) both assume someone notices and acts. In Wayfarer these are events that must route somewhere — Needs you, or a new run.
- **Review-driven revision.** GitHub's own agent tutorial has the agent fix the flagged layer *because a person flagged it, in session*.

**Survives, and has direct documented precedent:**
- **Auto-merge by exception with one human gate.** This is close to Google's LSC review model: mechanical changes go to *"a 'global approver': someone who has ownership rights to approve any change throughout the repository"*, global reviewers use *"pattern-based tooling to review each of the changes and automatically approve ones that meet their expectations"*, and only anomalous cases get human eyes; *"it's cheaper to have a single expert understand the nature of the change."* Wayfarer's "`/code-review` finds nothing + CI green ⇒ merge, one human PR into trunk per effort" is the same trade with `/code-review` in the pattern-matcher's chair. **The survey supports #13's decision.**
- **Tests as the real gate.** Google's stance on machine-authored change is that testing, not review, is what makes it safe: on haunted graveyards, *"the solution is good, ol'-fashioned testing. When software is thoroughly tested, we can make arbitrary changes to it."* TAP runs *"every test that depends on the files in a given change transitively."*
  **[inf] Wayfarer has no dependency-aware test selection.** Without it, the only honest equivalent is **the full suite per landing candidate**. That is a cost #16 should state rather than discover.
- **Regenerate rather than repair.** Google's framing is the sharpest thing in the survey for an agent regime: LSC shards are *"cattle: nameless and faceless commits that might be rolled back or otherwise rejected at any given time with little cost."* A ticket branch is cattle. A resolver run that replays a preservation branch is repair; re-running the ticket agent from the *current* effort-branch head is regeneration, and for a **semantic** break (which is not a git conflict — Waystation will integrate it happily) regeneration is the better-supported move.
  **[inf] Concretely:** keep ADR-0015's resolver run for *textual* conflicts, which is what it actually describes; for a ticket that lands cleanly but breaks the effort branch's tests, prefer re-running the ticket against the new head over asking an agent to resolve. The ticket is cheap; the graph position is what is valuable.
- **`git rerere`** is the one documented mechanism that resolves conflicts without an author present. **[doc]** *"This command assists the developer in this process by recording conflicted automerge results and corresponding hand resolve results on the initial manual merge, and applying previously recorded hand resolutions to their corresponding automerge results,"* for *"a workflow employing relatively long lived topic branches"* — which is Wayfarer's workflow exactly. It must be explicitly enabled (`rerere.enabled`), and it can fail to record when the file already contains conflict-marker-like lines. ([git-rerere](https://git-scm.com/docs/git-rerere)) ADR-0015 already names it as a mechanical handler that belongs in a custom integration strategy; **[inf]** it is worth a look for the repeated-conflict case, where the same ticket is retried against a moving head.

**The property Wayfarer has that none of the stacking tools have:** because a dependent ticket is cut from the effort branch **after** its blockers land, no parent is ever amended underneath a child. The restack problem — the one thing that reliably needs a human — **does not arise**. That is not luck; it is the consequence of #13's decision that landing is what unblocks. It should be written down as an invariant, because the obvious performance optimisation (start dependents early, speculatively, on their blockers' unlanded branches) would destroy it and import every failure mode in §1.

---

## 7. Recommendation for this shape

1. **Keep the three levels. Rename the middle one's *model*, not its name.** The effort branch is a `next`-style graduated integration branch (`gitworkflows(7)`), not a feature branch. Record the three obligations that come with it: merge trunk in continuously; never rewind, rebase, squash or force-push it during the effort; budget and surface its age and size.
2. **Record the no-restack invariant.** A ticket branch is cut from the effort branch only once every blocker has landed. Never start a dependent speculatively on an unlanded blocker. This is what makes the whole design work unattended.
3. **The merge queue re-validates; it does not merely order.** Serial, depth-1: rebase/replay the candidate onto the current effort-branch head, run the suite, land exactly what was tested. This is the Not Rocket Science Rule at the scale Wayfarer operates at. **No speculative execution** until measured queue depth demands it.
4. **On failure, distinguish the two kinds, because they have different answers.** A *textual* conflict → resolver run (ADR-0015), escalate on second failure. A *semantic* break (clean merge, red suite) → evict the ticket **and its dependents** from the queue (Graphite's rule) and prefer **re-running the ticket agent at the new head** over resolving. Escalate to Needs you on the second failure either way.
5. **One queue per effort branch; no serialisation across efforts.** Zuul's shared-change-queue doctrine, and it is free.
6. **Do not use blocking edges to decide what to re-test.** Use them to order landings and to cascade evictions. If overlap-based skipping is ever wanted, compute it from changed files.
7. **Lean harder on expand–contract.** Every ticket that can be made independently green shortens the effort branch and cheapens everything in §3. Keep the DAG as the enforcement mechanism for the contract phase.
8. **Prefer ordering the landings in Wayfarer over GitHub's native merge queue, for this shape.** Native gives speculation, eviction and rebuild for free — but it needs a per-branch protection rule (no wildcards, repo-level only) created and torn down per effort, a `merge_group` workflow trigger, and a GitHub App for the events; and it gives flat FIFO eviction when Wayfarer needs dependent-cascading eviction. **[inf]** This is a judgement, not a documented fact, and #16 owns the final call — but the per-effort rule churn is the concrete cost that tips it.
9. **State the test-selection cost honestly.** Without dependency-aware test selection, "re-test each candidate" means the full suite each time. If that is too slow, the fix is test selection or batching (bors-style, with bisection), **not** speculation.
10. **Say plainly what has no precedent.** No surveyed system lands unreviewed machine-authored changes onto a branch that other machine authors then build on. Google comes closest and buys it with TAP and a global approver. Wayfarer's equivalents are `/code-review`'s finding gate, CI, and each dependent's own tests — the same three #13 already named. The survey does not contradict that; it does say those three are carrying more weight than they would in any human workflow.

---

## 8. What this survey rules out of the current design

**Ruled out — do not build these:**

1. **Modelling the ticket DAG as a stack of pull requests.** GitHub requires *"a fully linear history between every branch in the stack"* as *"a strict requirement for merging"*; `git spr` is a linear commit series; Graphite records exactly one parent per branch (a tree); Gerrit's Rebase Chain *"requires a linear ancestry relation (single parenting throughout the chain)"*. The only surveyed tool whose dependency edges form a real DAG is Phabricator's free-text "Depends on", and it cannot *land* along those edges — `arc land` follows working-copy ancestry instead. A diamond in the DAG cannot be expressed anywhere. **[doc]**
2. **Starting a dependent ticket before its blockers land.** It is the only thing that would force restacking. Restacking has an unattended answer in exactly two places — Gerrit's server-side Rebase Chain and Graphite's post-merge server job — and *neither* covers the conflict case, which every surveyed tool escalates to a human. **[doc]**
3. **Any rewrite of the effort branch during the effort** — rebase, squash-tidy, force-push, "clean up the history before shipping". Dependents are based on it, so it is `next`, and `gitworkflows(7)` is explicit that a branch you may never base work on is a *different* branch (`seen`), and that rewinding `next` is exceptional and announced. **[doc]**
4. **Treating "no blocking edge" as proof two tickets can land without re-validation.** Every system that skips serialisation derives independence from file/build-graph overlap (Zuul shared queues, Mergify scopes, Rosie's project-boundary sharding, SubmitQueue's conflict analysis), never from an author-declared dependency. **[doc for the mechanism, inf for the conclusion]**
5. **A merge queue that only orders writes.** Waystation's per-repo lock already does that (ADR-0005). The documented value of gating is testing each change *"exactly as it is going to be merged"*. A queue with no re-validation is a second lock. **[doc]**
6. **Speculative execution at this scale.** Not wrong in principle — wrong for single-digit bursts. Uber's own ICSE 2025 result cut CI resource usage ~53% by speculating *less*, citing *"a high rate of premature build aborts"*. **[doc]**
7. **Flat-FIFO eviction.** GitHub's queue removes only the failing PR and rebuilds the tail; it has no idea a queued ticket depends on the one that just failed. Wayfarer must cascade eviction to dependents itself. **[doc for GitHub's behaviour; [claim] for Graphite's better rule]**
8. **Claiming a measured cost for the long-lived branch.** There is no published cost-vs-age or cost-vs-size curve anywhere in this literature. The design may cite thresholds (DORA's <1 day / <3 branches, correlational; TBD's ≤2 days / 1 developer, a practitioner heuristic) and the *mechanism* (semantic conflict, refactoring suppression, variance) — but not a number. **[doc, by absence]**
9. **Gerrit-style whole-topic submission as the model for landing a slice.** Submittability is transitively closed over dependencies *and their topics*, so one stuck ticket blocks the set — the opposite of "a failed ticket stops nothing" (ADR-0007, principle behind the map). **[doc]**

**Explicitly NOT ruled out — the survey supports these:**

- **Three branch levels.** `gitworkflows(7)` documents a graduated integration branch and Fowler names the Team Integration Branch pattern for exactly this case.
- **Auto-merge by exception.** Google's LSC review model — a global approver plus pattern-based auto-approval, with tests as the real gate — is direct precedent for machine-authored changes landing without per-change human review.
- **A resolver run on conflict.** Nothing contradicts it; `git rerere` is a documented mechanical complement for the repeated-conflict case. The survey's one refinement is that it is the right answer for *textual* conflicts and the wrong one for *semantic* breaks, where regeneration ("cattle, not pets") is better supported.

---

## Sources

**Stacked changes**
- GitHub, *About / Reference: stacked pull requests* — <https://docs.github.com/en/pull-requests/reference/stacked-pull-requests>
- GitHub, *Merging stacked pull requests* — <https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-stacked-pull-requests>
- GitHub, *Troubleshooting stacked pull requests* — <https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-stacked-pull-requests>
- GitHub, *Stack AI-generated code in pull requests* — <https://docs.github.com/en/copilot/tutorials/stack-ai-generated-code-in-pull-requests>
- GitHub Changelog, *Stacked pull requests are now in public preview* (2026-07-30) — <https://github.blog/changelog/2026-07-30-stacked-pull-requests-are-now-in-public-preview/>
- `git spr` — <https://github.com/ejoffe/spr> (README and `git/commit.go`)
- Gerrit, *Submitting Changes Across Repositories by using Topics* — <https://gerrit-review.googlesource.com/Documentation/cross-repository-changes.html>
- Gerrit, *REST API — Rebase Chain / Submitted Together* — <https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html>
- Gerrit, *Project configuration* (submit types) and *Configuration* (`change.maxSubmittableAtOnce`) — <https://gerrit-review.googlesource.com/Documentation/config-project-config.html>, <https://gerrit-review.googlesource.com/Documentation/config-gerrit.html>
- Graphite CLI docs — <https://github.com/withgraphite/docs/blob/main/guides/graphite-cli/restacking-branches.md>, <https://github.com/withgraphite/docs/blob/main/guides/graphite-cli/command-reference.md>
- Graphite, *Merge pull requests* / *Merge queue optimizations* — <https://graphite.com/docs/merge-pull-requests>, <https://graphite.com/docs/merge-queue-optimizations>
- Graphite, *How we built the first stack-aware merge queue* — <https://graphite.com/blog/the-first-stack-aware-merge-queue>
- Phabricator, *How do I create a dependency between revisions?* — <https://secure.phabricator.com/Q396>; LLVM's Phabricator guide (multi-parent "Depends on") — <https://releases.llvm.org/18.1.6/docs/Phabricator.html>

**Merge queues and speculative execution**
- GitHub, *Managing a merge queue* — <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue>
- GitHub, *Available rules for rulesets* — <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets>
- bors-ng — <https://github.com/bors-ng/bors-ng> and <https://bors.tech/documentation/>
- Mergify, *Merge queue* / *Performance* / *Batches* / *Scopes* / *Two-step* — <https://docs.mergify.com/merge-queue/>, <https://docs.mergify.com/merge-queue/performance/>, <https://docs.mergify.com/merge-queue/scopes/>
- Zuul, *Project gating* — <https://zuul-ci.org/docs/zuul/latest/gating.html>
- Zuul, *Pipeline* and *Queue* configuration — <https://zuul-ci.org/docs/zuul/latest/config/pipeline.html>, <https://zuul-ci.org/docs/zuul/latest/config/queue.html>, <https://zuul-ci.org/docs/zuul/latest/config/project.html>
- Juloori, Lin, Williams, Shin, Mahajan, *CI at Scale: Lean, Green, and Fast* (ICSE 2025) — <https://arxiv.org/abs/2501.03440>
- uber/submitqueue — <https://github.com/uber/submitqueue>
- "Not Rocket Science Rule" wording (secondary) — <https://huonw.github.io/blog/2015/03/rust-infrastructure-can-be-your-infrastructure/>

**Branching, trunk-based development, integration branches**
- `gitworkflows(7)` — <https://git-scm.com/docs/gitworkflows>
- `git-rerere(1)` — <https://git-scm.com/docs/git-rerere>
- Fowler, *Patterns for Managing Source Code Branches* — <https://martinfowler.com/articles/branching-patterns.html>
- Fowler, *FeatureBranch* — <https://martinfowler.com/bliki/FeatureBranch.html>
- Fowler, *BranchByAbstraction* — <https://martinfowler.com/bliki/BranchByAbstraction.html>
- trunkbaseddevelopment.com — <https://trunkbaseddevelopment.com/>, <https://trunkbaseddevelopment.com/short-lived-feature-branches/>, <https://trunkbaseddevelopment.com/branch-for-release/>, <https://trunkbaseddevelopment.com/continuous-integration/>
- DORA, *Trunk-based development* and research method — <https://dora.dev/capabilities/trunk-based-development/>, <https://dora.dev/research/2019/structural-equation-model/>

**Expand–contract and machine-authored change at scale**
- Sato, *ParallelChange* — <https://martinfowler.com/bliki/ParallelChange.html>
- Fowler, *Evolutionary Database Design* — <https://martinfowler.com/articles/evodb.html>
- Winters, Manshreck, Wright, *Software Engineering at Google*, ch. 22 "Large-Scale Changes" — <https://abseil.io/resources/swe-book/html/ch22.html>

**Local sources**
- `../waystation/docs/adr/0005-integration-strategy-and-conflicts.md`, `0006`, `0007`, `0015`
- `~/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/engineering/to-tickets/SKILL.md` (the wide-refactor / expand–contract paragraph)
- `CONTEXT.md` (effort branch, merge queue, landed, shipped), `docs/design/principles.md` (principle 6)
