from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import AuditLog
from .throttling import (
    AuthLoginThrottle,
    AuthRefreshThrottle,
    AuthRegisterThrottle,
    GlobalAnonThrottle,
)
from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [GlobalAnonThrottle, AuthLoginThrottle]


class RefreshView(TokenRefreshView):
    """JWT refresh (standard simplejwt behavior + endpoint throttling)."""

    throttle_classes = [GlobalAnonThrottle, AuthRefreshThrottle]


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(
            self.get_object(), data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [GlobalAnonThrottle, AuthRegisterThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        AuditLog.record(
            user,
            AuditLog.Action.REGISTER,
            object_type="auth",
            object_repr=user.display_name,
            request=request,
        )
        # An external-organization sign-up also creates the organization in
        # the PENDING state; record that separately so the verification trail
        # starts at registration. No credentials are issued here.
        if user.is_external_organization and user.organization_ref_id:
            AuditLog.record(
                user,
                AuditLog.Action.ORGANIZATION_REGISTERED,
                object_type="organization",
                object_id=user.organization_ref_id,
                object_repr=str(user.organization_ref),
                detail="External organization registered at sign-up",
                request=request,
            )
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )
