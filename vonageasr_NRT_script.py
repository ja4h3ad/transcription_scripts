import os
import logging
import requests
from os.path import join, dirname
from dotenv import load_dotenv
import json
dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)
from retry import retry
import base64
import time


VONAGE_API_KEY = os.environ.get('VONAGE_API_KEY')
VONAGE_API_SECRET = os.environ.get('VONAGE_API_SECRET')
AUTH_URL_ENDPOINT = os.environ.get('AUTH_URL_ENDPOINT')
PRE_SIGNED_URL_ENDPOINT = os.environ.get('PSU_ENDPOINT')
TRANSCRIPTION_ENDPOINT = os.environ.get('ANALYZE_ENDPOINT')

# Set up my logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_transcription_result(auth_token, job_id, result_url, max_retries=10, initial_wait_time=30):
    """1.  Since the transcription job requires some time, I am polling the server for status
           2.  THis is an exponential backoff.
           3.  Note that the job_id and the result URL are generated in the asr_vonage() function"""
    for attempt in range(max_retries):
        try:
            headers = {'Authorization': f"Bearer {auth_token}"}
            result_response = requests.get(result_url, headers=headers)
            if result_response.status_code != 200:
                logger.error(f"Unexpected status code on attempt {attempt + 1}: {result_response.status_code}. Response text: {result_response.text}")
                continue

            result_data = result_response.json()
            logger.info(f"Received response (Attempt {attempt + 1}/{max_retries}): {result_data}")

            if result_data.get("status") == "success":
                return result_data
            else:
                logger.info(f"Transcription status is {result_data.get('status')}. Retrying in {initial_wait_time} seconds.")
                time.sleep(initial_wait_time)
                initial_wait_time *= 2

        except Exception as e:
            logger.error(f"Error on attempt {attempt + 1}: {e}", exc_info=True)

    logger.error("Max retries reached. Failed to get transcription result.")
    return None



def fetch_transcription_content(result_url):

    try:
        response = requests.get(result_url)
        response.raise_for_status()  # This will raise an HTTPError if the HTTP request returned an unsuccessful status code
        transcription_content = response.json()
        return transcription_content

    except requests.exceptions.HTTPError:
        # Catch HTTP errors (like 404, 503, etc.)
        logger.error(f"HTTP error occurred. Status code: {response.status_code}, Response: {response.text}")
        return None
    except requests.exceptions.RequestException as e:
        # This will catch other types of errors like connection errors
        logger.error("Error fetching the transcription content:", exc_info=True)
        return None
    except json.JSONDecodeError:
        # This will catch errors if the response isn't a valid JSON
        logger.error(f"Error decoding JSON. Response: {response.text}")
        return None



