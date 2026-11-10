"""Drop the designation for the removed post-approval letter workflow.

The flag only ever granted access to the deleted approval-letter signing
module; it never affected reservations, accounts or uploaded documents.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0024_active_assistant_campus_director_unique'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='is_approval_signatory',
        ),
    ]
