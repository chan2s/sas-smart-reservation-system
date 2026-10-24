"""Designated approval-letter signatory and letterhead constants.

The signatory identity is FIXED by the campus's delegation of authority, not
chosen per letter and never supplied by a client. The authenticated account
that signs only needs the ``is_approval_signatory`` flag — the printed name
and position always come from here so no account field can forge them.
"""

# The one authorized signatory of reservation approval letters.
SIGNATORY_NAME = "Francis M. Galon, Ph.D."
SIGNATORY_POSITION = "Assistant Campus Director for Administration and Finance"

# Letterhead. Uses the institutional names the system already uses (SAS
# RESERVE / NORSU); no official logo is invented or embedded.
ISSUING_OFFICE = "Student Affairs and Services Office"
INSTITUTION = "Negros Oriental State University – Bais Campus"
SYSTEM_NAME = "SAS RESERVE"

# The test signature is a DEMONSTRATION mark, never a legally verified digital
# signature. This disclaimer is printed next to it on every generated document.
TEST_SIGNATURE_DISCLAIMER = (
    "Test signature — demonstration only; not a verified or legally "
    "authenticated digital signature."
)
