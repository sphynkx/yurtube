# Patch reference only: afta successful create
from services.notifications.events_pub import publish

publish(
    "comment.created",
    {
        "video_id": video_id,
        "comment_id": new_comment_id,
        "actor_uid": current_user_uid,
        "parent_comment_author_uid": parent_author_uid,
        "text_preview": text[:160],
    },
)