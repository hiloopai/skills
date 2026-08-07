# Snapshots and branches

Snapshots and durable workspaces are deployment capabilities. A refusal is final and never a
half-completed branch.

## Snapshot

```sh
hiloop sandbox snapshot create <sandbox> --name baseline
hiloop sandbox snapshot list --sandbox <sandbox>
hiloop sandbox snapshot delete <snapshot>
```

`--wait-remote` waits up to 25 seconds for replicated durability. Read the returned `durability`;
`local` is not replicated. Use `--idempotency-key` when an ambiguous failure may be retried.

## Branch

`create --from` is restore, fork, and branch in one verb:

```sh
hiloop sandbox create arm-a --from baseline --storage-class durable
hiloop sandbox create arm-b --from baseline --storage-class durable
```

Each child owns an independent durable workspace starting from the same bytes. Concurrent creates
from one snapshot are the fan-out primitive. Snapshots capture disk, not memory; checkpoint useful
state to files. There is no separate `fork`, `restore`, or `resume` verb.
