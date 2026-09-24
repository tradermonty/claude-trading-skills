# Documentation site CI

Tracking: [Issue #337](https://github.com/tradermonty/claude-trading-skills/issues/337).

## What runs on each pull request

The `Docs site` workflow builds the complete `docs/` tree with Jekyll's
`--strict_front_matter` option. It then rejects:

- malformed frontmatter, duplicate canonical permalinks, and missing or
  non-reciprocal `lang_peer` relationships;
- rendered links to missing pages or anchors;
- missing local images, scripts, stylesheets, media, iframe/object targets,
  `srcset` candidates, and CSS `url(...)` assets.

The rendered `_site` directory is uploaded as the `docs-site` workflow artifact
for 14 days. This build-and-link gate complements the skill-catalog parity gate
from #327: catalog parity checks source completeness, while this gate checks the
site Jekyll actually emits.

## Locked Pages toolchain

CI uses Ruby 3.3.9 and the committed `docs/Gemfile.lock`. The Gemfile constrains
`github-pages` to the v232 line and `just-the-docs` to v0.12. The Pages gem pins
Jekyll 3.10.0 and the plugin versions used by GitHub Pages. The `remote_theme`
reference is also fixed to the exact commit behind just-the-docs v0.12.0 rather
than its mutable tag. Dependabot owns weekly Bundler updates under `/docs`.

There are two deliberate differences from the hosted GitHub Pages runtime:

1. CI pins the Ruby interpreter rather than assuming the current hosted Ruby.
2. Just the Docs is both a locked build dependency and a `remote_theme` fixed at
   an immutable commit; the hosted service may update its underlying Ruby
   runtime without changing this repository's lockfile.

That makes the selected theme content reproducible while retaining compatibility
with the published `remote_theme` configuration. Dependency installation and the
Jekyll build require network access because the plugin downloads that immutable
commit; source, allowlist, and rendered-link validation are offline. When
updating the toolchain, change the Gemfile constraint, remote-theme commit, or
Ruby patch version, regenerate the lock on Linux with the committed platforms,
run the commands below, and review the built artifact.

## Local validation

From the repository root:

```bash
uv sync --locked --no-install-project
uv run --locked --no-sync python scripts/check_docs_site.py source
uv run --locked --no-sync python scripts/check_docs_site.py allowlist
cd docs
bundle config set path vendor/bundle
bundle install
bundle exec jekyll build --strict_front_matter --trace --destination ../_site
cd ..
uv run --locked --no-sync python scripts/check_docs_site.py internal \
  --site-dir _site --config docs/_config.yml
```

The local build output, Bundler install directory, and Jekyll caches are ignored.
`docs/Gemfile.lock` is not ignored and must remain committed.

## Scheduled external links

External HTTP(S) links are checked only by the weekly schedule or a manual
workflow dispatch, not during pull requests. The checker:

- retries transient failures with bounded timeouts, redirects, and response
  reads;
- rejects credentials and any DNS answer or redirect hop that reaches a
  non-public address, then pins the connection to a validated address while
  preserving the original TLS SNI and HTTP Host;
- caches only successful results for seven days; and
- writes a machine-readable `docs-external-links` artifact even when the job
  fails.

Temporary exclusions live in `config/docs-external-link-allowlist.json`. Every
entry must name the exact URL, a reason, an owner, a GitHub Issue URL, and an ISO
`expires_on` date. Expired or malformed entries fail pull-request validation
before the scheduled network check runs. Do not use the allowlist for internal
site links. Same-host absolute links within this project's configured `baseurl`
are normalized and checked against the current build on every pull request;
links outside that baseurl may target another GitHub Pages project and go
through the scheduled external check.
