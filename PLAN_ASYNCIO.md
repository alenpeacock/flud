# Asyncio Migration Plan

This plan outlines a staged migration from Twisted to asyncio for Flud.
It will be updated as the migration progresses.

## Current Status

- Phase 0: complete
- Phase 1: complete
- Phase 2: complete
- Phase 3: complete
- Phase 4: in progress
- Phase 5: pending

## Target Architecture

- HTTP server/client: aiohttp
  - Server: aiohttp.web.Application with routes for file ops + DHT ops
  - Client: shared aiohttp.ClientSession per node
  - Streaming: aiohttp.web.StreamResponse; protocol can evolve
- Scheduling: asyncio.create_task + asyncio.sleep
- Blocking work: asyncio.to_thread (zfec, crypto, filesystem IO as needed)
- Error handling: explicit try/except in async flows
- Local protocol: asyncio.start_server line protocol (or CLI direct calls)
- Process management: python entrypoint instead of twistd/tac

## Staged Migration Plan

### Phase 0 — Baseline safety net
- Add async test harness and logging hooks
- Keep a minimal smoke test for STORE/RETRIEVE/VERIFY

Deliverables:
- pytest-asyncio (or lightweight async runner)
- “smoke” test running against current Twisted stack

### Phase 1 — Async test harness + adapters
- Introduce Deferred->Future adapter
- Run tests under asyncio while Twisted remains in prod code

Deliverables:
- tests_async/ or converted tests
- compatibility helper for Deferred->Future

### Phase 2 — Replace HTTP client stack
- Swap ClientPrimitives/ClientDHTPrimitives to aiohttp
- Keep Twisted server for compatibility

Deliverables:
- aiohttp-based client ops
- tests passing against Twisted server

### Phase 3 — Replace HTTP server stack
- Implement aiohttp server and routes
- Define/adjust HTTP protocol (allowed to change)

Deliverables:
- asyncio server entrypoint
- core tests passing against aiohttp server

### Phase 4 — Remove Twisted from file ops + local protocol
- Convert FludFileOperations to async/await
- Replace DeferredList with asyncio.gather
- Replace reactor.callLater with asyncio sleep
- Replace local protocol with asyncio server or CLI direct path

Deliverables:
- fully async file ops
- no Twisted in core paths

### Phase 5 — Cleanup + protocol evolution
- Remove Twisted dependencies from packaging
- Tighten protocol and add structured logging

Deliverables:
- Twisted removed
- updated docs and CLI

## Risks / Deficiencies to Track

- Multipart/streaming behavior differences (Twisted vs aiohttp)
- Timeout/retry semantics and cancellation behavior
- Concurrency & mutable state interleaving
- Backpressure and memory usage in large transfers
- Threaded CPU work (zfec, crypto) blocking the loop
- Reputation and error propagation changes

## Verification Milestones

- Milestone A: async tests pass with Twisted adapters
- Milestone B: aiohttp client against Twisted server passes tests
- Milestone C: aiohttp server passes STORE/RETRIEVE/VERIFY + DHT tests
- Milestone D: Twisted removed, all tests pass, new CLI works
