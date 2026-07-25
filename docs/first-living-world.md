# First Living World runbook

Create and run the reference town:

```bash
python -m pip install -e '.[dev]'
worldos-living init --db living.db
worldos-living run --db living.db --ticks 10000 --restart-at 5000
worldos-inspector --db living.db
```

The scenario starts with three locations and twelve residents. Its bootstrap state deliberately includes production jobs, inventories, money, one trade offer, one conflict, and one rumor. The default runner uses the survival/economy module, saves snapshots every 500 ticks, closes and reopens at the requested restart point, and creates a historical branch from that checkpoint.

A successful report must show `restart_verified: true`, `ticks: 10000`, twelve actors, three locations, a non-empty alternate timeline, and narrator output. Repeating the same run from a fresh database with the same seed must produce the same main world hash and event count.

For interactive inspection, open `http://127.0.0.1:8765` after starting `worldos-inspector`. The database remains authoritative; the inspector and narrator are read-only.
