"""Version constants stamped onto every produced record and the dataset manifest.

Versioning is a first-class requirement: every record carries ``dataset_version`` and
``parser_version`` so downstream consumers can reproduce and diff releases.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Bumped when the *published dataset* schema or content changes in a breaking way.
DATASET_VERSION = "0.1.0"

# Bumped when raw -> normalized parsing logic changes (affects record reproducibility).
PARSER_VERSION = "0.1.0"
