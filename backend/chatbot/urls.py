from django.urls import path

from .views import chat

urlpatterns = [
    path("chatbot/", chat, name="chatbot-chat"),
]
