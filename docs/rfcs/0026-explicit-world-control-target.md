# RFC 0026: Explicit world targets for control writes

## Status

Accepted for implementation.

## Problem

The web control endpoint selected its write target from the `worldos_world` browser cookie. A stale cookie after deleting a world could produce an `unknown world` error. More importantly, a missing cookie silently fell back to the catalog default world, allowing a control request to advance the wrong world.

## Decision

Every mutating world-control request MUST carry an explicit `world_id` in its JSON body. Cookies may continue to select a world for read-only Inspector requests, but they are never authoritative for writes.

`POST /api/control/run` therefore requires both `world_id` and `ticks`.

- Missing `world_id`: `400 Bad Request` with a user-facing message.
- Unknown/deleted `world_id`: `404 Not Found` with a user-facing message.
- Valid `world_id`: resolve that descriptor directly and run only its database.
- No write endpoint may fall back to `catalog.default_world()`.

The world page derives its explicit world id from `/world/<world_id>` and includes it in each control request. A stale page for a deleted world receives the 404 and returns the user to `我的世界` instead of selecting another world.

Deleting a custom world clears `worldos_world` and reloads the world list page so browser state is refreshed.

## Invariant

A write request without an explicit world identity must fail closed. It must never mutate a default, legacy, or otherwise unrelated world.
