# Persistent development sandbox

There is no `hiloop devbox` command. Compose a long-lived environment from ordinary sandbox verbs
only when the deployment provides durable storage and, for interactive use, the session plane.

```sh
hiloop sandbox create devbox --storage-class durable --cpus 4 --memory-mb 8192
hiloop sandbox ssh devbox
hiloop sandbox stop devbox
hiloop sandbox start devbox
```

Keep source, setup scripts, and durable outputs under `/workspace`. Package installs and other files
outside it may disappear on start. Assume every process is gone after stop/start unless the
deployment explicitly proves memory restore. Never store credentials on the workspace; use the
`managing-secrets` skill for brokered credentials.

Use `sandbox cp` for files that cannot be cloned, and clone repositories from inside the sandbox
when egress permits. Omit `--ttl` only after checking the deployment's default expiry. Delete the
sandbox when its persistent workspace is no longer needed.
