#!/usr/bin/env bash
set -e

echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Creating/updating admin account..."
python manage.py shell <<'PY'
from django.contrib.auth import get_user_model

User = get_user_model()

username = "admin"
password = "admin1234"
email = "admin@sasreserve.local"

user, created = User.objects.get_or_create(
    username=username,
    defaults={
        "email": email,
    },
)

user.set_password(password)

# Django admin privileges
user.is_staff = True
user.is_superuser = True
user.is_active = True

# Your application's admin role
if hasattr(user, "role"):
    try:
        user.role = "ADMIN"
    except Exception:
        pass

user.save()

if created:
    print("==> Admin account created successfully.")
else:
    print("==> Admin account already exists. Credentials/privileges updated.")

print(f"==> Admin username: {username}")
PY

echo "==> Build completed successfully."