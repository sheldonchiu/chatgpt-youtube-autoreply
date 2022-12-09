import requests
import logging
import inspect
from googleapiclient.errors import HttpError

def handle_youtube_errors(func):
    """
    This decorator wraps a function that makes YouTube API calls,
    and catches any HttpError that is thrown. If an HttpError is caught,
    the decorator logs the error, sends a webhook post request, and re-raises the error.

    Args:
        func (function): The function to wrap.
    
    Returns:
        function: The wrapper function.
    """
    def wrapper(*args, **kwargs):
        # Get the webhook_url parameter from the function call
        webhook_url = kwargs.get("email_webhook_url", None)
        # Get the basic auth parameter from the function call
        auth = kwargs.get("webhook_auth", None)

        try:
            # Call the original function
            return func(*args, **kwargs)
        except HttpError as e:
            if e.status_code == 403:
                # TODO: handle 403, either forbidden or rate limit exceeded
                pass
            # Send a webhook post request with the error message
            if webhook_url and auth:
                requests.post(webhook_url, json={'Location': 'youtube api', 'Error message': str(e)}, auth=auth)

            # Re-raise the error
            raise
    return wrapper


@handle_youtube_errors
def youtube_execute(request, **kwargs):
    return request.execute()

@handle_youtube_errors
def reply_to_comment(youtube, comment_id, response_text, **kwargs):
    """
    This function replies to a comment on a YouTube video.
    It uses the YouTube API client to reply to the specified comment with the specified text.

    Args:
        youtube (googleapiclient.discovery.Resource): The YouTube API client.
        comment_id (str): The ID of the comment to reply to.
        response_text (str): The text of the reply.
    """
    youtube.comments().insert(
        part="snippet",
        body={
            "snippet": {
                "parentId": comment_id,
                "textOriginal": response_text
            }
        }
    ).execute()

@handle_youtube_errors
def updateVideoDescription(youtube, video_id, title, categoryId, description, **kwargs):
    """
    Update the description of a YouTube video.

    Args:
        youtube (googleapiclient.discovery.Resource): The YouTube API client.
        video_id (str): The ID of the video to update.
        title (str): The new title of the video.
        categoryId (str): The new category ID of the video.
        description (str): The new description of the video.
    """
    youtube.videos().update(
        part="snippet",
        body={
            "id": video_id,
            "snippet": {
                'title': title,
                "categoryId": categoryId,
                "description": description
            }
        }
    ).execute()
    
