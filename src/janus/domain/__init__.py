"""Pure domain core: value objects, the validation gate (``limen``), the split
policy, trust records, and the threat scanner.

Everything here is side-effect-free and import-light (stdlib only). The world —
``claude -p``, the filesystem, transcripts — is reached only through ports and
adapters, never from this package.
"""

from __future__ import annotations
