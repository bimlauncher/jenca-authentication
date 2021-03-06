"""
An authentication service for use in a Jenca Cloud.
"""

import os

from flask import Flask, jsonify, request, json
from flask.ext.bcrypt import Bcrypt
from flask.ext.login import (
    current_user,
    LoginManager,
    login_required,
    login_user,
    logout_user,
    make_secure_token,
    UserMixin,
)
from flask_jsonschema import JsonSchema, ValidationError
from flask_negotiate import consumes

import requests
from requests import codes

# This is necessary because urljoin moved between Python 2 and Python 3
from future.standard_library import install_aliases
install_aliases()

# Ignore this line with linters because it necessarily comes after
# `install_aliases`.
from urllib.parse import urljoin  # noqa


class User(UserMixin):
    """
    A user has an email address and a password hash.
    """

    def __init__(self, email, password_hash):
        self.email = email
        self.password_hash = password_hash

    def get_auth_token(self):
        """
        See https://flask-login.readthedocs.org/en/latest/#alternative-tokens

        :return: A secure token unique to this ``User`` with the current
            ``password_hash``.
        :rtype: string
        """
        return make_secure_token(self.email, self.password_hash)

    def get_id(self):
        """
        See https://flask-login.readthedocs.org/en/latest/#your-user-class

        :return: the email address to satify Flask-Login's requirements. This
            is used in conjunction with ``load_user`` for session management.
        :rtype: string
        """
        return self.email


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret')
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)

# Inputs can be validated using JSON schema.
# Schemas are in app.config['JSONSCHEMA_DIR'].
# See https://github.com/mattupstate/flask-jsonschema for details.
app.config['JSONSCHEMA_DIR'] = os.path.join(app.root_path, 'schemas')
jsonschema = JsonSchema(app)

STORAGE_HOST = os.environ.get('STORAGE_HOST', 'storage')
if STORAGE_HOST.find('env:') == 0:
    STORAGE_HOST = os.environ.get(STORAGE_HOST.split(':')[1])

STORAGE_URL = os.environ.get('STORAGE_URL', 'http://' + STORAGE_HOST + ':5001')


@login_manager.user_loader
def load_user_from_id(user_id):
    """
    Flask-Login ``user_loader`` callback.

    The ``user_id`` was stored in the session environment by Flask-Login.
    user_loader stores the returned ``User`` object in ``current_user`` during
    every flask request.

    See https://flask-login.readthedocs.org/en/latest/#flask.ext.login.LoginManager.user_loader.  # noqa

    :param user_id: The ID of the user Flask is trying to load.
    :type user_id: string
    :return: The user which has the email address ``user_id`` or ``None`` if
        there is no such user.
    :rtype: ``User`` or ``None``.
    """
    url = urljoin(STORAGE_URL, 'users/{email}').format(email=user_id)
    response = requests.get(url, headers={'Content-Type': 'application/json'})

    if response.status_code == codes.OK:
        details = json.loads(response.text)
        return User(
            email=details['email'],
            password_hash=details['password_hash'],
        )


@login_manager.token_loader
def load_user_from_token(auth_token):
    """
    Flask-Login token-loader callback.

    See https://flask-login.readthedocs.org/en/latest/#flask.ext.login.LoginManager.token_loader  # noqa

    :param auth_token: The authentication token of the user Flask is trying to
        load.
    :type user_id: string
    :return: The user which has the given authentication token or ``None`` if
        there is no such user.
    :rtype: ``User`` or ``None``.
    """
    response = requests.get(
        urljoin(STORAGE_URL, '/users'),
        headers={'Content-Type': 'application/json'},
    )

    for details in json.loads(response.text):
        user = User(
            email=details['email'],
            password_hash=details['password_hash'],
        )
        if user.get_auth_token() == auth_token:
            return user


@app.errorhandler(ValidationError)
def on_validation_error(error):
    """
    :resjson string title: An explanation that there was a validation error.
    :resjson string message: The precise validation error.
    :status 400:
    """
    return jsonify(
        title='There was an error validating the given arguments.',
        # By default on Python 2 errors will look like:
        # "u'password' is a required property".
        # This removes all "u'"s, and so could be dangerous.
        detail=error.message.replace("u'", "'"),
    ), codes.BAD_REQUEST


