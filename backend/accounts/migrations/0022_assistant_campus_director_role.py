from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0021_alter_auditlog_action")]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Administrator"),
                    ("STAFF", "SAS Staff"),
                    ("REQUESTER", "Requester"),
                    (
                        "ASSISTANT_CAMPUS_DIRECTOR_ADMIN_FINANCE",
                        "Assistant Campus Director for Administration and Finance",
                    ),
                ],
                default="REQUESTER",
                max_length=48,
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(role="ASSISTANT_CAMPUS_DIRECTOR_ADMIN_FINANCE"),
                fields=("role",),
                name="unique_assistant_campus_director_role",
            ),
        ),
        migrations.AlterField(
            model_name="auditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("LOGIN", "Logged in"),
                    ("LOGOUT", "Logged out"),
                    ("REGISTER", "Registered"),
                    ("GOOGLE_FIRST_ACCOUNT", "Google account created"),
                    ("OTP_SENT", "Email verification code sent"),
                    ("OTP_RESENT", "Email verification code resent"),
                    ("OTP_VERIFIED", "Email verified"),
                    ("OTP_FAILED", "Email verification failed"),
                    ("OTP_EXPIRED", "Email verification code expired"),
                    ("RESERVATION_CREATED", "Reservation created"),
                    ("RESERVATION_EDITED", "Reservation edited"),
                    ("RESERVATION_APPROVED", "Reservation approved"),
                    ("RESERVATION_REJECTED", "Reservation rejected"),
                    ("RESERVATION_CANCELLED", "Reservation cancelled"),
                    ("RESERVATION_NO_SHOW", "Reservation marked no-show"),
                    ("RESERVATION_STATUS", "Reservation status changed"),
                    ("APPROVAL_LETTER_CREATED", "Approval letter created"),
                    (
                        "APPROVAL_LETTER_DOC_GENERATED",
                        "Approval letter document generated",
                    ),
                    ("APPROVAL_LETTER_SIGNED", "Approval letter signed"),
                    ("APPROVAL_LETTER_APPROVED", "Approval letter approved"),
                    (
                        "APPROVAL_LETTER_EMAIL_SENT",
                        "Approval letter email accepted",
                    ),
                    (
                        "APPROVAL_LETTER_EMAIL_FAILED",
                        "Approval letter email failed",
                    ),
                    ("APPROVAL_LETTER_EMAIL_TRY", "Approval letter email attempted"),
                    (
                        "APPROVAL_LETTER_EMAIL_RETRIED",
                        "Approval letter email retried",
                    ),
                    ("EARLY_CHECK_IN", "Early check-in performed"),
                    ("CHECK_IN", "Checked in"),
                    ("CHECK_OUT", "Checked out"),
                    ("EQUIPMENT_CREATED", "Equipment created"),
                    ("EQUIPMENT_EDITED", "Equipment edited"),
                    ("EQUIPMENT_REMOVED", "Equipment removed"),
                    ("EQUIPMENT_IMAGE", "Equipment image changed"),
                    ("FACILITY_CREATED", "Facility created"),
                    ("FACILITY_EDITED", "Facility edited"),
                    ("FACILITY_REMOVED", "Facility removed"),
                    ("FACILITY_IMAGE", "Facility image changed"),
                    ("SETTINGS_CHANGED", "Settings changed"),
                    ("AFFILIATION_CHANGED", "Affiliation changed"),
                    ("ORGANIZATION_REGISTERED", "Organization registered"),
                    ("ORGANIZATION_UPDATED", "Organization updated"),
                    ("ORGANIZATION_APPROVED", "Organization approved"),
                    ("ORGANIZATION_REJECTED", "Organization rejected"),
                    ("ORGANIZATION_SUSPENDED", "Organization suspended"),
                    ("ORGANIZATION_REACTIVATED", "Organization reactivated"),
                    ("USER_CREATED", "User account created"),
                    ("USER_UPDATED", "User account updated"),
                    ("USER_PASSWORD_RESET", "User password reset"),
                    ("USER_DELETED", "User account deleted"),
                    ("USER_DEACTIVATED", "User account deactivated"),
                    ("USER_REACTIVATED", "User account reactivated"),
                ],
                max_length=32,
            ),
        ),
    ]
