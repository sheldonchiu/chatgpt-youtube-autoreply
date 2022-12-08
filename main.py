#%%
import os


import datetime
import google.oauth2.credentials
import googleapiclient.discovery
from google_auth_oauthlib.flow import InstalledAppFlow
import googleapiclient.errors
import pickle
import time
import logging
from collections import OrderedDict
from pychatgpt import OpenAI
from pychatgpt import Chat
from dotenv import load_dotenv

#%%
# Set up the logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

load_dotenv('.env', override=False)
chatgpt_email = os.environ["CHATGPT_EMAIL"]
chatgpt_password = os.environ["CHATGPT_PASSWORD"]
chat_keyword = os.environ["CHAT_KEYWORD"]
video_id = os.environ["VIDEO_ID"]
proxy = os.environ["PROXY_ADDRESS"]
google_api_key = os.environ["GOOGLE_API_KEY"]
interval = os.environ["INTERVAL"]
root_folder = os.environ["ROOT_FOLDER"]
description_text = os.environ["DESCRIPTION_TEXT"]
like_power = int(os.environ["LIKE_POWER"])
subscribe_power = int(os.environ["SUBSCRIBE_POWER"])

# Fallback to /app if value from env is incorrect
if not os.path.isdir(root_folder):
    root_folder = '/app'
os.chdir(root_folder)

try:
    interval = int(interval)
except ValueError:
    interval = 300
#%%
def updateVideoDescription(youtube, video_id, title, categoryId, description):
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
#%%
def process_comments(youtube, replied_to, video_id):
    # Set up the parameters for the API call
    params = {
        "part": "snippet",
        "videoId": video_id,
        "textFormat": "plainText",
        'maxResults': 100,
        'order': 'time',
        'searchTerms': chat_keyword
    }
        
    request = youtube.commentThreads().list(**params)

    # Loop through the pages of results
    while request:
        # Execute the API call
        response = request.execute()
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
                video_response = youtube.videos().list(**video_params).execute()
                title = video_response["items"][0]["snippet"]["title"]
                category_id = video_response["items"][0]["snippet"]["categoryId"]
                like_count = video_response["items"][0]["statistics"]["likeCount"]
                description = video_response["items"][0]["snippet"]["description"]

                channel_params = {
                    "part": "snippet,statistics",
                    "id": video_response['items'][0]["snippet"]["channelId"]
                }

                # Make the API call to get the channel information
                channel_response = youtube.channels().list(**channel_params).execute()
                # Get the number of subscribers of the channel
                subscriber_count = channel_response["items"][0]["statistics"]["subscriberCount"]
                
                if len(replied_to) < int(like_count) * like_power + int(subscriber_count) * subscribe_power:
                    # If the text is already present in the description, remove it
                    if description_text in description:
                        new_description = description.replace("!!! Power Charged, Will reply at FULL SPEED !!!", "")
                        # Update the video with the new description
                        updateVideoDescription(youtube, video_id, title, category_id, new_description)
                    chat = Chat(email=chatgpt_email, password=chatgpt_password, proxies=proxy) 
                    response = chat.ask(comment_text.replace(chat_keyword, ""))
                    
                    # Reply to the comment
                    youtube.comments().insert(
                        part="snippet",
                        body=dict(
                            snippet=dict(
                                parentId=comment["id"],
                                textOriginal=response
                            )
                        )
                    ).execute()
                    logging.info(f"Replied to {comment['id']} with: {response}")
                    replied_to.add(comment["id"])
                elif description_text not in description:
                    new_description = f"{description_text}\n" + description
                    # Update the video with the new description
                    updateVideoDescription(youtube, video_id, title, category_id, new_description)
            else:
                # If the comment has already been replied to, end the loop
                end = True
                break
        if end:
            break
        # Check if there are more pages of results
        if "nextPageToken" in response:
            # Set up the parameters for the next page of results
            request = youtube.commentThreads().list(
                **params,
                pageToken=response["nextPageToken"]
            )
        else:
            # If there are no more pages of results, exit the loop
            request = None

#%%
def auto_reply(video_id, credentials):
    # Set up the credentials for the YouTube API
    API_SERVICE_NAME = "youtube"
    API_VERSION = "v3"

    # Build the YouTube API client
    youtube = googleapiclient.discovery.build(
        API_SERVICE_NAME, API_VERSION, credentials=credentials)

    # Try to read the replied-to comments from a file
    try:
        with open("replied_to.pickle", "rb") as f:
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
            with open("replied_to.pickle", "wb") as f:
                pickle.dump(replied_to, f)
        except:
            # If an error occurs, log it and continue
            logging.exception("Error while processing comments")

        # Sleep for a minute between checking for new comments
        logging.info(f"Start to sleep for {interval} seconds")
        time.sleep(interval)
#%%

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
        
    
# get_comments_on_video(video_id)
auto_reply(video_id,  creds)
# %%
