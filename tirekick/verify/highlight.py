"""SAM 3.1 evidence highlights for the report frames (stretch, B11). Owner: B.

TODO(B): for each evidence frame (data/frames/{deal}/{EV-xx}.jpg) call SAM 3.1 through the
Meta Model API with a text concept prompt, e.g.
  vin_* evidence          -> "the VIN plate"
  warning_light_hidden    -> "the check engine warning icon on the dashboard"
  odometer_mismatch       -> "the odometer digits"
and save the overlay as {EV-xx}_hl.jpg, setting Evidence.highlight_path. Check the SAM 3.1
request format on dev.meta.ai. If it fails, leave highlight_path None (the report still works).
"""

from __future__ import annotations

from tirekick.models import VerificationReport

CONCEPT_PROMPTS = {
    "vin_unreadable": "the VIN plate",
    "vin_invalid": "the VIN plate",
    "vin_mismatch_doors": "the VIN sticker",
    "vin_listing_mismatch": "the VIN plate",
    "warning_light_hidden": "the check engine warning icon on the dashboard",
    "warning_light_on": "the illuminated warning icon on the dashboard",
    "odometer_mismatch": "the odometer digits",
    "engine_warm": "the temperature gauge needle",
}


def highlight_evidence(report: VerificationReport) -> None:
    """No-op until B wires SAM 3.1."""
    return None
