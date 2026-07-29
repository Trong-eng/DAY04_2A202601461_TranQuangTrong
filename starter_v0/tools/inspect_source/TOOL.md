---
name: inspect_source
track: core
kind: live_api
provider: Public website HTTP
requires_env: []
inputs: [url]
outputs: [final_url, domain, status_code, uses_https, title, author, published_at, canonical_url, content_type, redirects, quality_signals, warnings]
side_effect: false
---
# inspect_source

Inspects provenance and technical metadata for one public HTTP or HTTPS URL.
It reports observable signals such as redirects, HTTPS usage, title, author,
publication date, canonical URL, and content type. These signals do not prove
that a source is factually correct.

Private, loopback, link-local, reserved, credential-bearing, and non-HTTP URLs
are rejected. The tool reads at most 512 KiB and follows at most five validated
redirects.
