#!/bin/sh
# Expand environment variables in config template before starting CLIProxyAPI.
# CLIProxyAPI's yaml.v3 parser does not support ${VAR} substitution natively.
sed "s|\${CLIPROXY_API_KEY}|${CLIPROXY_API_KEY}|g" \
    /CLIProxyAPI/config.template.yaml > /CLIProxyAPI/config.yaml

# CLIProxyAPI stores credential files (claude-*.json) in its working directory.
# Symlink them from the persistent auth volume so they survive container recreates.
AUTH_DIR=/root/.cli-proxy-api
if [ -d "$AUTH_DIR" ]; then
    for f in "$AUTH_DIR"/*.json; do
        [ -f "$f" ] && ln -sf "$f" /CLIProxyAPI/
    done
fi

exec ./CLIProxyAPI
