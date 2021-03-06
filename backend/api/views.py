from django.http import JsonResponse
from django.db.models import Q
# Create your views here.
from rest_framework import generics, permissions, status

from api.serializers import PostSerializer, UserSerializer
from api.models import Post, User
from api.permissions import AuthorPermission, ViewPermission, FriendViewPermission
from api.elasticsearchApi import post_search, post_create
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from django.http import Http404


class Register(APIView):
    permission_classes = (
        permissions.AllowAny,
    )

    def post(self, request):
        serialized = UserSerializer(data=request.data, context={'request': request})
        if serialized.is_valid():
            User.objects.create_user(
                username=serialized.initial_data['username'],
                password=serialized.initial_data['password'],
                email=serialized.initial_data['email'],
            )
            return Response(serialized.initial_data, status=status.HTTP_201_CREATED)
        else:
            return Response(serialized.errors, status=status.HTTP_400_BAD_REQUEST)


class FeedSearchList(APIView):
    permission_classes = (
        FriendViewPermission,
    )

    def post(self, request):
        text = request.data.get('text', None)
        if text is None:
            return Response({"error": "Empty request"}, status=status.HTTP_400_BAD_REQUEST)
        vals = post_search(request.user, text)[:5]
        data = Post.objects.all().filter(pk__in=vals)
        serializer = PostSerializer(data, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class PostList(generics.ListCreateAPIView):
    model = Post
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    permission_classes = [
        AuthorPermission,
    ]

    def perform_create(self, serializer):
        post = serializer.save(author=self.request.user)
        post_create(self.request.user, serializer.validated_data['body'], post.id)


class PostDetail(generics.RetrieveUpdateDestroyAPIView):
    model = Post
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    permission_classes = [
        AuthorPermission,
    ]

    def create(self, request, *args, **kwargs):
        serialized = PostSerializer(data=request.data)
        if serialized.is_valid():
            serialized.save()
            post_create(request.user, serialized.validated_data['body'])
            return Response(serialized.validated_data, status=status.HTTP_201_CREATED)
        else:
            return Response(serialized.errors, status=status.HTTP_400_BAD_REQUEST)


class UserPostList(PostList):
    def get_queryset(self):
        queryset = super(UserPostList, self).get_queryset()
        return queryset.filter(author__username=self.kwargs.get('username'))


class CurrentUserPostList(PostList):
    def get_queryset(self):
        user = self.request.user
        queryset = super(CurrentUserPostList, self).get_queryset()
        return queryset.filter(author=user.id)


class UserList(generics.ListCreateAPIView):
    model = User
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [
        AuthorPermission,
    ]


class UserDetail(generics.RetrieveAPIView):
    model = User
    queryset = User.objects.all()
    serializer_class = UserSerializer
    lookup_field = 'username'
    permission_classes = [
        ViewPermission,
    ]


class CurrentUserDetail(UserDetail):
    def get_object(self):
        user = self.request.user
        if user.is_anonymous:
            raise Http404
        return user


class UserFriendList(generics.ListAPIView):
    model = User
    serializer_class = UserSerializer
    lookup_field = 'username'
    permission_classes = [
        ViewPermission,
    ]

    def get_queryset(self):
        user = User.objects.get(username=self.kwargs.get('username'))
        return user.friends


class CurrentUserFriendList(UserFriendList):
    permission_classes = [
        AuthorPermission,
    ]

    def get_queryset(self):
        user = self.request.user
        return user.friends

    def post(self, request):
        try:
            user = User.objects.get(username=request.data['username'])
        except User.DoesNotExist:
            return JsonResponse({'username': 'No such a user'}, status=status.HTTP_404_NOT_FOUND)
        if user == request.user:
            return JsonResponse({'username': 'You can\'t be your friend'}, status=status.HTTP_409_CONFLICT)
        if len(request.user.friends.all().filter(username=user.username)) > 0:
            return JsonResponse({'username': 'Already a friend'}, status=status.HTTP_409_CONFLICT)
        request.user.friends.add(user)
        serializer = self.get_serializer(user)
        return Response(serializer.data)


class WallPostsPagination(PageNumberPagination):
    page_size = 10


class WallPosts(generics.ListAPIView):
    model = Post
    serializer_class = PostSerializer
    pagination_class = WallPostsPagination

    def get_queryset(self):
        user = self.request.user
        return Post.objects.filter(Q(author__in=user.friends.all()) | Q(author=user))
