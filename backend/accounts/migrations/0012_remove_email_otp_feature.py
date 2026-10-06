from django.db import migrations


class Migration(migrations.Migration):
    """Remove the email-OTP verification feature.

    Data-preserving: no user rows are deleted. The one-to-one OTP session
    table is dropped and the ``first_login_verified`` flag is removed from
    ``User``. Historical accounts that were still pending verification
    (first_login_verified=False) become authenticated accounts — the flag
    no longer exists, so no login path can refuse them.
    """

    dependencies = [
        ("accounts", "0011_seed_internal_organizations"),
    ]

    operations = [
        migrations.DeleteModel(name="EmailOTPVerification"),
        migrations.RemoveField(model_name="user", name="first_login_verified"),
    ]
