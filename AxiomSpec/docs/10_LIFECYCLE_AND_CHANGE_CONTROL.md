# Lifecycle and change control

### AX-L-001 — Identity and revision

An ID denotes a stable concept. Increment revision when normative content changes. A new incompatible meaning needs a new ID and explicit migration. Draft/active/retired describe the model, not authenticated approval. Keep historical retired objects; never reuse their IDs.

## Change request

Record problem, baseline, intended observable result, affected requirements/files, exclusions, material decisions, risk, compatibility, tests and recovery where relevant. Distinguish additions, retirement, wording, unit/domain changes, constraints, relationships, bindings and policy. Text diff alone does not establish business impact. The release comparison below lists changed IDs mechanically; it does not replace the statement of intent.

### AX-L-002 — Fixed baseline

Bind work to baseline and candidate digests. Rebase or reject an application if the source changed. A local revision counter is not compare-and-swap. A single writer and atomic local replacement may be sufficient initially; qualify the actual mechanism rather than introducing distributed transactions.

## Responsibilities

| Phase | Output | Authority question |
|---|---|---|
| Explore | Sources and alternatives | Who supplied the need? |
| Clarify | Terms and decisions | Who may decide consequences? |
| Design | Model and verification plan | Which checks does policy require? |
| Implement | Code and tests | What scope and tools are authorized? |
| Accept | Evidence and residual decisions | Who accepts the remaining risk? |
| Operate | Observations and incidents | Who may revise the contract? |

One author can contribute to multiple phases. Policy determines any required separation. Autonomous execution concerns cadence, not authority; retain the task's execution declaration and policy digest with each change packet.

### AX-L-003 — Trusted policy controls exemptions

Policy defines required gates, risk floors, rights, runners and decision authority. A specification may propose classification but cannot waive its own obligations. Policy changes require their own authorized process. Local unauthenticated mode cannot establish real identities from names.

### AX-L-004 — Conservative invalidation

Canonical changes invalidate product acceptance evidence. Code, tests, environment, policy and tool changes invalidate dependent results; use global invalidation when dependency coverage is not qualified. Matching inputs and acceptable observation age are separate requirements. A cache is an optimization, never authority.

### AX-L-005 — Declared migrations

Reject or report unsupported format versions. Never silently discard unknown fields. State source/target versions, transformations and decisions that cannot be automated. Preserve the source, produce a candidate, show the diff and rerun checks.

The migration from 0.1 to 0.2 adds the release record, the weight units, a weight and a flag reference on each requirement and flag states on each test. It cannot know the weights: it sets each to the top of the band its risk label names. It creates an enabled flag for each optional requirement. Both are placeholders, listed for a person to decide, and missing flag-state tests remain a visible failure.

The migration from 0.2 to 0.3 adds the approval policy, the keys, the imports and the exports. It writes a policy of no approver in any band and no key, which is valid and visible and is for the organization to replace. A migrated release has a new digest, so a migrated successor names its migrated baseline.

A structural migration does not decide a new business policy. API compatibility, data migration, mixed-version operation and rollback are product requirements to verify separately.

## Publication and recovery

Generate product views in a new immutable snapshot, verify its manifest and atomically switch the published pointer. Interrupted generation retains the last complete snapshot. Returning to an old version requires compatible specification, code, policy and data, not just restored Markdown.

A recovery journal retains change ID, baselines, completed work, actual commands, stale evidence and next action. It is navigation evidence, not self-authentication.

An emergency process must already be defined by policy with authority, scope, retained checks, accepted gaps, duration and follow-up. An urgent issue does not create an exemption. Record exceptions as exceptions rather than passed original checks.

## Releases

A specification changes in releases. Comparing a candidate release with the baseline it names is gate G14. The comparison is deterministic and reads two documents; it runs nothing.

### AX-L-006 — Release identity

The candidate names its baseline in `release.previous` by version and canonical digest, and belongs to the same project. A comparison against any other document is refused. Objects are matched by ID, never by title or position:

- a node present in the baseline is still present: retire it, never delete it;
- a node keeps its kind;
- a revision never decreases, and it increases whenever anything else in the node changed;
- a retired node stays retired.

Environments, flags, edges, bindings, assets, actors and sources carry no status. They may be added or removed, and the removal is classified.

### AX-L-007 — Compatibility classification

Each changed object gets the highest level any of its changes reaches.

| Level | Change |
|---|---|
| major: breaking candidate | An active requirement retired or withdrawn; the rendered statement of a must requirement changed; a must lowered to should or could; an active requirement put behind a disabled flag. An active hard constraint whose predicate, environment, effective window, scope or strength changed, or which was withdrawn; a new hard constraint on a requirement the baseline already had. A state or transition of an active model removed or changed. The unit of a term changed. An environment removed, changed so that observations valid before may be rejected, or given different unit annotations. A flag switched from enabled to disabled, or its key renamed. |
| minor | An active goal, requirement, constraint, model, term, decision, assumption, risk or control added, or one of these other than a requirement, hard constraint or model withdrawn. A requirement raised to must, changed when it is not a must, or given a different flag without turning active behavior off. A soft constraint changed. A state or transition added. A term definition, a decision answer or the content of a goal, assumption, risk or control changed. An environment added or widened. A flag added or switched on. The project mode changed. |
| patch | Everything else: titles, weights, tests, scenarios, components, links, bindings, context assets, actors, sources, a removed flag and objects not active in either release. |

