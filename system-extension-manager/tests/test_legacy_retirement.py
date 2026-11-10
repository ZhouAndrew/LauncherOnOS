"""Retired Mint Toolbox guardrail tests. Never execute or modify the legacy tree."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
sys.path.insert(0, str(ROOT))
import lifecycle


class MintToolboxRetirementTests(unittest.TestCase):
    def test_mint_toolbox_catalog_items_are_rejected(self):
        bad = [
            {'id': 'mint-toolbox', 'name': 'Old app', 'package': 'legacy-one'},
            {'id': 'legacy-one', 'name': 'Mint Toolbox', 'package': 'legacy-one'},
            {'id': 'legacy-one', 'name': 'Old app', 'package': 'mint-toolbox'},
            {'id': 'legacy-one', 'name': 'Old app', 'package': 'legacy-one',
             'launch': ['/usr/bin/mint-toolbox']},
            {'id': 'legacy-one', 'name': 'Old app', 'package': 'legacy-one',
             'launch': ['/usr/bin/mint_toolbox']},
            {'id': 'legacy-one', 'kind': 'portable', 'name': 'Old app',
             'script': 'mint-toolbox/app.py'},
        ]
        for item in bad:
            with self.subTest(item=item):
                with self.assertRaisesRegex(ValueError, 'DO NOT USE MINT TOOLBOX'):
                    lifecycle.reject_retired_mint_toolbox(item)

    def test_catalog_cannot_register_retired_app(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'extensions.json'
            path.write_text(json.dumps([{'id': 'mint-toolbox',
                                         'name': 'Mint Toolbox',
                                         'package': 'mint-toolbox'}]), encoding='utf-8')
            with patch.object(lifecycle, 'ROOT', Path(temp)):
                with self.assertRaisesRegex(ValueError, 'DO NOT USE MINT TOOLBOX'):
                    lifecycle.plugins()

    def test_existing_independent_manager_and_extensions_remain_available(self):
        rows = lifecycle.plugins()
        self.assertIn('security-updates', {item['id'] for item in rows})
        self.assertNotIn('mint-toolbox', {item['id'] for item in rows})
        self.assertFalse(any(item.get('package') == 'mint-toolbox' for item in rows))

    def test_legacy_workflow_cannot_run_or_build(self):
        workflow = (REPOSITORY / '.github/workflows/mint-toolbox.yml').read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch:', workflow)
        self.assertIn('if: ${{ false }}', workflow)
        self.assertNotIn('    branches:', workflow)
        self.assertNotIn('  push:', workflow)
        self.assertNotIn('  pull_request:', workflow)
        self.assertNotIn('mint-toolbox/packaging/build.py', workflow)
        self.assertNotIn('mint-toolbox/packaging/build-toolbox.py', workflow)

    def test_user_facing_warnings_prohibit_reuse(self):
        root_readme = (REPOSITORY / 'README.md').read_text(encoding='utf-8')
        self.assertIn('DO NOT USE MINT TOOLBOX', root_readme)
        self.assertIn('DO NOT USE', lifecycle.MINT_TOOLBOX_RETIRED_WARNING)


if __name__ == '__main__':
    unittest.main()
