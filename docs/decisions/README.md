# Architecture decision records

Use this directory for future architecture decision records (ADRs). The repository does not reconstruct historical decisions without evidence; current behavior is documented in the main technical documents.

## When to add an ADR

Add an ADR when a change makes a durable, cross-cutting choice such as replacing SQLite, changing the one-guild command model, introducing a worker/process boundary, changing configuration ownership, or adopting a new persistent-view strategy. Routine fixes and local implementation details do not need an ADR.

## File naming

Use the next number and a short kebab-case title:

```text
0001-example-decision.md
```

Never renumber existing records. Supersede an old decision with a new ADR and link both records.

## Template

```markdown
# ADR-NNNN: Decision title

- Status: proposed | accepted | superseded
- Date: YYYY-MM-DD
- Owners: role or team, without personal data

## Context

Describe the verified problem, constraints, and forces.

## Decision

State the chosen approach precisely.

## Alternatives considered

Record realistic alternatives and why they were not selected.

## Consequences

List positive and negative operational, development, data, and migration effects.

## Verification and follow-up

State how the decision will be validated and any follow-up work.
```

Keep ADRs in English, link to relevant code and documentation, and anonymize Discord identifiers and operational data.
