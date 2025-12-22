# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
# SPDX-License-Identifier: MIT

# Makefile for building Mintlify-compatible docs from shared content

CONTENT_DIR = ../contents
BUILD_DIR = _build

.PHONY: build clean

# Build Mintlify-compatible docs with absolute links
build:
	@echo "Building Mintlify-compatible docs..."
	@python build.py "$(CONTENT_DIR)" "$(BUILD_DIR)"
	@echo "Done. Output in $(BUILD_DIR)/"

# Clean build artifacts
clean:
	@rm -rf "$(BUILD_DIR)"
	@echo "Cleaned $(BUILD_DIR)/"

