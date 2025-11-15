# Patch reference: when video got ready & status='public'
from services.notifications.events_pub import publish

def on_video_ready_and_public(video_row):
    publish(
        "video.published",
        {
            "video_id": video_row["video_id"],
            "author_uid": video_row["author_uid"],
            "title": video_row.get("title","")[:160],
            "status": video_row.get("status"),
            "processing_status": video_row.get("processing_status"),
            "is_unlisted": video_row.get("status") == "unlisted",
        },
    )