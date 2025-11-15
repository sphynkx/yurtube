# Patch reference: afta successful like (vote == 1)
from services.notifications.events_pub import publish

if vote_value == 1:
    publish(
        "comment.voted",
        {
            "video_id": video_id,
            "comment_id": comment_id,
            "actor_uid": current_user_uid,
            "comment_author_uid": comment_author_uid,
            "vote": 1,
        },
    )