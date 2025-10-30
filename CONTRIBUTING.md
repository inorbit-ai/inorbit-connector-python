<!--
SPDX-FileCopyrightText: 2025 InOrbit, Inc.

SPDX-License-Identifier: MIT
-->

# Contributing

Contributions are encouraged, and they are greatly appreciated! Every little bit helps, and credit will always be given.

## Get Started

Ready to contribute? Here's how to set up `inorbit-connector-python` for local development.

1. Fork the `inorbit-connector-python` repo on [GitHub](https://github.com/inorbit-ai/inorbit-connector-python).

2. Clone your fork locally:

   ```bash
   git clone git@github.com:{your_username_here}/inorbit-connector-python.git
   ```

3. Install the project in editable mode. (It is also recommended to work in a `virtualenv` environment):

   ```bash
   cd inorbit-connector-python
   virtualenv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .[dev]
   ```

   If you prefer to use [`uv`](https://github.com/astral-sh/uv):

   ```bash
   uv venv --python 3.13
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e .[dev]
   ```

4. Create a branch for local development:

   ```bash
   git checkout -b {your_development_type}/short-description
   ```

   Ex: feature/read-tiff-files or bugfix/handle-file-not-found<br>
   Now you can make your changes locally.

5. When you're done making changes, check that your changes pass linting and tests, including testing other Python
   versions with tox:

   ```bash
   tox
   ```

6. Commit your changes and push your branch to GitHub:

   ```bash
   git add .
   git commit -m "Resolves #xyz. Your detailed description of your changes."
   git push origin {your_development_type}/short-description
   ```

7. Submit a pull request through the [GitHub](https://github.com/inorbit-ai/inorbit-connector-python/pulls) website.

## Reuse compliance check

To check if the project is compliant with the REUSE compliance, run the following command:

```bash
reuse --root . lint
```

To fix the issues, run the following command:

```bash
reuse annotate --copyright "InOrbit, Inc." --license "MIT" --recursive . --skip-unrecognised
```

## Version bump and release - Maintainers only

To release a new version:

1. Ensure you're on the latest `main` branch:

   ```bash
   git checkout main
   git pull
   ```

2. Bump the version using `bump2version`. This automatically increments the version number in the
   places specified in the `.bumpversion.cfg` file:

   ```bash
   # Use major, minor, or patch to increment the version number
   bump2version patch --dry-run --verbose
   bump2version patch
   ```

3. Push both the commit and the tag:

   ```bash
   git push
   git push --tags
   ```

CI automatically publishes to PyPI when either:

- A tag is pushed, or
- A commit message contains "Bump version"

After publishing to PyPI, CI also signs the artifacts and creates/updates the GitHub Release.
