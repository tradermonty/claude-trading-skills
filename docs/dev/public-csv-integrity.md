# Public CSV integrity: scoped #332 plan and verification

Tracking: [#332](https://github.com/tradermonty/claude-trading-skills/issues/332).
This slice hardens provider-contract parsing and canary reports. It does not
complete the umbrella's provider inventory, change individual skill parsers,
promote report-only workflows, or change live repository settings.

## Final plan

The plan was independently reviewed twice. The only correction clarified that
module import/summary paths are stdlib-only, while the offline contract check
continues to use its existing PyYAML dependency and does not require requests.

1. Reproduce the current acceptance of duplicate headers and an unclosed quoted
   numeric cell. Add offline parser and real-fetch/fake-HTTP regressions first.
2. Validate header identity before DictReader collapses columns: fixed fatal
   blank_header/duplicate_header, without repairing names or logging their data.
3. Enable strict quoting and reject NUL consistently across supported Python
   versions. Reuse the fetch wrapper's parse_error path, discarding every row
   on a parse error, including a valid prefix.
4. Exercise each of the four recorded CSV endpoints as the single corrupted
   response among valid ones. Require a complete compatibility report, explicit
   failure, response cleanup, one call per endpoint and healthy other entries.
5. Preserve valid fixtures, BOM, CRLF, quoted commas/newlines/escaped quotes,
   exact case-sensitive field names, short/extra-row rules and existing coercion.
6. Run independent code review, focused and integration checks, all-files
   pre-commit and standard pre-push tests before publishing the PR. Refs #332;
   keep the umbrella open and make no live provider calls.

## Evidence and limits

On the base revision fdfff010, `value,value` with values `999,1` returned only
`value: 1` and no anomaly. An unclosed quoted numeric value also became a valid
number. The initial new regression set had 35 failures and 12 passes before the
fix. The final tests also duplicate actual required fields with valid-looking
values and remove the final closing quote from an otherwise complete fixture:
HTTP 200 and plausible field values must not conceal the structural defects.

The parser keeps no rows for invalid headers. A syntax/NUL/field-size failure
raises csv.Error; the fetch wrapper maps that to parse_error without leaking the
body or using partial rows. Valid header-only and empty responses retain the
existing non-empty validation route. Invalid header reports may also include
empty_response; the fatal header code supplies the structural cause.

Tests use bundled recorded fixtures and deliberately corrupted variants with
fake HTTP responses. They establish offline contract/report behavior, not
current provider availability or that every runtime consumer rejects these
inputs. Public canary scheduling and its report-only policy are unchanged.
