"""
Unit tests for the --operator-image-ref validation feature.

Tests verify that:
  - When --operator-image-ref matches the resolved image, processing continues
  - When --operator-image-ref mismatches, the processor exits with error
  - When --operator-image-ref is not provided, no validation occurs (backward compat)
  - The --use-existing-digests path is unaffected by --operator-image-ref
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

processors_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if processors_root not in sys.path:
    sys.path.insert(0, processors_root)

MATCHED_REF = 'quay.io/rhoai/odh-rhel9-operator@sha256:abc123'
MISMATCHED_REF = 'quay.io/rhoai/odh-rhel9-operator@sha256:different999'

# Simulated return values from util helpers
OPERATOR_ENTRY = [{'name': 'RELATED_IMAGE_ODH_OPERATOR_IMAGE', 'value': MATCHED_REF}]
GIT_METADATA = {'git_url': 'https://github.com/opendatahub-io/opendatahub-operator', 'git_commit': 'abc123'}


def _make_processor(operator_image_ref=None, use_existing_digests=False):
    """
    Build a minimal bundle_processor instance with mocked __init__.

    Skips all file I/O by replacing __init__ with a no-op, then sets
    only the attributes that fetch_operator_metadata needs.
    """
    from importlib import import_module
    bp_module = import_module('bundle-processor')
    BundleProcessor = bp_module.bundle_processor

    with patch.object(BundleProcessor, '__init__', lambda self: None):
        proc = BundleProcessor()

    proc.operator_image_ref = operator_image_ref
    proc.use_existing_digests = use_existing_digests
    proc.rhoai_version = 'rhoai-3.6'
    proc.build_type = 'ci'
    proc.patch_dict = {
        'patch': {
            'relatedImages': [
                {'name': 'RELATED_IMAGE_ODH_OPERATOR_IMAGE', 'value': 'quay.io/rhoai/odh-rhel9-operator@sha256:placeholder'},
            ]
        }
    }
    return proc


class TestOperatorImageRefValidation:

    @patch('utils.util.fetch_latest_images_and_git_metadata', return_value=(OPERATOR_ENTRY, GIT_METADATA))
    @patch('utils.util.filter_image_entries', return_value=[OPERATOR_ENTRY[0]])
    def test_matching_ref_passes(self, mock_filter, mock_fetch):
        """When --operator-image-ref matches resolved image, processing continues."""
        proc = _make_processor(operator_image_ref=MATCHED_REF)
        result = proc.fetch_operator_metadata()

        assert result[0][0]['value'] == MATCHED_REF
        assert result[1] == GIT_METADATA

    @patch('utils.util.fetch_latest_images_and_git_metadata', return_value=(OPERATOR_ENTRY, GIT_METADATA))
    @patch('utils.util.filter_image_entries', return_value=[OPERATOR_ENTRY[0]])
    def test_mismatching_ref_exits(self, mock_filter, mock_fetch):
        """When --operator-image-ref does not match, sys.exit(1) is called."""
        proc = _make_processor(operator_image_ref=MISMATCHED_REF)

        with pytest.raises(SystemExit) as exc_info:
            proc.fetch_operator_metadata()
        assert exc_info.value.code == 1

    @patch('utils.util.fetch_latest_images_and_git_metadata', return_value=(OPERATOR_ENTRY, GIT_METADATA))
    @patch('utils.util.filter_image_entries', return_value=[OPERATOR_ENTRY[0]])
    def test_ref_not_provided_skips_validation(self, mock_filter, mock_fetch):
        """When --operator-image-ref is not set, no validation occurs (backward compat)."""
        proc = _make_processor(operator_image_ref=None)
        result = proc.fetch_operator_metadata()

        # Should return normally without any ref check
        assert result[0][0]['value'] == MATCHED_REF
        assert result[1] == GIT_METADATA

    @patch('utils.util.fetch_git_metadata_for_existing_digests', return_value=GIT_METADATA)
    @patch('utils.util.filter_image_entries', return_value=[OPERATOR_ENTRY[0]])
    def test_use_existing_digests_unaffected(self, mock_filter, mock_fetch_git):
        """--use-existing-digests skips Quay lookup entirely; --operator-image-ref is never checked."""
        proc = _make_processor(operator_image_ref=MISMATCHED_REF, use_existing_digests=True)
        result = proc.fetch_operator_metadata()

        # Should return the original entry without calling fetch_latest_images_and_git_metadata
        assert result[0][0]['value'] == OPERATOR_ENTRY[0]['value']
        assert result[1] == GIT_METADATA
        mock_fetch_git.assert_called_once()
