#%%
import os
import sys
import googleapiclient.discovery
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError
import pickle
import time
import logging
from pychatgpt import Chat, Options as chatOptions
from dotenv import load_dotenv
from youtube_utils import *

#%%
# Set up the logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Load environment variables from the .env file
load_dotenv('.env', override=False)

root_folder = os.environ.get("ROOT_FOLDER")
if not os.path.isdir(root_folder):
    logging.error("Invalid root folder")
    sys.exit(1)
    
os.chdir(root_folder)

# Extract environment variables
chatgpt_email = os.environ.get("CHATGPT_EMAIL")
chatgpt_password = os.environ.get("CHATGPT_PASSWORD")
if chatgpt_email is None or chatgpt_password is None:
    logging.error("CHATGPT_EMAIL and CHATGPT_PASSWORD environment variables not set")
    sys.exit(1)

video_id = os.environ.get("VIDEO_ID")
if video_id is None:
    logging.error("VIDEO_ID environment variable not set")
    sys.exit(1)
    
google_api_key = os.environ.get("GOOGLE_API_KEY")
if google_api_key is None:
    logging.error("GOOGLE_API_KEY environment variable not set")
    sys.exit(1)

chat_keyword = os.environ.get("CHAT_KEYWORD", "")  
proxy = os.environ.get("PROXY_ADDRESS")   
interval = int(os.environ.get("INTERVAL"))
description_text = os.environ.get("DESCRIPTION_TEXT")
like_power = int(os.environ.get("LIKE_POWER"))
subscribe_power = int(os.environ.get("SUBSCRIBE_POWER"))

notify_on_youtube_error=bool(os.environ["NOTIFY_ON_YOUTUBE_ERROR"])
notify_on_openai_error=bool(os.environ["NOTIFY_ON_OPENAI_ERROR"])

if notify_on_youtube_error or notify_on_openai_error:
    email_webhook_url = os.environ["EMAIL_WEBHOOK_URL"]
    webhook_basic_auth_username = os.environ["WEBHOOK_BASIC_AUTH_USERNAME"]
    webhook_basic_auth_password = os.environ["WEBHOOK_BASIC_AUTH_PASSWORD"]
    webhook_auth = (webhook_basic_auth_username, webhook_basic_auth_password)
    webhook_kwargs = { 'email_webhook_url': email_webhook_url, 
                    'webhook_auth': webhook_auth }

else:
    webhook_kwargs = {}
    
chat_options = chatOptions()
# Track conversation
chat_options.track = False 
chat_options.proxies = proxy
    