@retry(Exception, tries=5, delay=1)
def asr_vonage(file_name):
    '''This is a function to call the Vonage ASR endpoint sequentially'''
    # I'm naming the resulting transcription and summary file according to the original file
    original_filename = os.path.splitext(os.path.basename(file_name))[0]
    json_filename = f"vonage_{original_filename}_transcription.json"
    transcript_filename = f"vonage_{original_filename}_transcript.txt"
    summary_filename = f"vonage_{original_filename}_summary.txt"
    formatted_filename = f"vonage_{original_filename}_paragraph.txt"
    sentiment_filename = f"vonage_{original_filename}_sentiment.txt"


    # Data to be sent in the request body
    data = 'grant_type=client_credentials'
    # Generate the auth token
    api_key_secret = f"{VONAGE_API_KEY}:{VONAGE_API_SECRET}"
    # encode the API key and secret in base64
    auth_header_value = base64.b64encode(api_key_secret.encode()).decode()
    auth_header = f"Basic {auth_header_value}"

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'{auth_header}',
        'Cookie': 'XSRF-TOKEN=a38df28f-3b0a-465b-8dc6-98c287d10949'
    }

    # Step 1:  POST request to the API to generate the auth token
    response = requests.post(f"{AUTH_URL_ENDPOINT}", data=data, headers=headers)
    # Log the API response content (the actual JSON data returned by the API)
    logger.info("API Response Content:")
    logger.info(response.json())  # Log the JSON content directly

    # Verify if the request was successful (status code 200)
    if response.status_code == 200:
        # Parse the response JSON and extract the auth token
        auth_token = response.json().get("access_token")
        logger.info("auth_token acquired successfully.")
    else:
        # For failed requests, print the error message and return None
        logger.error("Error acquiring access token:", exc_info=True)
        # print(f"Failed to generate auth token. Status code: {response.status_code}, Error: {response.text}")
        return None

    # Step 2: Obtain the pre-signed URL
    pre_signed_url_endpoint = f"{PRE_SIGNED_URL_ENDPOINT}/url?file_name={file_name}"
    headers = {
        "Authorization": f"Bearer {auth_token}"
    }

    try:
        response = requests.get(pre_signed_url_endpoint, headers=headers)
        response.raise_for_status()
        pre_signed_url = response.json().get("url")
        logger.info("pre_signed URL obtained successfully.")
        logger.info(f"Pre-signed URL: {pre_signed_url}")

    except requests.exceptions.RequestException as e:
        logger.error("Error getting pre-signed URL:", exc_info=True)
        logger.error("Response content:")
        logger.error(response.content)
        return

    # step 3 upload file and receive cognitive services data
    try:
        with open(file_name, "rb") as file:
            # use time to identify response times for the transcription and other cognitive services.
            data = file.read()
            st = time.time()
            response = requests.put(pre_signed_url, data=data)
            upload_time = time.time() - st
            response.raise_for_status()
            logger.info("File uploaded successfully!")
            logger.info(f"Upload time was {upload_time}")


    except requests.exceptions.RequestException as e:
        logger.error("Error uploading the file or processing the API response:", exc_info=True)

    # step 4 request cognitive services job
    try:
        payload = json.dumps({
            "account_id": "123456",
            "user_id": "tim_dentry_test",
            "language": "en-US",
            "insights": [
                {
                    "type": "transcription",
                    "config": {
                        "provider": "vonage"
                    }
                },
                {
                    "type": "sentiment",
                    "config": {
                        "provider": "vonage"
                    },
                },
                {
                    "type": "summary",
                    "config": {
                        "provider": "vonage"
                    }
                },
                {
                    "type": "topics",
                    "config": {
                        "provider": "vonage"
                    }
                }
            ],
            "media": {
                "meta_data": {},
                "url": pre_signed_url  # pre-signed url variable
            }
        })
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {auth_token}"  # auth_token variable
        }

        transcription_response = requests.post(TRANSCRIPTION_ENDPOINT, headers=headers, data=payload)
        transcription_response_data = transcription_response.json()
        # logger.info(transcription_response_data)
        job_id = transcription_response_data.get("job_id")
        logger.info(job_id)
        if job_id:
            result_url = transcription_response_data.get("result_url")
            logger.info(result_url)

        logger.info("About to call get_transcription_result function...")
        transcription_result = get_transcription_result(auth_token, job_id, result_url)

        if transcription_result:
            result_json_filename = f"vonage_{original_filename}_job_result.json"
            with open(result_json_filename, 'w') as json_file:
                json.dump(transcription_result, json_file, indent=4)
                logger.info(f"Transcription result saved to {result_json_filename}.")

            # Extract the embedded cognitive service nested result_url from the transcription_result
            urls_by_type = {item["type"]: item["result_url"] for item in transcription_result["insights"]}
            for insight_type, url in urls_by_type.items():
                content = fetch_transcription_content(url)

                if content:
                    # Use the insight type in the filename for clear identification
                    filename = f"vonage_{original_filename}_{insight_type}.json"

                    # If this is the summary content, then just get the summary key value
                    if insight_type == "summary":
                        summary_text = content.get("summary", {}).get("text")
                        if summary_text:
                            with open(summary_filename, 'w') as file:
                                file.write(summary_text)
                                logger.info(f"Summary saved to {summary_filename}.")
                        else:
                            logger.error("Failed to extract summary text from the content.")
                    else:
                        with open(filename, 'w') as file:
                            json.dump(content, file, indent=4)
                            logger.info(f"{insight_type.capitalize()} content saved to {filename}.")
                else:
                    logger.error(f"Failed to fetch {insight_type} content.")


    except Exception as e:
        #logger.error("Non-JSON response received from transcription service.")
        logger.error(f"Error during cognitive services job request: {e}")
        return

if __name__ == "__main__":
    # Pass the filename (PATH_TO_FILE) as an argument to the function
    asr_vonage('benchmark_test_3_converted.wav')













