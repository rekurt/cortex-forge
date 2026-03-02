#!/usr/bin/env python3
"""
Tests for CLIProxyAPI configuration and Docker Compose integration.

Validates config.yaml format and docker-compose.yml service definition.
Uses stdlib only (no PyYAML) — parses files as text.
"""

import os
import re
import unittest


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read_file(relative_path):
    path = os.path.join(REPO_ROOT, relative_path)
    with open(path) as f:
        return f.read()


class TestCliproxyapiConfig(unittest.TestCase):
    """Validate cliproxyapi/config.yaml structure and required fields."""

    def setUp(self):
        self.config = _read_file("cliproxyapi/config.yaml")

    def test_host_is_set(self):
        self.assertTrue(
            re.search(r'^host:\s*"0\.0\.0\.0"', self.config, re.MULTILINE),
            "host must be 0.0.0.0")

    def test_port_is_8317(self):
        self.assertTrue(
            re.search(r'^port:\s*8317', self.config, re.MULTILINE),
            "port must be 8317")

    def test_api_keys_present(self):
        self.assertIn("api-keys:", self.config)

    def test_logging_enabled(self):
        self.assertRegex(self.config, r'logging-to-file:\s*true')

    def test_commercial_mode_enabled(self):
        self.assertRegex(self.config, r'commercial-mode:\s*true')

    # ---  structural checks  ---

    def test_no_hardcoded_api_key(self):
        """API key must come from env variable, not be hardcoded."""
        in_api_keys = False
        for line in self.config.splitlines():
            stripped = line.strip()
            if stripped.startswith("api-keys:"):
                in_api_keys = True
                continue
            # End of api-keys block when a new top-level key starts
            if in_api_keys and stripped and not stripped.startswith("-") and not stripped.startswith("#"):
                in_api_keys = False
            if in_api_keys and stripped.startswith("-"):
                # Every entry under api-keys must use ${...} env substitution
                self.assertIn("${", stripped,
                              f"api key entry should use env variable substitution, got: {stripped}")


class TestDockerComposeCliproxyapi(unittest.TestCase):
    """Validate cliproxyapi service in docker-compose.yml."""

    def setUp(self):
        self.compose = _read_file("docker-compose.yml")

    def test_cliproxyapi_service_exists(self):
        self.assertTrue(
            re.search(r'^\s+cliproxyapi:', self.compose, re.MULTILINE),
            "cliproxyapi service must be defined")

    def test_cliproxyapi_image(self):
        self.assertIn("eceasy/cli-proxy-api:latest", self.compose)

    def test_cliproxyapi_in_corp_egress(self):
        # Find cliproxyapi service block and check networks
        match = re.search(
            r'cliproxyapi:.*?(?=^\s{2}\w|\Z)',
            self.compose, re.DOTALL | re.MULTILINE
        )
        self.assertIsNotNone(match, "cliproxyapi service block not found")
        block = match.group()
        self.assertIn("corp-egress", block)

    def test_cliproxyapi_not_in_corp_internal(self):
        """cliproxyapi must NOT be on corp-internal to prevent quota-proxy bypass."""
        match = re.search(
            r'cliproxyapi:.*?(?=^\s{2}\w|\Z)',
            self.compose, re.DOTALL | re.MULTILINE
        )
        self.assertIsNotNone(match)
        block = match.group()
        # Collect network lines from the networks section of cliproxyapi block
        in_networks = False
        network_lines = []
        for line in block.splitlines():
            stripped = line.strip()
            if stripped == "networks:":
                in_networks = True
                continue
            if in_networks:
                if stripped.startswith("- "):
                    network_lines.append(stripped)
                elif stripped and not stripped.startswith("#"):
                    break
        network_text = " ".join(network_lines)
        self.assertNotIn("corp-internal", network_text,
                          "cliproxyapi must NOT be on corp-internal (instances could bypass quota-proxy)")

    def test_cliproxyapi_no_exposed_ports(self):
        """cliproxyapi must NOT expose ports to host."""
        match = re.search(
            r'cliproxyapi:.*?(?=^\s{2}\w|\Z)',
            self.compose, re.DOTALL | re.MULTILINE
        )
        self.assertIsNotNone(match)
        block = match.group()
        self.assertIsNone(
            re.search(r'^\s+ports:', block, re.MULTILINE),
            "cliproxyapi should NOT have ports section")

    def test_cliproxyapi_config_volume(self):
        self.assertIn("cliproxyapi/config.yaml:/CLIProxyAPI/config.yaml", self.compose)

    def test_cliproxyapi_security_opt(self):
        """cliproxyapi must have no-new-privileges security option."""
        match = re.search(
            r'cliproxyapi:.*?(?=^\s{2}\w|\Z)',
            self.compose, re.DOTALL | re.MULTILINE
        )
        self.assertIsNotNone(match)
        block = match.group()
        self.assertIn("no-new-privileges", block,
                       "cliproxyapi must have no-new-privileges:true")

    def test_cliproxyapi_auths_volume(self):
        self.assertIn("cliproxyapi-auths", self.compose)

    def test_cliproxyapi_logs_volume(self):
        self.assertIn("cliproxyapi-logs", self.compose)

    def test_cliproxyapi_healthcheck(self):
        match = re.search(
            r'cliproxyapi:.*?(?=^\s{2}\w|\Z)',
            self.compose, re.DOTALL | re.MULTILINE
        )
        self.assertIsNotNone(match)
        block = match.group()
        self.assertIn("healthcheck:", block)
        self.assertIn("8317", block)

    def test_named_volumes_declared(self):
        # Check volumes section at root level
        volumes_section = self.compose.split("\nvolumes:")[1] if "\nvolumes:" in self.compose else ""
        self.assertIn("cliproxyapi-auths:", volumes_section)
        self.assertIn("cliproxyapi-logs:", volumes_section)


class TestEnvExample(unittest.TestCase):
    """Validate .env.example has CLIProxyAPI variables."""

    def setUp(self):
        self.env = _read_file(".env.example")

    def test_cliproxy_api_key_present(self):
        self.assertIn("CLIPROXY_API_KEY", self.env)

    def test_cliproxy_api_key_has_placeholder(self):
        """Must have a placeholder value, not be empty."""
        match = re.search(r'CLIPROXY_API_KEY=(\S+)', self.env)
        self.assertIsNotNone(match, "CLIPROXY_API_KEY must have a value")
        self.assertNotEqual(match.group(1), "",
                            "CLIPROXY_API_KEY must not be empty")


if __name__ == "__main__":
    unittest.main()
