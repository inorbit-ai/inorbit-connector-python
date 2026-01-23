#!/usr/bin/env python

# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

"""Tests for annotation synchronization models."""

import pytest
from pydantic import ValidationError

from inorbit_connector.annotation_sync.models import (
    AnnotationSyncConfig,
    AnnotationSyncMode,
)


class TestAnnotationSyncConfig:
    """Tests for AnnotationSyncConfig model."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        config = AnnotationSyncConfig()
        assert config.enabled is False
        assert config.mode == AnnotationSyncMode.EXTERNAL_TO_INORBIT
        assert config.sync_interval_seconds == 300
        assert config.location_id is None

    def test_enabled_false_location_id_none(self):
        """Test that location_id can be None when enabled is False."""
        config = AnnotationSyncConfig(enabled=False, location_id=None)
        assert config.enabled is False
        assert config.location_id is None

    def test_enabled_false_location_id_provided(self):
        """Test that location_id can be provided when enabled is False."""
        config = AnnotationSyncConfig(enabled=False, location_id="test_location")
        assert config.enabled is False
        assert config.location_id == "test_location"

    def test_enabled_true_location_id_provided(self):
        """Test that location_id can be provided when enabled is True."""
        config = AnnotationSyncConfig(enabled=True, location_id="test_location")
        assert config.enabled is True
        assert config.location_id == "test_location"

    def test_enabled_true_location_id_none_raises_error(self):
        """Test that location_id must be provided when enabled is True."""
        with pytest.raises(ValidationError) as exc_info:
            AnnotationSyncConfig(enabled=True, location_id=None)
        assert "location_id must be provided when enabled is True" in str(
            exc_info.value
        )

    def test_enabled_true_location_id_not_provided_raises_error(self):
        """Test that location_id must be provided when enabled is True and not specified."""
        with pytest.raises(ValidationError) as exc_info:
            AnnotationSyncConfig(enabled=True)
        assert "location_id must be provided when enabled is True" in str(
            exc_info.value
        )

    def test_custom_sync_interval(self):
        """Test that custom sync_interval_seconds can be set."""
        config = AnnotationSyncConfig(sync_interval_seconds=600)
        assert config.sync_interval_seconds == 600

    def test_sync_interval_must_be_positive(self):
        """Test that sync_interval_seconds must be greater than 0."""
        with pytest.raises(ValidationError, match="greater than 0"):
            AnnotationSyncConfig(sync_interval_seconds=0)

        with pytest.raises(ValidationError, match="greater than 0"):
            AnnotationSyncConfig(sync_interval_seconds=-1)

    def test_custom_mode(self):
        """Test that custom mode can be set."""
        config = AnnotationSyncConfig(mode=AnnotationSyncMode.INORBIT_TO_EXTERNAL)
        assert config.mode == AnnotationSyncMode.INORBIT_TO_EXTERNAL

    def test_all_fields_custom(self):
        """Test that all fields can be set with custom values."""
        config = AnnotationSyncConfig(
            enabled=True,
            location_id="custom_location",
            mode=AnnotationSyncMode.INORBIT_TO_EXTERNAL,
            sync_interval_seconds=120,
        )
        assert config.enabled is True
        assert config.location_id == "custom_location"
        assert config.mode == AnnotationSyncMode.INORBIT_TO_EXTERNAL
        assert config.sync_interval_seconds == 120
