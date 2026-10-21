"""Compatibility exports from the single original-document byte/view owner.

No runtime construction, provider, SQL, grant or authority is imported here.
"""
from oracle_brain.ingest import originals
from oracle_brain.ingest.originals import (
    RawPDFViewsV1, raw_pdf_view_policy_hash_v1, render_raw_pdf_views_v1,
    raw_pdf_multimodal_messages_v1, verify_raw_pdf_multimodal_messages_v1,
)