def process_comments(youtube, replied_to, video_id):
    """
    This function automatically replies to comments on a YouTube video that contain a specified keyword.
    It uses the YouTube API to retrieve comments for the specified video,
    and then uses the OpenAI chatbot to generate responses for each comment.
    Finally, it replies to the comment with the chatbot's response.

    Args:
        youtube (googleapiclient.discovery.Resource): The YouTube API client.
        replied_to (set): A set of comment IDs that have already been replied to.
        chat_keyword (str): The keyword to search for in the comments.
        video_id (str): The ID of the video to process comments for.
    
    Returns:
        None
    
    This function uses the YouTube API to retrieve comments for the specified video. It then loops through
    the comments and filters out any un-replied comments that contains the specified keyword. For each remaining
    comment, the function uses the OpenAI chatbot to generate a response. Finally, it replies to the comment
    with the chatbot's response and adds the comment ID to the replied_to set to keep track of which
    comments have already been replied to.
    """
    # Set up the parameters for the API call   
    params = {
        "part": "snippet",
        "videoId": video_id,
        "textFormat": "plainText",
        'maxResults': 100,
        'order': 'time',
    }

    # Check if the chat_keyword variable is defined and not empty
    if not chat_keyword or not chat_keyword.strip():
        # Set the searchTerms parameter to None to disable keyword filtering
        params['searchTerms'] = None
    else:
        # Set the searchTerms parameter to the value of the chat_keyword variable
        params['searchTerms'] = chat_keyword
        
    request = youtube.commentThreads().list(**params)

    # Loop through the pages of results
    while request:
        # Execute the API call
        response = youtube_execute(request, **webhook_kwargs)
        end = False
        # Loop through the comments in the current page of results
        for item in response["items"]:
            comment = item["snippet"]["topLevelComment"]
            # Check if the comment has not been replied to yet
            if comment["id"] not in replied_to:
                # Extract the author's name and the comment text
                author_name = comment["snippet"]["authorDisplayName"]
                comment_text = comment["snippet"]["textDisplay"]
                logging.info(f"Comment from {author_name}: {comment_text}")

                video_params = {
                    "part": "snippet,statistics",
                    "id": video_id
                }
                # Make the API call to get the video information
                video_response = youtube_execute(youtube.videos().list(**video_params), **webhook_kwargs)
                title = video_response["items"][0]["snippet"]["title"]
                category_id = video_response["items"][0]["snippet"]["categoryId"]
                like_count = video_response["items"][0]["statistics"]["likeCount"]
                description = video_response["items"][0]["snippet"]["description"]

                channel_params = {
                    "part": "snippet,statistics",
                    "id": video_response['items'][0]["snippet"]["channelId"]
                }

                # Make the API call to get the channel information
                channel_response = youtube_execute(youtube.channels().list(**channel_params), **webhook_kwargs)
                # Get the number of subscribers of the channel
                subscriber_count = channel_response["items"][0]["statistics"]["subscriberCount"]
                
                if len(replied_to) < int(like_count) * like_power + int(subscriber_count) * subscribe_power:
                    # If the text is already present in the description, remove it
                    if description_text in description:
                        new_description = description.replace("!!! Power Charged, Will reply at FULL SPEED !!!", "")
                        # Update the video with the new description
                        updateVideoDescription(youtube, video_id, title, category_id, new_description, **webhook_kwargs)
                    
                    # Use the OpenAI chatbot to generate a response to the comment
                    try:
                        chat = Chat(email=chatgpt_email, password=chatgpt_password, options=chat_options) 
                        response = chat.ask(comment_text.replace(chat_keyword, ""))
                    except Exception as e:
                        if notify_on_openai_error:
                            requests.post(email_webhook_url, json={'Location': 'ChatGPT API', 'Error message': str(e)}, auth=webhook_auth)
                        raise
                    
                    # Reply to the comment
                    reply_to_comment(youtube, comment['id'], response, **webhook_kwargs)
                    logging.info(f"Replied to {comment['id']} with: {response}")
                    replied_to.add(comment["id"])
                elif description_text not in description:
                    new_description = f"{description_text}\n" + description
                    # Update the video with the new description
                    updateVideoDescription(youtube, video_id, title, category_id, new_description, **webhook_kwargs)
            else:
                # If the comment has already been replied to, end the loop
                end = True
                break
        if end:
            break
        # Check if there are more pages of results
        if "nextPageToken" in response:
            # Set up the parameters for the next page of results
            request = youtube.commentThreads().list(**params,pageToken=response["nextPageToken"])
        else:
            # If there are no more pages of results, exit the loop
            request = None

def auto_reply(video_id, credentials):
    """
    A wrapper to run the 'process_comments' function indefinitely

    Args:
        video_id (str): The ID of the video to process comments for.
        credentials (google.oauth2.credentials.Credentials): The credentials for the YouTube API.

    Returns:
        None
    """
    # Set up the credentials for the YouTube API
    API_SERVICE_NAME = "youtube"
    API_VERSION = "v3"

    # Build the YouTube API client
    youtube = googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials)

    # Try to read the replied-to comments from a file
    try:
        with open(f"replied_to_{video_id}.pickle", "rb") as f:
            replied_to = pickle.load(f)
    except FileNotFoundError:
        # If the file does not exist, start with an empty set
        replied_to = set()

    # Keep watching for new comments and reply to them
    while True:

        # Process any new comments that have been posted since the last check
        try:
            process_comments(youtube, replied_to, video_id)
            # Save the replied-to comments to a file
            with open(f"replied_to_{video_id}.pickle", "wb") as f:
                pickle.dump(replied_to, f)
        except:
            # If an error occurs, log it and continue
            logging.exception("Error while processing comments")

        # Sleep for a minute between checking for new comments
        logging.info(f"Start to sleep for {interval} seconds")
        time.sleep(interval)

flow = InstalledAppFlow.from_client_secrets_file(
    google_api_key,
    scopes=['https://www.googleapis.com/auth/youtube.force-ssl'])

try:
    # Try to load the credentials from the pickle file
    with open("credentials.pickle", "rb") as f:
        creds = pickle.load(f)
except FileNotFoundError:
    # If the pickle file does not exist, run the OAuth 2.0 flow
    creds = flow.run_console()

    # Save the credentials to the pickle file
    with open("credentials.pickle", "wb") as f:
        pickle.dump(creds, f)
        
if __name__ == "__main__":    
    # get_comments_on_video(video_id)
    auto_reply(video_id,  creds)
