# poller guide

poller checks a list of URLs on a schedule and appends the results to a JSON
file. This guide is the artifact under audit in `examples/findings.docs.json`:
three of its claims are false.

## Install

Requires Python 3.9 or newer.

```bash
pip install poller
```

## Configure

Put your URL list in `config/poller.yaml`:

```yaml
urls:
  - https://example.com
```

## Run

Start the daemon:

```bash
poller --serve
```

Poll once and exit:

```bash
poller --once --config config/poller.yaml
```
