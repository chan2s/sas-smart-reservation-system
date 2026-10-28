"""Institutional letterhead and position constants."""

SIGNATORY_POSITION = "Assistant Campus Director for Administration and Finance"

# Letterhead. Uses the institutional names the system already uses (SAS
# RESERVE / NORSU); no official logo is invented or embedded.
ISSUING_OFFICE = "Student Affairs and Services Office"
INSTITUTION = "Negros Oriental State University – BSC"
SYSTEM_NAME = "SAS RESERVE"

# Institutional statements and the document notice are copied from the
# supplied NORSU template for the generated PDF; the DOCX retains their
# original header/footer artwork and text directly from the source file.
VISION_STATEMENT = "A globally recognized state university."
MISSION_STATEMENT = (
    "Negros Oriental State University delivers global excellence through "
    "advanced instruction, impactful research, and modern infrastructure "
    "shaping effective leaders to serve the Philippine society and the world."
)
QUALITY_POLICY = (
    "Negros Oriental State University commits to delivering quality "
    "instruction, research, extension and production. We ensure compliance "
    "with all statutory and regulatory requirements and continuously work to "
    "improve our management system to meet our quality objectives."
)
DOCUMENT_DISCLAIMER = (
    "The information transmitted by this document is intended only for the "
    "person or entity to which it is addressed. This document may contain "
    "proprietary, business-confidential and/or privileged material. If you are "
    "not the intended recipient, be aware that any use, review, retransmission, "
    "distribution, reproduction or any action taken in reliance upon this "
    "message is strictly prohibited. If you received this in error, please "
    "contact the sender. Thank you."
)

# The test signature is a DEMONSTRATION mark, never a legally verified digital
# signature. This disclaimer is printed next to it on every generated document.
TEST_SIGNATURE_DISCLAIMER = (
    "Test signature — demonstration only; not a verified or legally "
    "authenticated digital signature."
)
