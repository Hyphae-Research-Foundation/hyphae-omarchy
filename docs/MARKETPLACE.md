# Marketplace submission

Repository: https://github.com/Hyphae-Research-Foundation/hyphae-omarchy

Plugin: `org.hyphaeresearch.memory` — Hyphae Memory

Category: Developer Tools

Tags: AI, Bar, Quickshell

Submission: https://github.com/omacom/omarchy-plugin-marketplace/issues/6541

The revised client follows the boundary clarified in comment 5647744712:
an independently installed service may retain operator functionality, while
the client receives only a dedicated, server-restricted memory interface.

The client repository contains the panel, Python socket client, protocol
contract, tests and documentation. Memory data, query/proof and backup operations
are available through the separate credential. Service/runtime administration and
external agent integrations belong to the independently managed Hyphae application.

The README covers prerequisites, installation, connection and removal. The
root preview shows the actual Omarchy panel. A new exact commit must complete
compatibility validation and receive fresh maintainer review before listing.
