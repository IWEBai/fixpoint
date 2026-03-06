"""
Shim module to keep backward compatibility if pytest tries to import
`tests.test_cloud_api` directly. The real tests live under
`fixpoint-cloud/tests/test_cloud_api.py` and are collected from there.

We skip this module entirely to avoid duplicate test runs.
"""

import pytest

pytest.skip(
    "Cloud API tests are defined in fixpoint-cloud/tests/test_cloud_api.py",
    allow_module_level=True,
)


