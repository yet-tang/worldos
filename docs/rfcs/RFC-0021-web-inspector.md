# RFC-0021: Read-only Web Inspector

Status: Accepted for WorldOS v1.1

## Purpose

The Web Inspector makes a persistent WorldOS timeline observable without granting any mutation capability to the browser or narrator. It is a debugging and demonstration surface over replay-backed projections.

## Architecture

```text
SQLite Event Store
  -> WorldInspector
  -> WebInspectorService
  -> JSON HTTP API
  -> Embedded browser UI
```

The service never receives a `WorldRunner` or an append-capable command object. Every response is reconstructed from committed events.

## Required views

- world summary and canonical hash
- location map and actor list
- actor components and current state
- goals and plan steps
- observations, beliefs and memories
- relationship components
- bounded event timeline
- branch comparison
- omniscient or actor-scoped narrator context

## HTTP surface

- `GET /`
- `GET /api/overview?timeline=main`
- `GET /api/actor/{actor_id}?timeline=main`
- `GET /api/events?timeline=main&limit=200`
- `GET /api/narrative?timeline=main&actor={actor_id}`
- `GET /api/compare?left=main&right=alternate`

The HTTP adapter uses only the Python standard library. The event limit is bounded to protect the process from accidental unbounded responses.

## Security boundary

The initial server binds to `127.0.0.1` by default and provides no authentication or TLS. It is intended for local development. Operators exposing it beyond localhost must place it behind an authenticated reverse proxy.

## Determinism

Inspector reads do not append events. Repeating a request against the same timeline and sequence yields equivalent JSON, except for HTTP transport metadata.
