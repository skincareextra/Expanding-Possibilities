# Pre-Launch Integration Cost Policy

**Default state:** PRE-LAUNCH / PAID INTEGRATIONS OFF.

Until an authorized launch decision is recorded, this repository must treat every billable external integration as disabled by default.

## Required defaults

- `PRELAUNCH_MODE=true`
- `LAUNCH_APPROVED=false`
- `PAID_INTEGRATIONS_ENABLED=false`

## OFF before launch

Do not run recurring or background activity that can create provider charges, including:
- AI/model inference, embeddings, transcription, image/video generation
- SMS/MMS/voice/email delivery providers
- browser workers, agents, crawlers, enrichment or monitoring workers
- paid API polling/sync, webhook enrichment, data exports/imports
- scheduled integration jobs, queues, pub/sub consumers that invoke paid services
- always-on compute used only to keep an integration warm
- production analytics/warehousing jobs not required for development

## Allowed before launch

Keep only what is necessary to build safely and preserve data:
- source control and local/dev tests
- security/static validation
- canonical database/data backups where data already exists
- authentication required for development
- secrets/configuration storage
- manual, bounded integration tests explicitly triggered for verification

## Launch gate

A paid integration may turn on only when ALL are true:
1. `LAUNCH_APPROVED=true` is an explicit owner decision.
2. A monthly budget/cap exists.
3. The integration has a named owner and purpose.
4. Scale/concurrency/rate limits are explicit.
5. Scheduled jobs are bounded and justified.
6. Rollback/kill-switch behavior is documented.
7. The expected monthly cost is recorded.

**Fail closed:** missing launch configuration means OFF. Never infer launch from deployed code, available credentials, a production URL, or a configured secret.
