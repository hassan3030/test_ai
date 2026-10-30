# Directus snapshot: Marketing Content

Schema shape only. No row data, no PII, bearer tokens redacted.

Regenerate with:

    node scripts/marketing-content/09-snapshot.mjs

Diff a prod clone against this:

    node scripts/marketing-content/09-snapshot.mjs --out=/tmp/prod-clone
    node scripts/marketing-content/09-snapshot.mjs --diff=/tmp/prod-clone

Policy ids are stored as LOGICAL NAMES (public / authenticated / manager)
because the uuids differ between instances.

| File | Contents |
|---|---|
| collections.json | the 8 new collections and their meta |
| fields.json | fields in the new collections, plus only the fields we add to existing ones |
| relations.json | relations touching our collections |
| permissions.json | permission rows on our collections, keyed by logical policy |
| flows.json | the 3 Marketing Content flows with operations, resolve/reject as keys |
