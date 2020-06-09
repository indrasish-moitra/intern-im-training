import os
import sys
import base64
import json

from flask import Flask, request
from google.cloud import vision

app = Flask(__name__)

with open('/vault/secrets/db_creds.json') as f:
   rawsecret = f.read()
secrets=json.loads(rawsecret)

@app.route('/')
def hello_world():
    target = os.environ.get('TARGET', 'World')
    return 'Hello {}!\n'.format(target)

@app.route('/canyoukeepasecret')
def canyoukkeepasecret():
   answer = secrets['answer']
   return 'Can I keep a secret? {}!\n'.format(answer)   

@app.route('/file_drop', methods=['POST'])
def file_drop():
    """
    When a file is dropped in the storage bucket, it will trigger a pub sub message that will
    in turn post to this site.
    """
    print("/file_drop")
    try:
        envelope = request.get_json()
        print(envelope)
        pubsub_message = envelope['message']
        event_data = {}
        if isinstance(pubsub_message, dict) and 'data' in pubsub_message:
            datastr = base64.b64decode(
                pubsub_message['data']).decode('utf-8').strip()
            event_data = json.loads(datastr)
        
        vision_client = vision.ImageAnnotatorClient()
        
        bucket = event_data['bucket']
        filename = event_data['name']
        eventType = pubsub_message['attributes']['eventType']
        print(eventType)
        if eventType == 'OBJECT_FINALIZE':
            print(f"Processing file: {filename}.")
            text_detection_response = vision_client.text_detection(  # pylint: disable=no-member
                {'source': {
                    'image_uri': 'gs://{}/{}'.format(bucket, filename)
                }})
            annotations = text_detection_response.text_annotations
            if len(annotations) > 0:
                for index, annotation in enumerate(annotations):
                    text = annotation.description
                    print('{} - {}'.format(index,text))
            else:
                text = "No text found!"
                print(text)

            print('test complete')

        sys.stdout.flush()
        return("done",200)

    except Exception as identifier:
        print(identifier)
        sys.stdout.flush()
        return (str(identifier), 418)

if __name__ == "__main__":
    app.run(debug=True,host='localhost',port=int(os.environ.get('PORT', 8080)))