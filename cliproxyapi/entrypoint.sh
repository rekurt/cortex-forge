#!/bin/sh
# Expand environment variables in config template before starting CLIProxyAPI.
# CLIProxyAPI's yaml.v3 parser does not support ${VAR} substitution natively.
sed "s|\${CLIPROXY_API_KEY}|${CLIPROXY_API_KEY}|g" \
    /CLIProxyAPI/config.template.yaml > /CLIProxyAPI/config.yaml
exec ./CLIProxyAPI
