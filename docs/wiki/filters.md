# Filters

[Wiki home](README.md) | [Examples](examples.md) | [Troubleshooting](troubleshooting.md)

Select independently from Sector, Threat actor, Social engineering, Access & exploitation, Malware & impact, Other styles, and Education combinations. **All** leaves that scope unrestricted.

Every selected scope must match. Keywords/aliases within an option provide alternatives; combination rules can require both concepts. These are text rules, not AI judgments or guarantees of relevance. See the exact [catalog and matching rules](../SCOPES.md).

```sh
sh scripts/server.sh filters
```

`scope` is an alias. Windows uses Dashboard filters. Start with All, preview, and narrow one scope at a time; combining many scopes can legitimately produce no results.

Filtering precedes AI/delivery and nonmatches do not consume the cap. It applies to normal checks, previews, AI tests, and resend tests. Every Docker destination shares the filters. Changed filters can reconsider previously excluded articles without repeating acknowledged deliveries in normal mode. Cached reports are checked against changed filters.

Older sector-only settings migrate with the six new scopes at All.

Implementation: [matching](../../osint_digest/core/scopes.py). Evidence: [scope tests](../../tests/test_scopes.py).
