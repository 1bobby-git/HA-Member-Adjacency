from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_ROOT = REPO_ROOT / "custom_components" / "member_adjacency"
INTEGRATIONS_DASHBOARD_TYPES = {"device", "hub", "service", "hardware"}


class IntegrationVisibilityContractTests(unittest.TestCase):
    def test_manifest_routes_entries_to_integrations_dashboard(self) -> None:
        manifest = json.loads(
            (COMPONENT_ROOT / "manifest.json").read_text(encoding="utf-8")
        )

        self.assertEqual("member_adjacency", manifest["domain"])
        self.assertEqual("1.6.4", manifest["version"])
        self.assertTrue(manifest["config_flow"])
        self.assertEqual("calculated", manifest["iot_class"])
        self.assertEqual("service", manifest["integration_type"])
        self.assertIn(
            manifest["integration_type"],
            INTEGRATIONS_DASHBOARD_TYPES,
            "helper entries are routed to Helpers and omitted from "
            "/config/integrations",
        )

    def test_options_flow_contract_is_available(self) -> None:
        source = (COMPONENT_ROOT / "config_flow.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        classes = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

        config_flow = classes["MemberAdjacencyConfigFlow"]
        options_flow = classes["MemberAdjacencyOptionsFlow"]
        config_flow_methods = {
            node.name for node in config_flow.body if isinstance(node, ast.FunctionDef)
        }
        options_flow_methods = {
            node.name
            for node in options_flow.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        self.assertIn("async_get_options_flow", config_flow_methods)
        self.assertIn("async_step_init", options_flow_methods)
        self.assertIn("return MemberAdjacencyOptionsFlow()", source)
        self.assertIn('self.async_create_entry(title="", data=flat_data)', source)

    def test_options_save_reloads_same_config_entry(self) -> None:
        source = (COMPONENT_ROOT / "__init__.py").read_text(encoding="utf-8")

        self.assertIn("async_reload(entry.entry_id)", source)
        self.assertIn(
            "entry.add_update_listener(_async_update_listener)",
            source,
        )

    def test_device_and_entity_identity_remain_entry_id_based(self) -> None:
        manager = (COMPONENT_ROOT / "manager.py").read_text(encoding="utf-8")
        sensor = (COMPONENT_ROOT / "sensor.py").read_text(encoding="utf-8")
        binary_sensor = (COMPONENT_ROOT / "binary_sensor.py").read_text(
            encoding="utf-8"
        )
        button = (COMPONENT_ROOT / "button.py").read_text(encoding="utf-8")

        self.assertIn('"identifiers": {(DOMAIN, self.entry.entry_id)}', manager)
        for suffix in ("distance", "bucket", "proximity_duration"):
            self.assertIn(f'f"{{entry.entry_id}}_{suffix}"', sensor)
            self.assertIn(f'f"{{mgr.entry.entry_id}}_{suffix}"', sensor)
        self.assertIn('f"{entry.entry_id}_proximity"', binary_sensor)
        self.assertIn('f"{manager.entry.entry_id}_proximity"', binary_sensor)
        self.assertIn('f"{entry.entry_id}_refresh"', button)
        self.assertIn('f"{mgr.entry.entry_id}_refresh"', button)


if __name__ == "__main__":
    unittest.main()
