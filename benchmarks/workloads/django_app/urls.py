from django.urls import path

from .views import post_detail


urlpatterns = [path("posts/<slug:slug>/", post_detail, name="post-detail")]
