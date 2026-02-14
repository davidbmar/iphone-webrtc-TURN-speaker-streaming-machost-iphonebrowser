# Project Memory

Every coding session and architectural decision is traceable and searchable.

## Session ID Format

```
S-YYYY-MM-DD-HHMM-<slug>
```

- **HHMM** is UTC (use `date -u +%Y-%m-%d-%H%M`)
- **slug** is a short kebab-case descriptor
- Example: `S-2026-02-14-1430-tts-webrtc-pipeline`

## How It Links Together

```
Session → Commits → PRs → ADRs
   ↑                        |
   └────────────────────────┘
```

- **Session docs** describe what you worked on and why
- **Commits** reference the Session ID in the body
- **PRs** reference Session IDs and link to session docs
- **ADRs** capture significant architectural decisions

## Directory Structure

```
docs/project-memory/
├── .index/              ← Auto-generated search indices
├── sessions/            ← One file per coding session
│   └── _template.md
├── adr/                 ← Architecture Decision Records
│   └── _template.md
├── architecture/        ← System design docs
├── runbooks/            ← Operational procedures
├── backlog/             ← Feature backlog
└── index.md             ← This file
```

## Creating a Session

```bash
SESSION_ID="S-$(date -u +%Y-%m-%d-%H%M)-my-feature"
cp docs/project-memory/sessions/_template.md \
   docs/project-memory/sessions/$SESSION_ID.md
```

Fill in: Title, Goal, Context, Plan. Update after work: Changes Made, Decisions.

## Commit Messages

```
Human-readable subject line

Session: S-YYYY-MM-DD-HHMM-slug
```

The pre-commit hook auto-rebuilds the search index.

## When to Create an ADR

- Choosing between technical approaches
- Establishing patterns for the codebase
- Decisions with long-term consequences
- Significant architectural changes

## Searching

```bash
# Find commits for a session
git log --all --grep="S-2026-02-14"

# Search sessions by keyword
grep -r "keyword" docs/project-memory/sessions/

# Search ADRs
grep -r "topic" docs/project-memory/adr/

# Use the generated index
cat docs/project-memory/.index/keywords.json | python3 -m json.tool
```
