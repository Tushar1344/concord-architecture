# Concord · Architecture

The architecture spec for **Concord**, a library of contracts that turns any user request, system event, webhook, scheduled job, or agent action into a durable, inspectable workflow.

> Concord declares what work means; a durable runtime (DBOS by default) executes it.

## What's here

| File | Description |
|---|---|
| [`index.html`](./index.html) | The full architecture spec — three tabs (Core architecture, Multi-agent extensions, Runtime adapter), ~100 collapsible sections, ~40 mermaid diagrams. Live: see Pages URL below. |
| [`concord_boundary_check.py`](./concord_boundary_check.py) | Reference implementation of the NR.2 boundary checker. Zero-dependency AST scanner that enforces `concord/core/` and `concord/domain/` never import a runtime; only `concord/runtime/<adapter>.py` may. Drop into CI as `python concord_boundary_check.py concord/`. |

## Core idea

```
Ingress → Command → Context → Policy → Plan → Execution → State → Output → Memory → Audit
```

Every consequential action flows through that pipeline. The contract (what an action means, what policy applies, what compensations exist, who may cancel it) is Concord's job. The mechanics (when it runs, how it retries, how it queues, how it sleeps, how it recovers) belong to the runtime adapter.

## Reading order

1. **Core architecture** (Part I): foundations, schema, domain model, policy, approval, memory, artifact, audit, cancellation, compensation, service interfaces, testing.
2. **Multi-agent extensions** (Part II): swarm runs, agent runs, subagent spawning, governance for multi-agent execution.
3. **Runtime adapter · DBOS today** (Part III): the DBOS-specific implementation, queue model, retry mechanics, transaction boundaries.

The contract/mechanics split is anchored in §2.8 of the spec. The `DurableRuntime` protocol that makes the runtime swappable is in §41.

## Boundary check

```bash
python concord_boundary_check.py concord/
```

Exits non-zero on the first violation. CI integration:

```yaml
- name: Concord boundary check
  run: python concord_boundary_check.py concord/
```

## License

MIT
