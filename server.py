from flask import Flask, request, jsonify
from pushNotificationHandler import PushNotificationHelperV2
from const import *
from lokiLogger import LokiLogger
import urllib3
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
import resource
from utils import decrypt, encrypt, make_symmetric_key
import json

resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))
urllib3.disable_warnings()

app = Flask(__name__)
logger = LokiLogger().logger


# PN approach V1 (DEPRECATED) #
@app.route('/register', methods=[GET, POST])
def register():
    return jsonify({CODE: 1,
                    MSG: ENDPOINT_DEPRECATED})


@app.route('/acknowledge_message_delivery', methods=[GET, POST])
def update_last_hash():
    return jsonify({CODE: 1,
                    MSG: ENDPOINT_DEPRECATED})


# PN approach V2 #
PN_helper_v2 = PushNotificationHelperV2(logger)


def register_v2(args):
    device_token = None
    session_id = None
    if TOKEN in args:
        device_token = args[TOKEN]
    if PUBKEY in args:
        session_id = args[PUBKEY]

    if device_token and session_id:
        PN_helper_v2.register(device_token, session_id)
    else:
        logger.info("Onion routing register error")
        raise Exception(PARA_MISSING)


def unregister(args):
    device_token = None
    if TOKEN in args:
        device_token = args[TOKEN]

    if device_token:
        PN_helper_v2.unregister(device_token)
    else:
        logger.info("Onion routing unregister error")
        raise Exception(PARA_MISSING)


def subscribe_closed_group(args):
    closed_group_id = None
    session_id = None
    if PUBKEY in args:
        session_id = args[PUBKEY]
    if CLOSED_GROUP in args:
        closed_group_id = args[CLOSED_GROUP]

    if closed_group_id and session_id:
        PN_helper_v2.subscribe_closed_group(closed_group_id, session_id)
    else:
        logger.info("Onion routing subscribe closed group error")
        raise Exception(PARA_MISSING)


def unsubscribe_closed_group(args):
    closed_group_id = None
    session_id = None
    if PUBKEY in args:
        session_id = request.args[PUBKEY]
    if CLOSED_GROUP in request.args:
        closed_group_id = args[CLOSED_GROUP]

    if closed_group_id and session_id:
        PN_helper_v2.unsubscribe_closed_group(closed_group_id, session_id)
    else:
        logger.info("Onion routing unsubscribe closed group error")
        raise Exception(PARA_MISSING)


def notify(args):
    session_id = None
    data = None
    if SEND_TO in args:
        session_id = args[SEND_TO]
    if DATA in args:
        data = args[DATA]

    if session_id and data:
        PN_helper_v2.add_message_to_queue(args)
    else:
        raise Exception(PARA_MISSING)


Routing = {'register': register_v2,
           'unregister': unregister,
           'subscribe_closed_group': subscribe_closed_group,
           'unsubscribe_closed_group': unsubscribe_closed_group,
           'notify': notify}


@app.route('/loki/v1/lsrpc', methods=[POST])
def onion_request():
    ciphertext = None
    ephemeral_pubkey = None
    response = json.dumps({STATUS: 400,
                           BODY: {CODE: 0,
                                  MSG: PARA_MISSING}})

    if request.data:
        body_as_string = request.data.decode('utf-8')
        body = json.loads(body_as_string)
        if CIPHERTEXT in body:
            ciphertext = body[CIPHERTEXT]
        if EPHEMERAL in body:
            ephemeral_pubkey = body[EPHEMERAL]

    symmetric_key = make_symmetric_key(ephemeral_pubkey)

    if ciphertext and symmetric_key:
        try:
            parameters = json.loads(decrypt(ciphertext, symmetric_key).decode('utf-8'))
            args = json.loads(parameters['body'])
            if debug_mode:
                logger.info(parameters)
            func = Routing[parameters['endpoint']]
            func(args)
            response = json.dumps({STATUS: 200,
                                   BODY: {CODE: 1,
                                          MSG: SUCCESS}})
        except Exception as e:
            logger.error(e)
            response = json.dumps({STATUS: 400,
                                   BODY: {CODE: 0,
                                          MSG: str(e)}})
    return jsonify({RESULT: encrypt(response, symmetric_key)})


if __name__ == '__main__':
    PN_helper_v2.run()
    port = 3000 if debug_mode else 5000
    http_server = HTTPServer(WSGIContainer(app), no_keep_alive=True)
    http_server.listen(port)
    IOLoop.instance().start()
    PN_helper_v2.stop()
