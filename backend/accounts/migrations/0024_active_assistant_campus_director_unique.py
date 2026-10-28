from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0023_alter_user_options")]

    operations = [
        migrations.RemoveConstraint(
            model_name="user",
            name="unique_assistant_campus_director_role",
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    role="ASSISTANT_CAMPUS_DIRECTOR_ADMIN_FINANCE", is_active=True
                ),
                fields=("role",),
                name="unique_assistant_campus_director_role",
            ),
        ),
    ]
