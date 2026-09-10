"""extscorer: generic framework for scoring residential properties as
exterior-renovation (siding/roofing) lead candidates.

This is the free/course/public package. It knows nothing about any
specific client, scraping target, or hosting provider -- those belong in
a downstream deployment package (e.g. a paid "full" overlay) that depends
on this one. Same split as `bidscraper` (Tool 1), `leadscorer` (Tool 2),
and `oppscanner` (Tool 3) -- see any of those repos' ARCHITECTURE.md for
the pattern this follows.
"""

import truststore

# See bidscraper's __init__.py for why: the OS-native trust store is a
# safe superset of certifi's bundled CA list and avoids TLS verification
# failures behind local HTTPS-inspecting security software.
truststore.inject_into_ssl()

__version__ = "0.1.0"