The classifier is mechanical and conservative. It cannot tell a tightened formula from a relaxed one, so both are candidates, and a predicate that only writes down what a requirement already said is a candidate too.

A breaking candidate is never settled silently. `release.compatibility` holds one entry per candidate: `breaking`, with a migration statement, or `compatible`, which lowers that change to minor. Either rests on an active Decision with an answer. A candidate without an entry fails the comparison, and so does an entry that matches no candidate, so approvals cannot outlive the change they were given for. Who was entitled to answer is G12's question, not this gate's.

The classification concerns the specification. Whether a deployed API, stored data or a mixed-version rollout tolerates the change is verified on the product.

### AX-L-008 — Version step

The required step is the highest level among the changes after recorded overrides. The declared step, from the baseline's version to the candidate's, is at least the required one and is exactly one step. A larger step than required is allowed. Versions below 1.0.0 follow the same rule.

### AX-L-009 — Change risk score

The score answers one question before review: how much of what matters does this release touch?

1. For each change, find the requirements it concerns through declared links: the requirement itself; a constraint's `formalizes`, a component's `implements`, a test's `verifies`, a scenario's `illustrates` and a model's `models` targets; the requirements that satisfy a goal, use a term, assume an assumption or realize a control; the targets a decision governs or a risk threatens; the users of a changed environment; the requirements behind a changed flag; both ends of a changed link; the node of a changed binding or asset.
2. Each requirement active in either release takes the highest factor among the changes that reach it: 100% for major, 50% for minor, 10% for patch, after recorded overrides.
3. A requirement connected by `depends_on`, in either direction and to a fixed point, takes 25% or the factor of the requirement it was reached from, whichever is lower.
4. The score is the sum of weight times factor.

The result is an integer `score_minor` with `score_minor_units` equal to the weight units times 100, so that percentages stay exact. A weight of 700 at 10 units per point reached at 50% contributes 35000 at 1000 units per point: 35 points. When the two releases use different weight units the finer one is used, and a requirement whose weight changed counts with the larger value. The report also gives the share of the total active weight in thousandths.

A change that reaches no requirement through declared links is listed as unmapped; it is not counted as zero risk. Hard project rules are not added to this closure as they are to context closure (AX-K-010), because they would add the same requirements to every change.

The score ranks releases and changes for attention. It never changes a gate result (AX-K-005), and a low score is not evidence of safety: it sees declared links and weights that people chose. Policy may demand more review above a threshold. It cannot use the score to waive a check.

### AX-L-010 — Release store

A release is immutable and is named by the digest of its canonical form. A store is any set of release files and approval files: a directory, a repository, an object bucket, or the union of several.

- **No shared state.** There is no index, log, ordering service, quorum or clock. The verdict on a release needs that release, its approvals, its baseline and the releases it imports.
- **The verdict is a function of the set.** The order in which files arrived and the replica that supplied them cannot change it. Two stores merge by taking the union of their files, and a file received twice changes nothing.
- **Absence is unknown.** A release whose baseline, approvals or provider is not in the store is unknown, never passed and never failed. When the file arrives, the verdict completes.
- **Each release has its own status.** A failed release, or a file that cannot be read, withholds nothing from the others.
- **A broken store file is named.** A file that says it is a release, a parts manifest or an approvals file and cannot be read as one (too large, not strict JSON, not valid) is listed with its reason, and the store is incomplete until it is repaired or removed. It is never skipped in silence. A file of any other format is ignored, and nothing is read below a name that starts with a dot, where a writer stages a file before moving it into place.

The head of a project is its highest version, whatever its status. Its accepted head is its highest release whose own status is pass, and is absent when none passes. A release that was refused, or that still waits for its approvals, can be the head; it is never the accepted head. A tool that needs the release a project stands on takes the accepted head.

When two different releases of one project hold its highest version, the store reports a fork. Nothing is lost: both stay verifiable by digest and every pin on either still resolves. Where a tool needs a single answer it takes the one with the smaller digest, so every replica takes the same one. The fork is settled by an ordinary approved release that names one of the two. Its line then holds the highest version and the other is listed as an orphaned head. The store never deletes a file.

There are no witness services. Every successor names its baseline by digest and every consumer names its providers by digest, each under the signatures of its own approvers. Anyone who pinned a release cannot be shown another in its place.

A store cannot show that it is complete or current. Withholding the newest release is not detectable from the files that are present; a consumer that needs a particular release pins it. The chain verifies link by link back to a first release, which governs itself: pin that digest through a channel the organization trusts.

### AX-L-011 — Impact across specifications

When a provider moves from one release to the next, the comparison of the two (G14) is followed into the specifications that import it.

1. A use is reached when the ID it names changed, or when a change is linked to it by the provider's declared links, at the highest level among those changes. An ID withdrawn from the exports is reached at major.
2. In the consumer, the local objects of a reached use lead to requirements as in AX-L-009.
3. Each such requirement counts as a dependent does within one specification: its weight times the factor of the level, at most 25%.

The report lists each consumer with its pin, the uses reached, the local requirements and a score in the consumer's own units. It examines the accepted head of each project in the store, or its head when no release of the project passes there, and follows declared uses only.

Moving a pin is a change of the consumer and is classified from the provider's version number: to a later major version, backwards or to another provider is a breaking candidate; to a later minor version, or to other content under the same version, is minor; to a later patch is patch.
