# Security policy

Read the [privacy and data handling policy](docs/en/privacy.md)
([日本語](docs/ja/privacy.md)) before using personal trading data or session mining.
It documents local storage, external providers, redaction limits, retention and
[tested backup/restore](docs/dev/thesis-backup-restore.md).

## Reporting a vulnerability

At the 2026-11-14 capability check, GitHub private vulnerability reporting was
**disabled** for this repository. There is no documented private security mailbox.
Do not post vulnerability details, exploit payloads, credentials or personal data
in public Issues or PRs. If GitHub's private reporting form is available when you
report, use it; otherwise open only a minimal contact request without sensitive
details to arrange a private channel with the maintainer. That request is public
and is not itself a confidential report. Private reporting/scanning setup remains
separate work (#611); this document does not enable it or promise a response SLA.

If a key has leaked, revoke/rotate it with its provider promptly. Removing a file
from the latest commit does not erase copies, Git history or published artifacts.
Do not include the key in a report.

## Supported code and runtimes

| Code line | Security-fix policy |
| --- | --- |
| Current `main` | Target for fixes; validate the exact updated snapshot |
| Historical commits / copied skill packages | No separate maintained fix branch; update and revalidate |

Security fixes target the current `main` branch. Older snapshots and independently
copied skill packages have no separate maintained security-fix branch commitment;
update and revalidate before use. No GitHub Releases were listed at the above
check; do not infer a maintained version line from that observation.

The canonical [Python support configuration](config/python-support.json) defines
root development/CI as Python `>=3.11.5,<3.14` and standalone skill compatibility
with a Python 3.9 minimum. Compatibility is not a promise
of upstream security maintenance for every Python version. Choose a runtime still
receiving upstream security updates and follow the canonical configuration for
actual tested versions. CI is evidence for the tested snapshot, not a guarantee
that an integration, credential, or broker operation is safe.

## Contribution controls and limits

Install both repository pre-commit and pre-push hooks. The private-path guard
checks the whole active Git index, including forced additions and alternate
indexes; root CI tests also audit the checkout index. It permits only the two
empty regular `state` placeholders. It does not scan arbitrary contents or protect
private data placed in public fixture paths. Secret-scanning exclusions and
external model/tool disclosures are described in the privacy policy.

Use fictional fixtures in public tests and reviews. Never attach real account
exports, session transcripts, provider payloads or recovery copies to a PR.