@app.route('/login', methods=['POST'])
@consumes('application/json')
@jsonschema.validate('user', 'get')
def login():
    """
    Log in a given user.

    :param email: An email address to log in as.
    :type email: string
    :param password: A password associated with the given ``email`` address.
    :type password: string
    :reqheader Content-Type: application/json
    :resheader Content-Type: application/json
    :resheader Set-Cookie: A ``remember_token``.
    :resjson string email: The email address which has been logged in.
    :resjson string password: The password of the user which has been logged
        in.
    :status 200: A user with the given ``email`` has been logged in.
    :status 404: No user can be found with the given ``email``.
    :status 401: The given ``password`` is incorrect.
    """
    email = request.json['email']
    password = request.json['password']

    user = load_user_from_id(user_id=email)
    if user is None:
        return jsonify(
            title='The requested user does not exist.',
            detail='No user exists with the email "{email}"'.format(
                email=email),
        ), codes.NOT_FOUND

    if not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify(
            title='An incorrect password was provided.',
            detail='The password for the user "{email}" does not match the '
                   'password provided.'.format(email=email),
        ), codes.UNAUTHORIZED

    login_user(user, remember=True)

    return jsonify(email=email, password=password)


@app.route('/logout', methods=['POST'])
@consumes('application/json')
@login_required
def logout():
    """
    Log the current user out.

    :resheader Content-Type: application/json
    :status 200: The current user has been logged out.
    """
    logout_user()
    return jsonify({}), codes.OK


@app.route('/users/<email>', methods=['DELETE'])
@consumes('application/json')
def specific_user_route(email):
    """
    Delete a particular user.

    :reqheader Content-Type: application/json
    :resheader Content-Type: application/json
    :resjson string email: The email address of the deleted user.
    :status 200: The user has been deleted.
    :status 404: There is no user with the given ``email``.
    """
    user = load_user_from_id(email)

    if user is None:
        return jsonify(
            title='The requested user does not exist.',
            detail='No user exists with the email "{email}"'.format(
                email=email),
        ), codes.NOT_FOUND

    requests.delete(
        urljoin(STORAGE_URL, '/users/{email}'.format(email=email)),
        headers={'Content-Type': 'application/json'},
    )

    return_data = jsonify(email=user.email)
    return return_data, codes.OK


@app.route('/signup', methods=['POST'])
@consumes('application/json')
@jsonschema.validate('user', 'create')
def signup():
    """
    Sign up a new user.

    :param email: The email address of the new user.
    :type email: string
    :param password: A password to associate with the given ``email`` address.
    :type password: string
    :reqheader Content-Type: application/json
    :resheader Content-Type: application/json
    :resjson string email: The email address of the new user.
    :resjson string password: The password of the new user.
    :status 200: A user with the given ``email`` and ``password`` has been
        created.
    :status 409: There already exists a user with the given ``email``.
    """
    email = request.json['email']
    password = request.json['password']

    if load_user_from_id(email) is not None:
        return jsonify(
            title='There is already a user with the given email address.',
            detail='A user already exists with the email "{email}"'.format(
                email=email),
        ), codes.CONFLICT

    data = {
        'email': email,
        'password_hash': bcrypt.generate_password_hash(password).decode(
            'utf8'),
    }

    requests.post(
        urljoin(STORAGE_URL, '/users'),
        headers={'Content-Type': 'application/json'},
        data=json.dumps(data),
    )

    return jsonify(email=email, password=password), codes.CREATED


@app.route('/status', methods=['GET'])
@consumes('application/json')
def status():
    """
    Get information about the current activated user.

    :reqheader Content-Type: application/json
    :resheader Content-Type: application/json
    :resjson bool is_authenticated: There is a current authenticated user.
    :resjson string email: The email address of the current user. This is only
        given if there is a current authenticated user.
    :status 200:
    """
    if current_user.is_authenticated:
        return jsonify(is_authenticated=True, email=current_user.email)
    return jsonify(is_authenticated=False)

if __name__ == '__main__':   # pragma: no cover
    # Specifying 0.0.0.0 as the host tells the operating system to listen on
    # all public IPs. This makes the server visible externally.
    # See http://flask.pocoo.org/docs/0.10/quickstart/#a-minimal-application
    app.run(host='0.0.0.0')
