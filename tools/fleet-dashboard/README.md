# Fleet dashboard

Watch one hiloop project as a live terminal dashboard: current runs, lineage, the best experiment
per lane, and a rolling event ticker. The script calls only the public `hiloop` CLI.

It declares Python and `rich` in PEP 723 metadata. Install `uv` and the hiloop CLI, authenticate,
then run:

```sh
uv run tools/fleet-dashboard/dashboard.py \
  --project autoresearch \
  --schema demo.experiment.v1 \
  --direction lower
```

Use `--once` to print one snapshot for a preflight. `Ctrl-C` stops only the dashboard; the runs and
sandboxes continue.
