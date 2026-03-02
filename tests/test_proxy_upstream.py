#!/usr/bin/env python3
"""
Tests for quota-proxy configurable upstream (CLIProxyAPI integration).

Validates:
- UPSTREAM_URL / UPSTREAM_API_KEY env variables
- Header construction for CLIProxyAPI vs direct Anthropic modes
- docker-compose.yml wiring (depends_on, env vars)
- ANTHROPIC_API_KEY is optional when UPSTREAM_API_KEY is set
"""

import os
import re
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read_file(relative_path):
    path = os.path.join(REPO_ROOT, relative_path)
    with open(path) as f:
        return f.read()


class TestProxyUpstreamConfig(unittest.TestCase):
    """Validate proxy.py has configurable upstream."""

    def setUp(self):
        self.proxy = _read_file("quota-proxy/proxy.py")

    def test_upstream_url_env_variable(self):
        """UPSTREAM_URL must be read from environment with sensible default."""
        self.assertIn('UPSTREAM_URL', self.proxy)
        self.assertIn('os.environ.get("UPSTREAM_URL"', self.proxy)
        # Default must be api.anthropic.com
        self.assertRegex(self.proxy, r'UPSTREAM_URL.*api\.anthropic\.com')

    def test_upstream_api_key_env_variable(self):
        """UPSTREAM_API_KEY must be read from environment."""
        self.assertIn('UPSTREAM_API_KEY', self.proxy)
        self.assertIn('os.environ.get("UPSTREAM_API_KEY"', self.proxy)

    def test_anthropic_api_key_optional(self):
        """ANTHROPIC_API_KEY alone should NOT cause crash if UPSTREAM_API_KEY is set."""
        # The error message should mention both keys, not just ANTHROPIC_API_KEY
        self.assertRegex(
            self.proxy,
            r'UPSTREAM_API_KEY.*ANTHROPIC_API_KEY|ANTHROPIC_API_KEY.*UPSTREAM_API_KEY',
            "Error message should mention both key options"
        )

    def test_cliproxy_mode_detection(self):
        """Proxy must detect CLIProxyAPI mode based on UPSTREAM_URL."""
        self.assertIn('_is_cliproxy', self.proxy)
        self.assertIn('api.anthropic.com', self.proxy)

    def test_cliproxy_user_agent(self):
        """CLIProxyAPI mode must set User-Agent to avoid cloaking."""
        self.assertIn('claude-cli/', self.proxy)
        self.assertIn('User-Agent', self.proxy)

    def test_cliproxy_no_oauth_betas(self):
        """CLIProxyAPI mode must NOT add OAuth betas automatically."""
        # Find the CLIProxyAPI branch in _proxy and verify it doesn't force oauth betas
        cliproxy_section = re.search(
            r'if _is_cliproxy:.*?(?=elif|else)',
            self.proxy, re.DOTALL
        )
        self.assertIsNotNone(cliproxy_section, "CLIProxyAPI branch must exist in _proxy")
        block = cliproxy_section.group()
        self.assertNotIn('oauth-2025-04-20', block,
                         "CLIProxyAPI mode should NOT add oauth betas")

    def test_direct_anthropic_oauth_betas(self):
        """Direct Anthropic with OAuth key must add oauth betas."""
        self.assertIn('oauth-2025-04-20', self.proxy)
        self.assertIn('claude-code-20250219', self.proxy)

    def test_upstream_key_priority(self):
        """UPSTREAM_API_KEY should take priority over ANTHROPIC_API_KEY."""
        self.assertRegex(
            self.proxy,
            r'_upstream_key\s*=\s*UPSTREAM_API_KEY\s*or\s*REAL_API_KEY'
        )

    def test_uses_upstream_url_in_request(self):
        """Request must be constructed with UPSTREAM_URL, not hardcoded."""
        # Check that Request() uses UPSTREAM_URL
        self.assertRegex(self.proxy, r'Request\(UPSTREAM_URL\s*\+')
        # Ensure no hardcoded UPSTREAM + self.path
        self.assertNotRegex(
            self.proxy,
            r'Request\(UPSTREAM\s*\+\s*self\.path',
            "Must use UPSTREAM_URL, not old UPSTREAM constant"
        )


class TestDockerComposeUpstreamWiring(unittest.TestCase):
    """Validate quota-proxy → cliproxyapi wiring in docker-compose.yml."""

    def setUp(self):
        self.compose = _read_file("docker-compose.yml")
        # Extract quota-proxy service block
        match = re.search(
            r'quota-proxy:.*?(?=^\s{2}\w|\Z)',
            self.compose, re.DOTALL | re.MULTILINE
        )
        self.assertIsNotNone(match, "quota-proxy service must exist")
        self.proxy_block = match.group()

    def test_upstream_url_env(self):
        """quota-proxy must receive UPSTREAM_URL pointing to cliproxyapi."""
        self.assertIn('UPSTREAM_URL=http://cliproxyapi:8317', self.proxy_block)

    def test_upstream_api_key_env(self):
        """quota-proxy must receive UPSTREAM_API_KEY from CLIPROXY_API_KEY."""
        self.assertIn('UPSTREAM_API_KEY=${CLIPROXY_API_KEY}', self.proxy_block)

    def test_depends_on_cliproxyapi(self):
        """quota-proxy must depend on cliproxyapi with healthcheck."""
        self.assertIn('cliproxyapi:', self.proxy_block)
        self.assertIn('condition: service_healthy', self.proxy_block)

    def test_still_in_corp_egress(self):
        """quota-proxy must remain in corp-egress for fallback."""
        self.assertIn('corp-egress', self.proxy_block)


class TestProxyHeaderModes(unittest.TestCase):
    """Validate that proxy constructs correct headers for each mode."""

    def setUp(self):
        self.proxy = _read_file("quota-proxy/proxy.py")

    def test_three_header_modes_exist(self):
        """Proxy must handle 3 modes: CLIProxyAPI, OAuth, standard API key."""
        # CLIProxyAPI mode
        self.assertIn('if _is_cliproxy:', self.proxy)
        # OAuth mode
        self.assertIn('sk-ant-oat', self.proxy)
        # Standard mode (else branch)
        # Count the x-api-key assignments - should be at least 2 (cliproxy + standard)
        xapi_count = len(re.findall(r'headers\["x-api-key"\]\s*=', self.proxy))
        self.assertGreaterEqual(xapi_count, 2,
                                "Must set x-api-key in both CLIProxyAPI and standard modes")

    def test_cliproxy_uses_x_api_key(self):
        """CLIProxyAPI mode must use x-api-key (not Authorization bearer)."""
        cliproxy_section = re.search(
            r'if _is_cliproxy:.*?(?=elif|else)',
            self.proxy, re.DOTALL
        )
        self.assertIsNotNone(cliproxy_section)
        block = cliproxy_section.group()
        self.assertIn('x-api-key', block)
        self.assertNotIn('Authorization', block)


if __name__ == "__main__":
    unittest.main()
