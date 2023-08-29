import os
import logging
from deepgram import Deepgram
import json
from os.path import join, dirname
from dotenv import load_dotenv
dotenv_path = join(dirname(__file__), ".env")
load_dotenv(dotenv_path)
from retry import retry

DEEPGRAM_API_KEY = os.environ.get('DEEPGRAM_API_SECRET')

# Set up my logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@retry(Exception, tries=5, delay=1)
def asr_deepgram(file_path):
    # Initialize the Deepgram SDK
    deepgram = Deepgram(DEEPGRAM_API_KEY)
    # Open the audio file using the provided file_path argument
    with open(file_path, 'rb') as audio:
        source = {'buffer': audio, 'mimetype': 'video/mp4'}

        # Logging the transaction to detect errors
        logger.info("Guess what? It's starting")

        try:
            response = deepgram.transcription.sync_prerecorded(source, {'smart_format': True, 'summarize':  True})
            # Print the response to understand the structure
            logger.info("API Response:")
            logger.info(json.dumps(response, indent=4))

            # I'm naming the resulting transcription and summary file according to the original file
            original_filename = os.path.splitext(os.path.basename(file_path))[0]
            json_filename = f"deepgram_{original_filename}_transcription.json"
            transcript_filename = f"deepgram_{original_filename}_transcript.txt"
            summary_filename = f"deepgram_{original_filename}_summary.txt"
            formatted_filename = f"deepgram_{original_filename}_paragraph.txt"

            # Extract the transcript from the response
            transcript = response["results"]["channels"][0]["alternatives"][0]["transcript"]

            # Save the transcription response to the JSON file
            with open(json_filename, 'w') as json_file:
                json.dump(response, json_file, indent=4)

            # Save the transcript to the text file
            with open(transcript_filename, 'w') as transcript_file:
                transcript_file.write(transcript)

            # Extract the summaries from the response and concatenate them
            summaries_list = response['results']['channels'][0]['alternatives'][0]['summaries']
            with open(summary_filename, 'w') as summary_file:
                for summary_data in summaries_list:
                    summary = summary_data['summary']
                    summary_file.write(f"{summary}\n")
            # Extract the paragraph>>sentences from the response and concatentate them into one file
            paragraphs = response['results']['channels'][0]['alternatives'][0]['paragraphs']['transcript']
            with open (formatted_filename, 'w') as formatted_file:
                formatted_file.write(paragraphs)

        except Exception as e:
            # Log an error message if the transcription fails
            logger.error("Transcription failed! Error: %s", e)

if __name__ == "__main__":
    # Pass the filename (PATH_TO_FILE) as an argument to the function
    asr_deepgram('benchmark_test_3.mp4')
