from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AuditLog, EmailOTPVerification
from . import twofa

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "organization",
            "phone",
            "display_name",
        )
        read_only_fields = ("role",)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = (
            "username",
            "password",
            "first_name",
            "last_name",
            "email",
            "organization",
            "phone",
        )

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """JWT login that also returns the authenticated user profile.

    Two-factor handling: when the account has a confirmed TOTP device the
    response contains ``mfa_required`` + a short-lived ``mfa_token`` and NO
    tokens — the SPA must complete ``/api/auth/2fa/verify-login/`` before it
    is authenticated.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        # First-time Google accounts must finish email OTP verification
        # before ANY authentication — password login on such an account is
        # refused (it has no usable password anyway, but block defensively).
        if EmailOTPVerification.objects.filter(
            user=self.user, verified_at__isnull=True
        ).exists():
            raise serializers.ValidationError(
                "Finish verifying your email from the Google sign-in screen "
                "before signing in with a password."
            )
        if twofa.has_2fa(self.user):
            return {
                "mfa_required": True,
                "mfa_token": twofa.issue_challenge(self.user),
            }
        AuditLog.record(
            self.user,
            AuditLog.Action.LOGIN,
            object_type="auth",
            object_repr="Password sign-in",
        )
        data["user"] = UserSerializer(self.user).data
        return data