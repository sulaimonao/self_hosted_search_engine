# Logs: layout and how-to

This document explains where runtime logs are stored and how to access them.

## Recommended logs folder (not tracked by git)
- Root path: `logs/`
- Per service: `logs/<service>/`
- Per environment: `logs/<service>/<env>/`
- Partitioned by date: `logs/<service>/<env>/<YYYY>/<MM>/<DD>.log`
- Symlink: `logs/<service>/<env>/latest.log` → points to current daily file

Example:
- `logs/webapp/production/2025/11/07.log`
- `logs/ingester/staging/latest.log`

## Environment configuration
- Use the environment variable `LOG_DIR` to override the log root (default `./logs`).
- Use `LOG_LEVEL` to control runtime level.

## Best practices
- Use structured logs (JSON) with keys:
  - timestamp, level, service, env, pid, thread, message, correlation_id, extra
- Include correlation_id in logs for tracing across services.
- Configure log rotation (daily or size-based) and retention (e.g., 30 days).
- Do not commit runtime logs to git.
- Provide a logging config for each language/component.

## Tools & ingestion
- For local development: tail and jq for JSON logs: `tail -F logs/webapp/development/latest.log | jq .`
- For production: forward logs to a centralized aggregator (Vector/Fluentd/Promtail/Logstash) or use a cloud logging service.
