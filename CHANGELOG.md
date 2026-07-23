# Changelog

## [0.3.0](https://github.com/form-function-labs/janus/compare/v0.2.0...v0.3.0) (2026-07-23)


### Features

* **cli:** doctor preflight — validate claude auth/binary/home (FOR-569) ([5b03acc](https://github.com/form-function-labs/janus/commit/5b03acc578d0da8f7cc3536e88fd87a9996b1e14))
* **cli:** doctor preflight — validate claude auth/binary/home (FOR-569) ([6075b5b](https://github.com/form-function-labs/janus/commit/6075b5b688ec54702fa104fc2dd85beebd2443be))
* **cli:** ignore command — durable JANUS_IGNORE_PATTERNS management (FOR-568) ([3a692e4](https://github.com/form-function-labs/janus/commit/3a692e4dc15e9177cb4254c268b76d56f82e670e))
* **cli:** ignore command — durable JANUS_IGNORE_PATTERNS management (FOR-568) ([21cc7da](https://github.com/form-function-labs/janus/commit/21cc7dab8a19462ca34a97fbbaedd6dbc3d1ce5b))
* **corpus:** durable transcript archive + request-side noise filter ([8cc1890](https://github.com/form-function-labs/janus/commit/8cc1890893f76ec095c7ed064afb045ff2467d88))
* **harvest:** configurable JANUS_IGNORE_PATTERNS + show proposed edits in report ([7ddd245](https://github.com/form-function-labs/janus/commit/7ddd24540f38f10aa4c6fd7848f0b2a06b0d9839))
* **harvest:** extract (request, correction) candidate pairs from transcripts ([2f9daac](https://github.com/form-function-labs/janus/commit/2f9daac15bb2f881be239dcafe5db66d124c0470))
* initial Janus v0.1 — gated memory-REM optimizer for Claude Code ([bb72dff](https://github.com/form-function-labs/janus/commit/bb72dff22101562fd81dfbfb852bafd8f2bf5aac))
* **mine:** correction-driven optimization (Haiku classifier + rubric judge) ([22b64b5](https://github.com/form-function-labs/janus/commit/22b64b5cda44f199caf248ae32ec7e077db9e8c5))
* **surfaces:** generalize text-state to memory, skills, and CLAUDE.md ([e4f56c0](https://github.com/form-function-labs/janus/commit/e4f56c08420fc705aa32e9623ecf091675de9a1c))
* **worker:** JANUS_JUDGE_MODEL — split the judge model from the executor ([7cdbb40](https://github.com/form-function-labs/janus/commit/7cdbb40ba46a520b44ec9c9211bee5875bf06abb))
* **worker:** JANUS_TIMEOUT knob + non-fatal rollout timeouts (D1) ([ff215cd](https://github.com/form-function-labs/janus/commit/ff215cd4fb65d2f8d79e30423566b50217e8e13e))


### Bug Fixes

* **cli:** warn on stale staged proposals at run start (D3) ([30d8da9](https://github.com/form-function-labs/janus/commit/30d8da9daffd003bb2abe41bc95227201af21d5c))
* **harvest:** filter harness-injected text from mined intents ([7130aa0](https://github.com/form-function-labs/janus/commit/7130aa07b15a373641381ada315d617ef13c9975))
* **optimizer:** fence document vs evidence + thread correction lessons into reflect ([610b2bd](https://github.com/form-function-labs/janus/commit/610b2bdcd34c9194f37e04490103b9d0fb319b65))
* **store:** harden IgnorePatternStore — atomic writes, validation, dedupe-on-write ([6a7767d](https://github.com/form-function-labs/janus/commit/6a7767df7b3bcba1b55d92804b9325fcbba1370c))
* **worker:** auth failures are indistinguishable from other exit-1s (D2) ([fa74e0a](https://github.com/form-function-labs/janus/commit/fa74e0acbb070bfd485bab8c561d06b0edfa67e1))
* **worker:** D1-D3 hardening — timeout knob, auth diagnostics, stale-staging warning ([8dbe1f7](https://github.com/form-function-labs/janus/commit/8dbe1f7a81734b157207b91839d046d998518199))
* **worker:** probe_auth always yields an actionable failure reason; tighten doctor tests ([bc73356](https://github.com/form-function-labs/janus/commit/bc73356832b703a8873b8d14f539a9839a9d251c))


### Documentation

* update README for corrections, surfaces, corpus durability ([c3cbec2](https://github.com/form-function-labs/janus/commit/c3cbec2765ebcd3192eb0cd6deb2f17f2d2ad80c))

## [0.2.0](https://github.com/form-function-labs/janus/compare/v0.1.0...v0.2.0) (2026-07-23)


### Features

* **cli:** doctor preflight — validate claude auth/binary/home (FOR-569) ([5b03acc](https://github.com/form-function-labs/janus/commit/5b03acc578d0da8f7cc3536e88fd87a9996b1e14))
* **cli:** doctor preflight — validate claude auth/binary/home (FOR-569) ([6075b5b](https://github.com/form-function-labs/janus/commit/6075b5b688ec54702fa104fc2dd85beebd2443be))
* **cli:** ignore command — durable JANUS_IGNORE_PATTERNS management (FOR-568) ([3a692e4](https://github.com/form-function-labs/janus/commit/3a692e4dc15e9177cb4254c268b76d56f82e670e))
* **cli:** ignore command — durable JANUS_IGNORE_PATTERNS management (FOR-568) ([21cc7da](https://github.com/form-function-labs/janus/commit/21cc7dab8a19462ca34a97fbbaedd6dbc3d1ce5b))
* **worker:** JANUS_TIMEOUT knob + non-fatal rollout timeouts (D1) ([ff215cd](https://github.com/form-function-labs/janus/commit/ff215cd4fb65d2f8d79e30423566b50217e8e13e))


### Bug Fixes

* **cli:** warn on stale staged proposals at run start (D3) ([30d8da9](https://github.com/form-function-labs/janus/commit/30d8da9daffd003bb2abe41bc95227201af21d5c))
* **store:** harden IgnorePatternStore — atomic writes, validation, dedupe-on-write ([6a7767d](https://github.com/form-function-labs/janus/commit/6a7767df7b3bcba1b55d92804b9325fcbba1370c))
* **worker:** auth failures are indistinguishable from other exit-1s (D2) ([fa74e0a](https://github.com/form-function-labs/janus/commit/fa74e0acbb070bfd485bab8c561d06b0edfa67e1))
* **worker:** D1-D3 hardening — timeout knob, auth diagnostics, stale-staging warning ([8dbe1f7](https://github.com/form-function-labs/janus/commit/8dbe1f7a81734b157207b91839d046d998518199))
* **worker:** probe_auth always yields an actionable failure reason; tighten doctor tests ([bc73356](https://github.com/form-function-labs/janus/commit/bc73356832b703a8873b8d14f539a9839a9d251c))
