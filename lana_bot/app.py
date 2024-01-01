import flask
from flask import request
from bot import ObjectDetectionBot
import boto3
from botocore.exceptions import ClientError
import json
from loguru import logger

app = flask.Flask(__name__)
table = None


def setup_routes():

    @app.route('/', methods=['GET'])
    def index():
        return 'Ok'

    @app.route(f'/{TELEGRAM_TOKEN}/', methods=['POST'])
    def webhook():
        req = request.get_json()
        # logger.info(f"Received request: {req}")  # Log the incoming request for debugging
        if 'message' in req:
            bot.handle_message(req['message'])
        elif 'callback_query' in req:
            bot.handle_callback_query(req['callback_query'])
        else:
            logger.warning("Received unknown type of update")

        return 'Ok'

    @app.route(f'/results/', methods=['GET'])
    def results():
        prediction_id = request.args.get('predictionId')
        # logger.info(f"Received Prediction ID: {prediction_id}")

        if not prediction_id:
            return 'Prediction ID not provided', 400

        try:

            response = table.get_item(Key={'prediction_id': prediction_id})
            item = response.get('Item')

            if not item:
                return 'No data found for given Prediction ID', 404

            # Extract necessary information
            chat_id = item.get('chat_id')
            yolo_results = item.get('labels')
            image_name = item.get('original_img_path')

            # logger.info(f"chat_id: {chat_id}")
            # logger.info(f"yolo_results: {yolo_results}")
            # logger.info(f"image_name: {image_name}")
            # logger.info(f"yolo_results: {yolo_results}")

            bot.continue_image_chat(chat_id, yolo_results, image_name)
            return 'Ok'

        except ClientError as lana_exception:
            return f"Error retrieving data from DynamoDB: {lana_exception}", 500

    @app.route(f'/loadTest/', methods=['POST'])
    def load_test():
        req = request.get_json()
        bot.handle_message(req['message'])
        return 'Ok'


if __name__ == "__main__":

    secret_name = "lanabot_secrets"
    region_name = "eu-west-2"

    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as error:
        raise error

    secrets = json.loads(get_secret_value_response['SecretString'])
    TELEGRAM_TOKEN = secrets['TELEGRAM_TOKEN']
    TELEGRAM_APP_URL = secrets['TELEGRAM_APP_URL']

    AWS_REGION = secrets['REGION']
    dynamodb = boto3.resource('dynamodb', region_name=region_name)
    table_name = 'lanabot-dynamoDB'
    table = dynamodb.Table(table_name)

    bot = ObjectDetectionBot(TELEGRAM_TOKEN, TELEGRAM_APP_URL)

    setup_routes()
    app.run(host='0.0.0.0', port=8443)
