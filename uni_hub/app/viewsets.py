from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from .permissions import *
from .models import *
from .serializers import *
from .pagination import *
from django.db.models import Q, Count, Max, F
from django.db import transaction

from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from .models import Post, Community
from .serializers import PostSerializer
from .email_templates import AnnouncementNotificationEmail

# Viewset for posting related functions, including creating global posts,
# community posts, comments, likes, and filtering returned posts for the home page
class PostViewSet(viewsets.ModelViewSet):
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    # Default get returns global posts
    def get_queryset(self):
        queryset = Post.objects.all().order_by("-created_at")
        request = self.request
        community_id = request.query_params.get("community")

        # If all show global posts
        if community_id == "all":
            return queryset.filter(community__community_name="Global Community (News Feed)")

        return queryset
    
    # For keeping liked status updated visually
    # Sending the user as context in serializer requests
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    # Creates either global or community post
    def perform_create(self, serializer):
        request = self.request
        community_id = self.kwargs.get("community_id") or request.data.get("community")

        if community_id:
            try:
                community = Community.objects.get(id=community_id)
            except Community.DoesNotExist:
                return Response({"error": "Community not found."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            try:
                community = Community.objects.get(community_name="Global Community (News Feed)")
            except Community.DoesNotExist:
                return Response({"error": "Global Community does not exist."}, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(user=request.user, community=community)

    # Overriding destroy to also remove likes and comments when a post is deleted
    def destroy(self, request, *args, **kwargs):
        try:
            post = self.get_object()

            # If owner of the post
            is_post_owner = post.user == request.user
            # If community leader of the community in which the post was made
            is_community_owner = post.community and post.community.is_community_owner == request.user

            # Error if neither
            if not (is_post_owner or is_community_owner):
                return Response({"error": "You cannot delete a post that isn't your own."}, status=status.HTTP_403_FORBIDDEN)
            
        except Post.DoesNotExist:
            return Response({"error": "Post not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            # Get the hashtags in the post before deleting it
            related_hashtags = list(post.hashtags.all())
            # Delete related likes
            post.post_likes.all().delete()
            # Delete related comments
            post.comments.all().delete()
            # Delete the post itself
            post.delete()
            # Delete the hashtags which are no longer in use
            for hashtag in related_hashtags:
                if not hashtag.posts.exists():
                    hashtag.delete()
            # Return success
            return Response({"success": "Post and related comments/likes have been deleted."}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            # Rollback the transaction if any error occurs
            # Prevents likes and comments being deleted but not the post
            transaction.set_rollback(True)
            return Response({"error": "Error deleting post and related data."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    #GET will list comments, POST will create a comment
    @action(detail=True, methods=["get", "post"], url_path="comments")
    def comments(self, request, pk=None):
        try:
            post = Post.objects.get(pk=pk)
        except Post.DoesNotExist:
            return Response({"error": "Post not found."}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "GET":
            comments = Comment.objects.filter(post=post).order_by("created_at")
            serializer = CommentSerializer(comments, many=True)
            return Response(serializer.data)

        if request.method == "POST":
            serializer = CommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(user=request.user, post=post)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    # Liked/unlikes a post
    @action(detail=True, methods=["post"], url_path="toggle-like")
    def toggle_like(self, request, pk=None):
        try:
            post = Post.objects.get(pk=pk)
        except Post.DoesNotExist:
            return Response({"error": "Post not found."}, status=status.HTTP_404_NOT_FOUND)

        like, created = PostLike.objects.get_or_create(user=request.user, post=post)

        if not created:
            like.delete()
            liked = False
        else:
            liked = True

        like_count = PostLike.objects.filter(post=post).count()

        return Response({
            "liked": liked,
            "like_count": like_count
        }, status=status.HTTP_200_OK)
    
    # Returns posts by the passed community id
    @action(detail=False, methods=["get"], url_path="community")
    def community(self, request):
        community_id = request.query_params.get("community_id")

        if not community_id:
            return Response({"detail": "Community not found."}, status=404)
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({"detail": "Community not found."}, status=404)

        # Check if the user is a member of this community
        user = request.user
        is_member = UserCommunity.objects.filter(user=user, community_id=community_id).exists()
            
        # Base query to get posts from the community
        posts_query = Q(community_id=community_id)
            
        # If not a member, exclude members-only posts
        if not is_member:
            posts_query &= Q(is_members_only=False)
                
        # Get posts based on the filter
        posts = Post.objects.filter(posts_query).order_by("-created_at")

        # Pagination
        paginator = StandardResultsSetPagination()
        paginated_posts = paginator.paginate_queryset(posts, request)
        serializer = self.get_serializer(paginated_posts, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    # Returns posts by the passed user id
    @action(detail=False, methods=["get"], url_path="user")
    def user(self, request):
        user_id = request.query_params.get("user_id")

        if not user_id:
            return Response({"detail": "User posts not found."}, status=404)

        # Get posts from the specified community
        posts = Post.objects.filter(user_id=user_id).order_by("-created_at")

        # Pagination
        paginator = StandardResultsSetPagination()
        paginated_posts = paginator.paginate_queryset(posts, request)
        serializer = self.get_serializer(paginated_posts, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    # Returns posts by the user's followed profiles
    @action(detail=False, methods=["get"], url_path="following")
    def following(self, request):
        user = request.user
        following = Follow.objects.filter(following_user=user).select_related("followed_user")
        following_users = [f.followed_user for f in following]


        posts = Post.objects.filter(user__in=following_users).order_by("-created_at")
        paginator = StandardResultsSetPagination()
        paginated_posts = paginator.paginate_queryset(posts, request)
        serializer = self.get_serializer(paginated_posts, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    # Returns posts by the user's joined communities
    @action(detail=False, methods=["get"], url_path="communities")
    def communities(self, request):
        # Get the communities the logged-in user is a part of
        user_communities = UserCommunity.objects.filter(user=request.user)

        # Get the community IDs from the user's communities
        community_ids = [uc.community.id for uc in user_communities]

        # Fetch posts from those communities
        posts = Post.objects.filter(community_id__in=community_ids).exclude(
        community__community_name="Global Community (News Feed)"
    ).exclude(user=request.user).order_by("-created_at")

        # Serialize, paginate, and return the posts
        paginator = StandardResultsSetPagination()
        paginated_posts = paginator.paginate_queryset(posts, request)
        # Serialize the paginated posts
        serializer = self.get_serializer(paginated_posts, many=True)
        # Return the paginated response
        return paginator.get_paginated_response(serializer.data)
    
    @action(detail=False, methods=["get"], url_path="hashtag")
    def by_hashtag(self, request):
        hashtag_name = request.query_params.get("hashtag")

        if not hashtag_name:
            return Response({"error": "Hashtag is required to filter posts by hashtag."}, status=status.HTTP_400_BAD_REQUEST)

        posts = Post.objects.filter(hashtags__name__iexact=hashtag_name).order_by("-created_at")

        serializer = self.get_serializer(posts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    # For searching hashtags and typeaheads
    @action(detail=False, methods=["get"], url_path="search-hashtags")
    def search_hashtags(self, request):
        query = request.query_params.get("hashtag_query", "")

        if query:
            hashtags = Hashtag.objects.filter(name__icontains=query).order_by("name")[:5]
        else:
            hashtags = Hashtag.objects.all().order_by("name")[:10]
        
        data = [{"id": tag.id, "name": tag.name} for tag in hashtags]
        return Response(data, status=status.HTTP_200_OK)

# View set for following/unfollowing users and returning list of followed/following users
class FollowViewSet(viewsets.ModelViewSet):
    # All rows in Follow table
    queryset = Follow.objects.all()
    # Use follow serializer
    serializer_class = FollowSerializer
    # Required logged in user
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # If a user ID is passed filter by that ID otherwise use logged in user id
        user_id = self.request.query_params.get("user_id")

        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Follow.objects.none()  #If user doesn't exist return no results
        else:
            user = self.request.user  #Use logged in user ID

        return Follow.objects.filter(following_user=user)  #Get users following
    
    # To follow a user
    @action(detail=False, methods=["POST"])
    def follow(self, request):
        #ID to follow
        user_id = request.data.get("user_id")

        # If user ID not provided
        if not user_id:
            return Response({"error": "User ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure the user is not trying to follow themselves
        if int(user_id) == request.user.id:
            return Response({"error": "You cannot follow yourself."}, status=status.HTTP_400_BAD_REQUEST)

        # Get user to follow details
        try:
            followed_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check if already following
        if Follow.objects.filter(following_user=request.user, followed_user=followed_user).exists():
            return Response({"error": "You are already following this user."}, status=status.HTTP_400_BAD_REQUEST)

        # Create the follow row in db
        Follow.objects.create(following_user=request.user, followed_user=followed_user)

        return Response({"success": "Followed successfully."}, status=status.HTTP_201_CREATED)

    #To unfollow a user
    @action(detail=False, methods=["DELETE"])
    def unfollow(self, request):
        #User ID to unfolow
        user_id = request.query_params.get("user_id")

        #If user not passed
        if not user_id:
            return Response({"error": "User ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        #Get user to unfollow
        try:
            followed_user = User.objects.get(id=user_id)
        #If user ID not in database
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        #Get follow row to delete
        follow = Follow.objects.filter(following_user=request.user, followed_user=followed_user).first()
        #If exists detete
        if follow:
            follow.delete()
            return Response({"success": "Unfollowed successfully."}, status=status.HTTP_204_NO_CONTENT)
        
        #Else return error
        return Response({"error": "You are not following this user."}, status=status.HTTP_400_BAD_REQUEST)

    # Gets list of followers of the given user ID
    @action(detail=False, methods=["GET"])
    def followers(self, request):
        # Get passed user ID if applicable to allow fetching of any users followers
        user_id = request.query_params.get("user_id")

        # If user ID is passed check it exists
        if user_id:  
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            user = request.user  #Use logged in user
        
        #Get list of followers
        followers = Follow.objects.filter(followed_user=user).select_related("following_user")
        #Get list of follows in json as the response
        #Using separate serializer that wont use logged in user ID, request context passed to get if logged-in user follows
        follower_data = UserFollowerSerializer([f.following_user for f in followers], many=True, context={'request': request})

        return Response(follower_data.data, status=status.HTTP_200_OK)
    
    # Gets list of followed users the given user ID
    @action(detail=False, methods=["GET"])
    def following(self, request):
        # Get passed user ID if applicable to allow fetching of any users followers
        user_id = request.query_params.get("user_id")

        # If user ID is passed check it exists
        if user_id:  
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            user = request.user  #Use logged in user
        
        # Get list of following
        following = Follow.objects.filter(following_user=user).select_related("followed_user")
        # Get list of follows
        following_users = [f.followed_user for f in following]
        # Using separate serializer that wont use logged in user ID, request context passed to get if logged-in user follows
        following_data = UserFollowingSerializer(following_users, many=True, context={'request': request})

        return Response(following_data.data, status=status.HTTP_200_OK)
    
    # Used on profile page to set the isFollowing to true/false
    @action(detail=False, methods=["GET"])
    def check_following(self, request):
        user_id = request.query_params.get("user_id")

        # If user ID not passed
        if not user_id:
            return Response({"error": "User ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # If viewing own profile just return true
        if int(user_id) == request.user.id:
            return Response({"is_following": True}, status=status.HTTP_200_OK)

        # Check user exists
        try:
            followed_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check logged-in user follows viewed user
        is_following = Follow.objects.filter(following_user=request.user, followed_user=followed_user).exists()

        return Response({"is_following": is_following}, status=status.HTTP_200_OK)
    

# View set for joining/leaving, requesting/canelling requests to join, and for leaders to approve/deny join requests on communities
# Also includes routes for returning list of a users joined/requested communties
class CommunityFollowViewSet(viewsets.ModelViewSet):
    #All rows
    queryset = UserCommunity.objects.all()
    #Use follow serializer
    serializer_class = UserCommunitySerializer
    #Required logged in user
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        #Use logged in user
        user = self.request.user  #Use logged in user ID

        return UserCommunity.objects.filter(user=user)  #Get joined communities
    
    # To follow/join a community
    @action(detail=False, methods=["POST"])
    def follow(self, request):
        # ID to follow
        community_id = request.data.get("community_id")

        # If ID not provided
        if not community_id:
            return Response({"error": "Community ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Get community to join details
        try:
            followed_community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({"error": "Community not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check if already a member
        if UserCommunity.objects.filter(user=request.user, community=followed_community).exists():
            return Response({"error": "You are already a member of this community."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if community is private, need to request to join if private
        if followed_community.privacy == "private":
            return Response({"error": "This community is private. You need to request to join."}, status=status.HTTP_403_FORBIDDEN)

        # Create the follow relationship in db
        try:
            UserCommunity.objects.create(user=request.user, community=followed_community)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"success": "Joined community successfully."}, status=status.HTTP_201_CREATED)

    # To unfollow/leave a community
    @action(detail=False, methods=["DELETE"])
    def unfollow(self, request):
        # Community ID to unfolow
        community_id = request.query_params.get("community_id")

        # If community ID not passed
        if not community_id:
            return Response({"error": "Community ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Get community to unfollow
        try:
            unfollowed_community = Community.objects.get(id=community_id)
        # If community ID not in database
        except Community.DoesNotExist:
            return Response({"error": "Community not found."}, status=status.HTTP_404_NOT_FOUND)
        
        # If trying to leave global community
        if not unfollowed_community.is_community_owner:
            return Response(
                {"error": "You cannot leave the global community."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get row to delete
        unfollow = UserCommunity.objects.filter(user=request.user, community=unfollowed_community).first()

        #If user not following
        if not unfollow:
            return Response({"error": "You are not a member of this community."}, status=status.HTTP_400_BAD_REQUEST)

        # Check user isn't leader of community (leaders cannot leave without transferring ownership)        
        if unfollow.role == "Leader":
            return Response(
                {"error": "You cannot leave the community as a leader. Please transfer leadership first."},
                status=status.HTTP_400_BAD_REQUEST
            )
    
        # If exists detete
        try:
            unfollow.delete()
            return Response({"success": "Successfully left the community."}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    # Request to transfer ownership of a community 
    @action(detail=True, methods=["POST"], url_path="transfer-ownership")
    def transfer_ownership(self, request, pk=None):
        new_owner_id = request.data.get("new_owner_id")
        community = self.get_object()

        if community.is_community_owner != request.user:
            return Response({"error": "Only the current owner can transfer ownership."}, status=403)

        try:
            new_owner = User.objects.get(id=new_owner_id)
            UserCommunity.objects.filter(user=new_owner, community=community).update(role="Leader")
            UserCommunity.objects.filter(user=request.user, community=community).update(role="Member")
            community.is_community_owner = new_owner
            community.save()
            return Response({"success": "Ownership transferred."})
        except User.DoesNotExist:
            return Response({"error": "New owner user not found."}, status=404)  
              
    # Requests to follow a community
    @action(detail=False, methods=["POST"])
    def request_follow(self, request):
        community_id = request.data.get("community_id")

        # If community ID not passed
        if not community_id:
            return Response({"error": "Community ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Get community details
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({"error": "Community not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check privacy, if not private dont attempt request
        if community.privacy != "private":
            return Response({"error": "This community is not private. You can join directly."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the user has already requested to join this community
        if UserRequestCommunity.objects.filter(user=request.user, community=community).exists():
            return Response({"error": "You have already requested to join this community."}, status=status.HTTP_400_BAD_REQUEST)

        # Create the request to join community
        try:
            user_request = UserRequestCommunity.objects.create(user=request.user, community=community)
            return Response({"success": "Request to join community sent."}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
    # To cancel a community request to join
    @action(detail=False, methods=["DELETE"])
    def cancel_follow_request(self, request):
        # Community ID to cancel request
        community_id = request.query_params.get("community_id")

        # If community ID not passed
        if not community_id:
            return Response({"error": "Community ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Get community to cancel request
        try:
            unfollowed_community = Community.objects.get(id=community_id)
        # If community ID not in database
        except Community.DoesNotExist:
            return Response({"error": "Community not found."}, status=status.HTTP_404_NOT_FOUND)

        # Get request row to delete
        unfollow = UserRequestCommunity.objects.filter(user=request.user, community=unfollowed_community).first()
        # If exists detete
        if unfollow:
            unfollow.delete()
            return Response({"success": "Successfully cancelled the follow request."}, status=status.HTTP_204_NO_CONTENT)
        
        # Else return error
        return Response({"error": "You are not a member of this community."}, status=status.HTTP_400_BAD_REQUEST)
    
    # Gets user communities with the user's role
    @action(detail=False, methods=["GET"])
    def user_communities_list(self, request):
        # If a user ID is passed filter by that ID otherwise use logged in user id
        user_id = request.GET.get('user_id')

        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            user = request.user # Use logged in user

        # If user not found
        if not user:
            return Response({"error": "Missing user credentials."}, status=status.HTTP_400_BAD_REQUEST)

        # Return list of communities in response
        user_communities = UserCommunity.objects.filter(
            user_id=user.id
            ).exclude(
            community__is_community_owner__isnull=True  # Filter out global community
            ).select_related('community')
        serializer = UserCommunitySerializer(user_communities, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)   
        

    @action(detail=False, methods=["GET"])
    def followers(self, request): # List of joined communities for the logged-in user
        user = request.user  # Use logged in user
        
        # Get list of joined communities
        followed_communities = UserCommunity.objects.filter(user=user).select_related("community")
        # Get list of communities with details in json as the response
        community_data = UserCommunityFollowerSerializer([f.community for f in followed_communities], many=True)

        return Response(community_data.data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=["GET"])
    def follow_requests(self, request): # List of outgoing requests of the logged-in user
        user = request.user  # Use logged in user
        
        # Get list of requested communities
        requested_communities = UserRequestCommunity.objects.filter(user=user).select_related("community")
        # Get list of communities with details in json as the response
        community_data = UserCommunityFollowerSerializer([f.community for f in requested_communities], many=True)

        return Response(community_data.data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=["GET"])
    def follow_requests_for_community(self, request):
        # Get the community_id from query params
        community_id = request.query_params.get("community_id")

        # If none passed error
        if not community_id:
            return Response({"error": "Community ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Get community details
        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({"error": "Community not found."}, status=status.HTTP_404_NOT_FOUND)

        # Check if the logged-in user is the community owner
        if community.is_community_owner != request.user:
            return Response({"error": "You do not have the required permissions to view this."}, status=status.HTTP_403_FORBIDDEN)

        # Retrieve the list of follow requests for this community
        try:
            # Filter by the given community id
            follow_requests = UserRequestCommunity.objects.filter(community=community)
        except Exception as e:
            return Response({"error": f"Error fetching follow requests: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Serialize and return the follow requests
        follow_requests_serializer = UserRequestCommunitySerializer(follow_requests, many=True)
        return Response(follow_requests_serializer.data, status=status.HTTP_200_OK)
    
    # Leader denies a request to join
    @action(detail=False, methods=["DELETE"], permission_classes=[IsAuthenticated, IsCommunityLeader])
    def deny_follow_request(self, request):
        # Request ID to deny
        request_id = request.query_params.get("request_id")

        #If request ID not passed
        if not request_id:
            return Response({"error": "Request ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get request details
        try:
            join_request = UserRequestCommunity.objects.filter(id= request_id).first()
        #If request ID not in database
        except UserRequestCommunity.DoesNotExist:
            return Response({"error": "Request not found."}, status=status.HTTP_404_NOT_FOUND)
        
        # Delete join request
        try:
            join_request.delete()
            return Response({"success": "Follow request approved and user added to the community."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": "Error deleting the join request."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 

    # Leader approves a request to join
    @action(detail=False, methods=["DELETE"], permission_classes=[IsAuthenticated, IsCommunityLeader])
    def approve_follow_request(self, request):
        # Request ID to deny
        request_id = request.query_params.get("request_id")

        # If request ID not passed
        if not request_id:
            return Response({"error": "Request ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get request details
        try:
            join_request = UserRequestCommunity.objects.filter(id= request_id).first()
        # If request ID not in database
        except UserRequestCommunity.DoesNotExist:
            return Response({"error": "Request not found."}, status=status.HTTP_404_NOT_FOUND)
        
        # Create follow relationship and delete the join request
        try:
            # Prevents user follow creation without also deleting join request
            with transaction.atomic():
                user_community = UserCommunity.objects.create(
                    user=join_request.user,
                    community=join_request.community
                )
                join_request.delete()

            return Response({"success": "Follow request approved and user added to the community."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": "Error approving the request to join."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 

    

class AnnouncementViewSet(viewsets.ModelViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        community_id = self.request.query_params.get('community_id')
        if community_id:
            qs = qs.filter(community_id=community_id)
        return qs

    def perform_create(self, serializer):
        community_id = self.request.data.get('community_id')
        if not community_id:
            raise serializers.ValidationError({"community_id": "This field is required."})

        announcement = serializer.save(created_by=self.request.user, community_id=community_id)
        
        #Send emails to all community members
        community = announcement.community
        community_members = UserCommunity.objects.filter(community=community).select_related('user')
        
        for member in community_members:
            #Dont send to the announcement creator
            if member.user != self.request.user:
                AnnouncementNotificationEmail.send_notification(
                    recipient=member.user,
                    announcement=announcement,
                    community=community
                )
        
        return announcement


class CommunityViewSet(viewsets.ModelViewSet):
    serializer_class = CommunitySerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    def get_queryset(self):
        """
        Customize the queryset based on query parameters.
        This handles filtering and ordering.
        """
        queryset = Community.objects.filter(is_community_owner__isnull=False)
        
        queryset = queryset.annotate(member_count=Count('user_communities'))
        
        search_query = self.request.query_params.get('search', None)
        keywords = self.request.query_params.get('keywords', None)
        privacy = self.request.query_params.get('privacy', None)
        ordering = self.request.query_params.get('ordering', '-id')
        
        #Search text (looks in name and description)
        if search_query:
            queryset = queryset.filter(
                Q(community_name__icontains=search_query) | 
                Q(description__icontains=search_query)
            )
        
        #Keywords filter
        if keywords:
            keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
            if keyword_list:
                #Filter communities that have ALL of the specified keywords
                for keyword in keyword_list:
                    queryset = queryset.filter(keywords__keyword=keyword)
                queryset = queryset.distinct()
        
        #Privacy
        if privacy and privacy != 'all':
            queryset = queryset.filter(privacy=privacy)
        
        #Sort ordering
        if ordering == 'community_name':
            queryset = queryset.order_by('community_name')
        elif ordering == '-community_name':
            queryset = queryset.order_by('-community_name')
        elif ordering == 'member_count':
            queryset = queryset.order_by('member_count')
        elif ordering == '-member_count':
            queryset = queryset.order_by('-member_count')
        else:
            queryset = queryset.order_by('-id' if ordering == '-id' else 'id')
        
        return queryset

    def get_serializer_context(self):
        #Pass the request to the serializer to access request.user in create()
        return {"request": self.request}
    
    def destroy(self, request, *args, **kwargs):
        community = self.get_object()

        # Only the community owner can delete their own community
        if community.is_community_owner != request.user:
            return Response({"error": "Only the community leader can delete the community."},
                            status=status.HTTP_403_FORBIDDEN)

        try:
            # Ensures full deletion or no deletion
            with transaction.atomic():
                # Delete community posts and their related likes/comments
                posts = community.posts.all()
                for post in posts:
                    post.post_likes.all().delete()
                    post.comments.all().delete()
                    post.delete()

                # Delete memberships
                UserCommunity.objects.filter(community=community).delete()

                # Delete the community
                community.delete()

            return Response({"success": "Community and all related data deleted successfully."},
                            status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": "An error occurred while deleting the community."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["POST"], url_path="transfer-ownership")
    def transfer_ownership(self, request, pk=None):
        community = self.get_object()
        new_owner_id = request.data.get("new_owner_id")

        # Only current owner can transfer ownership
        if community.is_community_owner != request.user:
            return Response({"error": "You are not the owner of this community."}, status=status.HTTP_403_FORBIDDEN)

        try:
            new_owner = User.objects.get(id=new_owner_id)
        except User.DoesNotExist:
            return Response({"error": "New owner not found."}, status=status.HTTP_404_NOT_FOUND)

        # Make sure the new owner is a current member
        try:
            membership = UserCommunity.objects.get(user=new_owner, community=community)
        except UserCommunity.DoesNotExist:
            return Response({"error": "Selected user is not a member of the community."}, status=status.HTTP_400_BAD_REQUEST)

        # Transfer ownership
        community.is_community_owner = new_owner
        community.save()

        # Update roles
        UserCommunity.objects.filter(user=request.user, community=community).update(role="Member")
        membership.role = "Leader"
        membership.save()

        return Response({"success": "Ownership transferred successfully."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=["POST"], url_path="update-role")
    def update_role(self, request, pk=None):
        community = self.get_object()
        user_id = request.data.get("user_id")
        new_role = request.data.get("role")
        COMMUNITY_ROLES = (
            ("Leader", "Leader"),
            ("EventManager", "Event Manager"),
            ("Member", "Member"),
            )
        if community.is_community_owner != request.user:
            return Response({"error": "Only the leader can update roles."}, status=403)

        try:
            user_community = UserCommunity.objects.get(community=community, user__id=user_id)
        except UserCommunity.DoesNotExist:
            return Response({"error": "User is not a member of this community."}, status=404)

        if new_role not in dict(COMMUNITY_ROLES):
            return Response({"error": "Invalid role."}, status=400)

        user_community.role = new_role
        user_community.save()

        return Response({"success": "Role updated successfully."})

class AchievementViewSet(viewsets.ModelViewSet):
    serializer_class = AchievementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Uses passed user_id or logged-in user
        user_id = self.request.query_params.get('user_id')
        
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Achievement.objects.none()
        else:
            user = self.request.user

        # Return in order of date achieved
        return Achievement.objects.filter(user=user).order_by("-date_achieved")
        
    def perform_create(self, serializer):
        # When achievement created assign user to logged-in user
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        # Modifying destory so that user can only delete their own achievements
        achievement = self.get_object()
        if achievement.user != request.user:
            return Response({"error": "You can only delete your own achievements."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

import logging
from datetime import timezone as dtTimezone

logger = logging.getLogger(__name__)
from .zoom_utils import create_zoom_meeting
class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all().order_by('-date')
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated, IsEventManager]

    # Filter events by community_id if provided in query params
    def get_queryset(self):
        qs = super().get_queryset()
        community_id = self.request.query_params.get('community_id')
        if community_id:
            qs = qs.filter(community_id=community_id)
        return qs.select_related('community')

    # Save event when creating
    def perform_create(self, serializer):
        validated = serializer.validated_data
        event_type = validated.get('event_type')
        title = validated.get('event_name')
        start_time = validated.get('date')  
        location = validated.get('location')

        print(f"[DEBUG] Event type: {event_type}")
        print(f"[DEBUG] Validated data: {validated}")

        if event_type in ['meeting', 'webinar'] and start_time:
            start_time_iso = start_time.astimezone(dtTimezone.utc).isoformat()
            zoom_data = create_zoom_meeting(title, start_time_iso)
            join_url = zoom_data.get("join_url")
            if join_url:
                location = f"{location or 'Online'} | Zoom Link: {join_url}"
                print(f"        Topic: {zoom_data.get('topic')}")
                print(f"        Start: {zoom_data.get('start_time')}")
                print(f"        Duration: {zoom_data.get('duration')} mins")
            else:
                print(f"[ZOOM] Failed to create meeting for '{title}'")
        else:
            print("[ZOOM] No Zoom meeting created – missing start time or event_type mismatch.")

        serializer.save(location=location)


    # Custom action to get events for a specific community
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated])
    def community_events(self, request, pk=None):
        community = None
        try:
            community = Community.objects.get(id=pk)
        except (Community.DoesNotExist, ValueError, TypeError):
            try:
                event = self.get_object()
                community = event.community
            except Exception:
                return Response({"error": "Could not determine community from provided ID."}, status=status.HTTP_400_BAD_REQUEST)

        if not community:
            return Response({"error": "Community not found."}, status=status.HTTP_404_NOT_FOUND)

        events = Event.objects.filter(community=community).select_related('community')
        serializer = self.get_serializer(events, many=True)
        return Response(serializer.data)

class PinnedPostViewSet(viewsets.ModelViewSet):
    """
    Viewset for managing pinned posts in communities.
    Community leaders can pin/unpin posts.
    """
    serializer_class = PinnedPostSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Fetch pinned posts for a specific community.
        """
        community_id = self.request.query_params.get('community_id')
        if community_id:
            return PinnedPost.objects.filter(community_id=community_id).order_by('order')
        return PinnedPost.objects.none()
    
    @action(detail=False, methods=["POST"])
    def pin_post(self, request):
        community_id = request.data.get('community_id')
        post_id = request.data.get('post_id')
        
        # Validate input
        if not community_id or not post_id:
            return Response(
                {"error": "Both community_id and post_id are required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Get community and post
        try:
            community = Community.objects.get(id=community_id)
            post = Post.objects.get(id=post_id)
        except (Community.DoesNotExist, Post.DoesNotExist):
            return Response(
                {"error": "Community or Post not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        # Check if user is community leader
        if community.is_community_owner != request.user:
            return Response(
                {"error": "Only community leaders can pin posts."}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        # Check if post belongs to the community
        if post.community != community:
            return Response(
                {"error": "This post does not belong to the specified community."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Check if post is already pinned
        if PinnedPost.objects.filter(post=post, community=community).exists():
            return Response(
                {"error": "This post is already pinned."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Check if community already has 3 pinned posts
        pinned_count = PinnedPost.objects.filter(community=community).count()
        if pinned_count >= 3:
            return Response(
                {"error": "A community can have at most 3 pinned posts. Please unpin a post before pinning another."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Calculate the order for the new pinned post
        max_order_result = PinnedPost.objects.filter(community=community).aggregate(Max('order'))
        current_max_order = max_order_result.get('order__max') #Extract the maximum order value found. It be 'None' if first post
        next_order = (current_max_order if current_max_order is not None else -1) + 1  #If there are existing pinned posts (current_max_order is not None),

        # Create pinned post
        pinned_post = PinnedPost.objects.create(
            post=post,
            community=community,
            pinned_by=request.user,
            order=next_order
        )
        
        serializer = PinnedPostSerializer(pinned_post)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=["DELETE"])
    def unpin_post(self, request):
        post_id = request.query_params.get('post_id')
        
        # Validate input
        if not post_id:
            return Response(
                {"error": "post_id is required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Get pinned post
        try:
            pinned_post = PinnedPost.objects.get(post_id=post_id)
        except PinnedPost.DoesNotExist:
            return Response(
                {"error": "Pinned post not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        community = pinned_post.community

        # Check if user is community leader
        if pinned_post.community.is_community_owner != request.user:
            return Response(
                {"error": "Only community leaders can unpin posts."}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        

         # Re-order remaining posts after deletion
        deleted_order = pinned_post.order
        pinned_post.delete()

        # Decrement the order of all subsequent posts in the same community
        # `F('order') - 1` tells the database: For each matching row, set its
        # order field to its own current order value minus 1.
        PinnedPost.objects.filter(
            community=community,
            order__gt=deleted_order # Only affect posts that came afteR the deleted one
        ).update(order=F('order') - 1)

        return Response(
            {"success": "Post unpinned successfully."}, 
            status=status.HTTP_204_NO_CONTENT
        )


    @action(detail=False, methods=['POST'], url_path='reorder')
    def reorder_pinned_posts(self, request):
        community_id = request.data.get('community_id')
        # Expect a list of pinned post IDs (the PinnedPost model ID) in the desired new order.
        ordered_pinned_post_ids = request.data.get('ordered_pinned_post_ids')

        if not community_id or not isinstance(ordered_pinned_post_ids, list):
            return Response(
                {"error": "community_id and a list of ordered_pinned_post_ids are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            community = Community.objects.get(id=community_id)
        except Community.DoesNotExist:
            return Response({"error": "Community not found."}, status=status.HTTP_404_NOT_FOUND)

        # Validation check
        if community.is_community_owner != request.user:
            return Response(
                {"error": "Only the community leader can reorder pinned posts."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Verify that the provided IDs correspond to actual PinnedPost entries for this community
        current_pinned_posts = PinnedPost.objects.filter(community=community)
        current_pinned_post_ids = set(current_pinned_posts.values_list('id', flat=True))
        provided_ids_set = set(ordered_pinned_post_ids)

        if current_pinned_post_ids != provided_ids_set:
            return Response(
                {"error": "The provided list of IDs does not match the currently pinned posts for this community."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update the order based on the provided list
        for index, pinned_post_id in enumerate(ordered_pinned_post_ids):
            PinnedPost.objects.filter(id=pinned_post_id, community=community).update(order=index) # Start order from 0

        # Fetch the updated list to return
        updated_pinned_posts = PinnedPost.objects.filter(community=community).order_by('order')
        serializer = self.get_serializer(updated_pinned_posts, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)



class UserSearchViewSet(viewsets.ModelViewSet):
    serializer_class = UserSearchSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        """
        Filter users based on search query, university, interests, and apply ordering.
        Exclude the requesting user from the results.
        """
        request_user = self.request.user
        # Start with all active users, excluding the current user
        queryset = User.objects.filter(is_active=True) \
                          .exclude(id=request_user.id) \
                          .exclude(is_superuser=True) \
                          .select_related('university')

        search_query = self.request.query_params.get('search', None)
        university_id = self.request.query_params.get('university', None)
        interests = self.request.query_params.get('interests', None)
        ordering = self.request.query_params.get('ordering', 'last_name')

        # Text search (first name, last name, bio)
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(bio__icontains=search_query)
            )

        # University filter
        if university_id:
            queryset = queryset.filter(university__id=university_id)
            
        # Interests filter
        if interests:
            interest_list = [i.strip() for i in interests.split(',') if i.strip()]
            if interest_list:
                # Filter users that have ALL of the specified interests
                for interest in interest_list:
                    queryset = queryset.filter(user_interests__interest__interest=interest)
                queryset = queryset.distinct()

        # Sort ordering
        valid_ordering_fields = {
            'last_name': 'last_name',
            '-last_name': '-last_name',
            'first_name': 'first_name',
            '-first_name': '-first_name',
            'date_joined': 'date_joined',
            '-date_joined': '-date_joined',
        }
        order_field = valid_ordering_fields.get(ordering, 'last_name') 
        queryset = queryset.order_by(order_field)

        return queryset

    def get_serializer_context(self):
        """
        Pass the request context to the serializer.
        Needed for checking the 'is_following' status.
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context



from django.utils import timezone
import datetime

class EventSearchViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet dedicated to searching events with filtering options.
    This is a read-only viewset as it's only used for searching events.
    """
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def get_queryset(self):
        """
        Filter events based on search query, event type, date filters, and apply ordering.
        Only shows events from public communities or private communities the user is a member of.
        """
        user = self.request.user
        
        #Get communities the user is a member of
        user_community_ids = list(UserCommunity.objects.filter(user=user).values_list('community_id', flat=True))
        
        queryset = Event.objects.all().select_related('community')
        
        #Privacy filter
        privacy_filter = Q(community__privacy='public') | Q(community_id__in=user_community_ids)
        queryset = queryset.filter(privacy_filter)
        

        # Apply search filter
        search_query = self.request.query_params.get('search', None)
        if search_query:
            queryset = queryset.filter(
                Q(event_name__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(location__icontains=search_query)
            )
        
        # Apply event type filter
        event_type = self.request.query_params.get('event_type', None)
        if event_type and event_type != 'all':
            queryset = queryset.filter(event_type=event_type)
        
        # Apply date filter
        date_filter = self.request.query_params.get('date_filter', None)
        now = timezone.now()
        
        if date_filter:
            if date_filter == 'upcoming':
                queryset = queryset.filter(date__gte=now)
            elif date_filter == 'past':
                queryset = queryset.filter(date__lt=now)
            elif date_filter == 'today':
                today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = today_start + datetime.timedelta(days=1)
                queryset = queryset.filter(date__gte=today_start, date__lt=today_end)
            elif date_filter == 'this_week':
                week_start = now - datetime.timedelta(days=now.weekday())
                week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                week_end = week_start + datetime.timedelta(days=7)
                queryset = queryset.filter(date__gte=week_start, date__lt=week_end)
            elif date_filter == 'next_week':
                week_start = now - datetime.timedelta(days=now.weekday())
                week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                next_week_start = week_start + datetime.timedelta(days=7)
                next_week_end = next_week_start + datetime.timedelta(days=7)
                queryset = queryset.filter(date__gte=next_week_start, date__lt=next_week_end)
            elif date_filter == 'this_month':
                month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                next_month = month_start.month + 1
                year = month_start.year
                if next_month > 12:
                    next_month = 1
                    year += 1
                month_end = month_start.replace(year=year, month=next_month, day=1)
                queryset = queryset.filter(date__gte=month_start, date__lt=month_end)
            elif date_filter == 'custom':
                start_date = self.request.query_params.get('start_date', None)
                end_date = self.request.query_params.get('end_date', None)
                
                if start_date:
                    try:
                        queryset = queryset.filter(date__gte=start_date)
                    except (TypeError, ValueError):
                        pass
                
                if end_date:
                    try:
                        queryset = queryset.filter(date__lte=end_date)
                    except (TypeError, ValueError):
                        pass
        
        # Apply ordering
        ordering = self.request.query_params.get('ordering', 'date')
        if ordering == 'date':
            queryset = queryset.order_by('date')
        elif ordering == '-date':
            queryset = queryset.order_by('-date')
        elif ordering in ['event_name', '-event_name']:
            queryset = queryset.order_by(ordering)
        
        return queryset