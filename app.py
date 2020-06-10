import os
import sys
import base64
import json
import sqlalchemy

from flask import Flask, request
from google.cloud import vision

app = Flask(__name__)

with open('/vault/secrets/db_creds.json') as f:
   rawsecret = f.read()
secrets=json.loads(rawsecret)


db_user = secrets["db_user"]
db_pass = secrets["db_pass"]
db_name = secrets["db_name"]
#cloud_sql_connection_name = os.environ.get("CLOUD_SQL_CONNECTION_NAME")

# [START cloud_sql_postgres_sqlalchemy_create]
# The SQLAlchemy engine will help manage interactions, including automatically
# managing a pool of connections to your database
# sql proxy
connect_string = f"postgres+pg8000://{db_user}:{db_pass}@127.0.0.1:5432/{db_name}"
db = sqlalchemy.create_engine(
    connect_string,
    # ... Specify additional properties here.
    # [START_EXCLUDE]

    # [START cloud_sql_postgres_sqlalchemy_limit]
    # Pool size is the maximum number of permanent connections to keep.
    pool_size=5,
    # Temporarily exceeds the set pool_size if no connections are available.
    max_overflow=2,
    # The total number of concurrent connections for your application will be
    # a total of pool_size and max_overflow.
    # [END cloud_sql_postgres_sqlalchemy_limit]

    # [START cloud_sql_postgres_sqlalchemy_backoff]
    # SQLAlchemy automatically uses delays between failed connection attempts,
    # but provides no arguments for configuration.
    # [END cloud_sql_postgres_sqlalchemy_backoff]

    # [START cloud_sql_postgres_sqlalchemy_timeout]
    # 'pool_timeout' is the maximum number of seconds to wait when retrieving a
    # new connection from the pool. After the specified amount of time, an
    # exception will be thrown.
    pool_timeout=30,  # 30 seconds
    # [END cloud_sql_postgres_sqlalchemy_timeout]

    # [START cloud_sql_postgres_sqlalchemy_lifetime]
    # 'pool_recycle' is the maximum number of seconds a connection can persist.
    # Connections that live longer than the specified amount of time will be
    # reestablished
    pool_recycle=1800,  # 30 minutes
    # [END cloud_sql_postgres_sqlalchemy_lifetime]

    # [END_EXCLUDE]
)
# [END cloud_sql_postgres_sqlalchemy_create]

metadata = sqlalchemy.MetaData()
image_text = sqlalchemy.Table('image_text',metadata,
    sqlalchemy.Column("record_id",sqlalchemy.String, nullable = False),
    sqlalchemy.Column("image_id",sqlalchemy.String, nullable = False),
    sqlalchemy.Column("description_id",sqlalchemy.Integer, nullable = False),
    sqlalchemy.Column("description",sqlalchemy.String, nullable = False),
    sqlalchemy.Column("boundingpoly",sqlalchemy.String, nullable = False),
)
metadata.create_all(db)

def callsql(sql_statement):
    """
    Test function to confirm database connection
    """
    print("connecting")
    with db.connect() as conn:
        stmt = sqlalchemy.text(sql_statement)
        print(stmt)
        tab_result = conn.execute(stmt).fetchall()

    print(tab_result)
    sys.stdout.flush()
    result_str = json.dumps([list(r) for r in tab_result])
    print(result_str)
    return (result_str) 

@app.route('/category')
def category():
    return(callsql("""SELECT * FROM category;"""), 200)


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
            insertQueue = []
            for index, annotation in enumerate(annotations):
                text = annotation.description
                print('{} - {}'.format(index,text))
                image_id = filename
                record_id= filename.strip('.')[0]
                tobeinserted = {
                "record_id": record_id,
                "image_id": image_id,
                "description_id": index,
                "description":text,
                "boundingpoly":str(annotation.bounding_poly)
                }
                insertQueue.append(tobeinserted)
            with db.connect() as conn:
                conn.execute(image_text.insert(),insertQueue)
        else:
            text = "No text found!"
            print(text)

        print('test complete')

    sys.stdout.flush()
    return("done",200)

if __name__ == "__main__":
    app.run(debug=True,host='localhost',port=int(os.environ.get('PORT', 8080)))

