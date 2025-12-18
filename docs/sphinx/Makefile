# SPDX-FileCopyrightText: 2025 InOrbit, Inc.
#
# SPDX-License-Identifier: MIT

# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

# Path prefix matching Mintlify structure (for link compatibility)
SITE_PREFIX   = ground-control/robot-integration/connector-framework

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile serve site clean-site

# Fix absolute Mintlify-style links that MyST converts to anchors
fix-links:
	@echo "Fixing absolute links in HTML..."
	@python fix_links.py "$(BUILDDIR)/html"

# Build and nest under Mintlify-compatible path for local testing
site: html fix-links
	@mkdir -p "$(BUILDDIR)/site/$(SITE_PREFIX)"
	@cp -r "$(BUILDDIR)/html/"* "$(BUILDDIR)/site/$(SITE_PREFIX)/"
	@echo '<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0; url=/$(SITE_PREFIX)/index.html"></head><body></body></html>' > "$(BUILDDIR)/site/index.html"
	@echo "Site ready at $(BUILDDIR)/site/"

# Serve locally with correct path structure
serve: site
	@echo "Serving at http://localhost:8000/$(SITE_PREFIX)/"
	@cd "$(BUILDDIR)/site" && python -m http.server 8000

# Clean the nested site directory
clean-site:
	@rm -rf "$(BUILDDIR)/site"

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
