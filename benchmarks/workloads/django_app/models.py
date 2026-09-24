from django.db import models


class Author(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    bio = models.TextField()


class Tag(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)


class Post(models.Model):
    ordinal = models.PositiveIntegerField(unique=True)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="posts")
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=100, unique=True)
    body = models.TextField()
    published = models.BooleanField(default=True)
    published_at = models.DateTimeField()
    reading_minutes = models.PositiveSmallIntegerField()
    score = models.DecimalField(max_digits=5, decimal_places=2)
    tags = models.ManyToManyField(Tag, related_name="posts", blank=True)


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    ordinal = models.PositiveSmallIntegerField()
    display_name = models.CharField(max_length=80)
    body = models.TextField()
    created_at = models.DateTimeField()
    approved = models.BooleanField(default=True)

    class Meta:
        ordering = ("ordinal", "id")
