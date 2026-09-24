from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.db.models import Prefetch

from .models import Comment, Post, Tag


def post_detail(request, slug):
    post = get_object_or_404(
        Post.objects.filter(published=True)
        .select_related("author")
        .prefetch_related(
            Prefetch("tags", queryset=Tag.objects.order_by("slug"), to_attr="benchmark_tags"),
            Prefetch(
                "comments",
                queryset=Comment.objects.filter(approved=True).order_by("ordinal", "id"),
                to_attr="approved_comments",
            ),
        ),
        slug=slug,
    )
    data = {
        "post": {
            "slug": post.slug,
            "title": post.title,
            "author": {"name": post.author.name, "email": post.author.email},
            "published_at": post.published_at.isoformat(),
            "reading_minutes": post.reading_minutes,
            "score": format(post.score, ".2f"),
            "body_word_count": len(post.body.split()),
            "tags": [tag.name for tag in post.benchmark_tags],
            "comments": [
                {
                    "author": comment.display_name,
                    "body": comment.body,
                    "created_at": comment.created_at.isoformat(),
                }
                for comment in post.approved_comments
            ],
            "url": reverse("post-detail", kwargs={"slug": post.slug}),
        }
    }
    return JsonResponse(data)
