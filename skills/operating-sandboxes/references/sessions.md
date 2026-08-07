# Sessions and file transfer

Use buffered `exec` unless the task needs an interactive terminal, file transfer, or an OpenSSH
feature. The latter paths require the deployment's managed session plane.

## SSH

```sh
hiloop sandbox ssh <sandbox>
hiloop sandbox ssh <sandbox> -- 'cd /workspace && git status'
hiloop sandbox ssh <sandbox> -- -L 8080:localhost:8080
```

Arguments after `--` are stock OpenSSH arguments or the remote command. SSH auto-starts a stopped
sandbox. If the deployment has no session endpoint, use `sandbox exec`; do not poll or construct a
private endpoint.

## Copy

Exactly one path must use `<sandbox>:/absolute/path`:

```sh
hiloop sandbox cp ./train.py box:/workspace/train.py
hiloop sandbox cp -r box:/workspace/out ./out
```

`cp` uses managed SFTP and needs nothing installed in the guest. The CLI does not expose reusable
credentials for invoking plain scp, sftp, or rsync directly. For a large repository, clone inside
the sandbox instead of copying thousands of files one by one.

For large versioned datasets shared by many sandboxes, use the `managing-volumes` skill, but confirm
the deployment admits volume mounts before building a workflow around them.
