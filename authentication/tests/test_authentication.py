"""
Tests for authentication.authentication.
"""

import json
import re
import unittest

from flask.ext.login import make_secure_token
from requests import codes
import responses
from werkzeug.http import parse_cookie

from authentication.authentication import (
    app,
    bcrypt,
    load_user_from_id,
    load_user_from_token,
    User,
    STORAGE_URL,
)

from storage.tests.testtools import InMemoryStorageTests

# This is necessary because urljoin moved between Python 2 and Python 3
from future.standard_library import install_aliases
install_aliases()

# Ignore this line with linters because it necessarily comes after
# `install_aliases`.
from urllib.parse import urljoin  # noqa

USER_DATA = {'email': 'alice@example.com', 'password': 'secret'}


class AuthenticationTests(InMemoryStorageTests):
    """
    Connect to an in memory fake of the storage service and create a verified
    fake for ``requests`` to connect to.
    """

    def setUp(self):
        """
        Create an environment with a fake storage app available and mocked for
        ``requests``.
        """
        # This sets up variables to use as a fake storage service.
        super(AuthenticationTests, self).setUp()

        self.app = app.test_client()

        for rule in self.storage_app.url_map.iter_rules():
            # We assume here that everything is in the style:
            # "{uri}/{method}/<{id}>" or "{uri}/{method}" when this is
            # not necessarily the case.
            pattern = urljoin(
                STORAGE_URL,
                re.sub(pattern='<.+>', repl='.+', string=rule.rule),
            )

            for method in rule.methods:
                responses.add_callback(
                    # ``responses`` has methods named like the HTTP methods
                    # they represent, e.g. ``responses.GET``.
                    method=getattr(responses, method),
                    url=re.compile(pattern),
                    callback=self.request_callback,
                    content_type='application/json',
                )

    def request_callback(self, request):
        """
        Given a request to the storage service, send an equivalent request to
        an in memory fake of the storage service and return some key details
        of the response.

        :param request: The incoming request to pass onto the storage app.
        :return: A tuple of status code, response headers and response data
            from the storage app.
        """
        # The storage application is a ``werkzeug.test.Client`` and therefore
        # has methods like 'head', 'get' and 'post'.
        response = getattr(self.storage_app, request.method.lower())(
            request.path_url,
            content_type=request.headers['Content-Type'],
            data=request.body)

        return (
            response.status_code,
            {key: value for (key, value) in response.headers},
            response.data)


class SignupTests(AuthenticationTests):
    """
    Tests for the user sign up endpoint at ``/signup``.
    """

    @responses.activate
    def test_signup(self):
        """
        A signup ``POST`` request with an email address and password returns a
        JSON response with user credentials and a CREATED status.
        """
        response = self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.CREATED)
        self.assertEqual(json.loads(response.data.decode('utf8')), USER_DATA)

    @responses.activate
    def test_passwords_hashed(self):
        """
        Passwords are hashed before being saved to the database.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        user = load_user_from_id(user_id=USER_DATA['email'])
        self.assertTrue(bcrypt.check_password_hash(user.password_hash,
                                                   USER_DATA['password']))

    def test_missing_email(self):
        """
        A signup request without an email address returns a BAD_REQUEST status
        code and an error message.
        """
        response = self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps({'password': USER_DATA['password']}))
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.BAD_REQUEST)
        expected = {
            'title': 'There was an error validating the given arguments.',
            'detail': "'email' is a required property",
        }
        self.assertEqual(json.loads(response.data.decode('utf8')), expected)

    def test_missing_password(self):
        """
        A signup request without a password returns a BAD_REQUEST status code
        and an error message.
        """
        response = self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps({'email': USER_DATA['email']}))
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.BAD_REQUEST)
        expected = {
            'title': 'There was an error validating the given arguments.',
            'detail': "'password' is a required property",
        }
        self.assertEqual(json.loads(response.data.decode('utf8')), expected)

    @responses.activate
    def test_existing_user(self):
        """
        A signup request for an email address which already exists returns a
        CONFLICT status code and error details.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        data = USER_DATA.copy()
        data['password'] = 'different'
        response = self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.CONFLICT)
        expected = {
            'title': 'There is already a user with the given email address.',
            'detail': 'A user already exists with the email "{email}"'.format(
                email=USER_DATA['email']),
        }
        self.assertEqual(json.loads(response.data.decode('utf8')), expected)

    def test_incorrect_content_type(self):
        """
        If a Content-Type header other than 'application/json' is given, an
        UNSUPPORTED_MEDIA_TYPE status code is given.
        """
        response = self.app.post('/signup', content_type='text/html')
        self.assertEqual(response.status_code, codes.UNSUPPORTED_MEDIA_TYPE)


class LoginTests(AuthenticationTests):
    """
    Tests for the user log in endpoint at ``/login``.
    """

    @responses.activate
    def test_login(self):
        """
        Logging in as a user which has been signed up returns an OK status
        code.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        response = self.app.post(
            '/login',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        self.assertEqual(response.status_code, codes.OK)

    @responses.activate
    def test_non_existant_user(self):
        """
        Attempting to log in as a user which has been not been signed up
        returns a NOT_FOUND status code and error details..
        """
        response = self.app.post(
            '/login',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.NOT_FOUND)
        expected = {
            'title': 'The requested user does not exist.',
            'detail': 'No user exists with the email "{email}"'.format(
                email=USER_DATA['email']),
        }
        self.assertEqual(json.loads(response.data.decode('utf8')), expected)

    @responses.activate
    def test_wrong_password(self):
        """
        Attempting to log in with an incorrect password returns an UNAUTHORIZED
        status code and error details.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        data = USER_DATA.copy()
        data['password'] = 'incorrect'
        response = self.app.post(
            '/login',
            content_type='application/json',
            data=json.dumps(data))
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.UNAUTHORIZED)
        expected = {
            'title': 'An incorrect password was provided.',
            'detail': 'The password for the user "{email}" does not match the '
                      'password provided.'.format(email=USER_DATA['email']),
        }
        self.assertEqual(json.loads(response.data.decode('utf8')), expected)

    @responses.activate
    def test_remember_me_cookie_set(self):
        """
        A "Remember Me" token is in the response header of a successful login
        with the value of ``User.get_auth_token`` for the logged in user.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        response = self.app.post(
            '/login',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        cookies = response.headers.getlist('Set-Cookie')

        items = [list(parse_cookie(cookie).items())[0] for cookie in cookies]
        headers_dict = {key: value for key, value in items}
        token = headers_dict['remember_token']
        with app.app_context():
            user = load_user_from_id(user_id=USER_DATA['email'])
            self.assertEqual(token, user.get_auth_token())

    def test_missing_email(self):
        """
        A login request without an email address returns a BAD_REQUEST status
        code and an error message.
        """
        response = self.app.post(
            '/login',
            content_type='application/json',
            data=json.dumps({'password': USER_DATA['password']}))
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.BAD_REQUEST)
        expected = {
            'title': 'There was an error validating the given arguments.',
            'detail': "'email' is a required property",
        }
        self.assertEqual(json.loads(response.data.decode('utf8')), expected)

    def test_missing_password(self):
        """
        A login request without a password returns a BAD_REQUEST status code
        and an error message.
        """
        response = self.app.post(
            '/login',
            content_type='application/json',
            data=json.dumps({'email': USER_DATA['email']}))
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.BAD_REQUEST)
        expected = {
            'title': 'There was an error validating the given arguments.',
            'detail': "'password' is a required property",
        }
        self.assertEqual(json.loads(response.data.decode('utf8')), expected)

    def test_incorrect_content_type(self):
        """
        If a Content-Type header other than 'application/json' is given, an
        UNSUPPORTED_MEDIA_TYPE status code is given.
        """
        response = self.app.post('/login', content_type='text/html')
        self.assertEqual(response.status_code, codes.UNSUPPORTED_MEDIA_TYPE)


class LogoutTests(AuthenticationTests):
    """
    Tests for the user log out endpoint at ``/logout``.
    """

    @responses.activate
    def test_logout(self):
        """
        A POST request to log out when a user is logged in returns an OK status
        code.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        self.app.post(
            '/login',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        response = self.app.post('/logout', content_type='application/json')
        self.assertEqual(response.status_code, codes.OK)

    def test_not_logged_in(self):
        """
        A POST request to log out when no user is logged in returns an
        UNAUTHORIZED status code.
        """
        response = self.app.post('/logout', content_type='application/json')
        self.assertEqual(response.status_code, codes.UNAUTHORIZED)

    @responses.activate
    def test_logout_twice(self):
        """
        A POST request to log out, after a successful log out attempt returns
        an UNAUTHORIZED status code.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        self.app.post(
            '/login',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        self.app.post('/logout', content_type='application/json')
        response = self.app.post('/logout', content_type='application/json')
        self.assertEqual(response.status_code, codes.UNAUTHORIZED)

    def test_incorrect_content_type(self):
        """
        If a Content-Type header other than 'application/json' is given, an
        UNSUPPORTED_MEDIA_TYPE status code is given.
        """
        response = self.app.post('/logout')
        self.assertEqual(response.status_code, codes.UNSUPPORTED_MEDIA_TYPE)


class LoadUserTests(AuthenticationTests):
    """
    Tests for ``load_user_from_id``, which is a function required by
    Flask-Login.
    """

    @responses.activate
    def test_user_exists(self):
        """
        If a user exists with the email given as the user ID to
        ``load_user_from_id``, that user is returned.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        self.assertEqual(
            load_user_from_id(user_id=USER_DATA['email']).email,
            USER_DATA['email'],
        )

    @responses.activate
    def test_user_does_not_exist(self):
        """
        If no user exists with the email given as the user ID to
        ``load_user_from_id``, ``None`` is returned.
        """
        self.assertIsNone(load_user_from_id(user_id='email'))


class StatusTests(AuthenticationTests):
    """
    Tests for the endpoint to get the current user's details.
    """

    @responses.activate
    def test_user_logged_in(self):
        """
        A ``GET`` request for information about the logged in user returns an
        OK status code with a flag that there is an active user and that
        user's email address if there is a logged in user.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        self.app.post(
            '/login',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        response = self.app.get('/status', content_type='application/json')
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.OK)
        expected = {
            'is_authenticated': True,
            'email': USER_DATA['email'],
        }
        self.assertEqual(json.loads(response.data.decode('utf8')), expected)

    def test_no_user_logged_in(self):
        """
        A ``GET`` request for information about the logged in user returns an
        OK status code and a flag describing that there is no active user if
        there is no logged in user.
        """
        response = self.app.get('/status', content_type='application/json')
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.OK)
        expected = {
            'is_authenticated': False,
        }
        self.assertEqual(json.loads(response.data.decode('utf8')), expected)

    def test_incorrect_content_type(self):
        """
        If a Content-Type header other than 'application/json' is given, an
        UNSUPPORTED_MEDIA_TYPE status code is given.
        """
        response = self.app.get('/status', content_type='text/html')
        self.assertEqual(response.status_code, codes.UNSUPPORTED_MEDIA_TYPE)


class LoadUserFromTokenTests(AuthenticationTests):
    """
    Tests for ``load_user_from_token``, which is a function required by
    Flask-Login when using secure "Alternative Tokens".
    """

    @responses.activate
    def test_load_user_from_token(self):
        """
        A user is loaded if their token is provided to
        ``load_user_from_token``.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        response = self.app.post(
            '/login',
            content_type='application/json',
            data=json.dumps(USER_DATA))
        cookies = response.headers.getlist('Set-Cookie')

        items = [list(parse_cookie(cookie).items())[0] for cookie in cookies]
        headers_dict = {key: value for key, value in items}
        token = headers_dict['remember_token']
        with app.app_context():
            user = load_user_from_id(user_id=USER_DATA['email'])
            self.assertEqual(load_user_from_token(auth_token=token), user)

    @responses.activate
    def test_fake_token(self):
        """
        If a token does not belong to a user, ``None`` is returned.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))

        with app.app_context():
            self.assertIsNone(load_user_from_token(auth_token='fake'))


class DeleteUserTests(AuthenticationTests):
    """
    Tests for the delete user endpoint at ``DELETE /users/<email>``.
    """

    @responses.activate
    def test_delete_user(self):
        """
        A ``DELETE`` request to delete a user returns an OK status code and the
        email of the deleted user. The user no longer exists.
        """
        self.app.post(
            '/signup',
            content_type='application/json',
            data=json.dumps(USER_DATA))

        response = self.app.delete(
            '/users/{email}'.format(email=USER_DATA['email']),
            content_type='application/json')

        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.OK)
        self.assertEqual(
            json.loads(response.data.decode('utf8')),
            {'email': USER_DATA['email']})

        self.assertIsNone(load_user_from_id(user_id=USER_DATA['email']))

    @responses.activate
    def test_non_existant_user(self):
        """
        A ``DELETE`` request for a user which does not exist returns a
        NOT_FOUND status code and error details.
        """
        response = self.app.delete(
            '/users/{email}'.format(email=USER_DATA['email']),
            content_type='application/json')
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertEqual(response.status_code, codes.NOT_FOUND)
        expected = {
            'title': 'The requested user does not exist.',
            'detail': 'No user exists with the email "{email}"'.format(
                email=USER_DATA['email']),
        }
        self.assertEqual(json.loads(response.data.decode('utf8')), expected)

    def test_incorrect_content_type(self):
        """
        If a Content-Type header other than 'application/json' is given, an
        UNSUPPORTED_MEDIA_TYPE status code is given.
        """
        response = self.app.delete(
            '/users/{email}'.format(email=USER_DATA['email']),
            content_type='text/html',
        )

        self.assertEqual(response.status_code, codes.UNSUPPORTED_MEDIA_TYPE)


class UserTests(unittest.TestCase):
    """
    Tests for the ``User`` model.
    """

    def test_get_id(self):
        """
        ``User.get_id`` returns the email of a ``User``. This is required by
        Flask-Login as a unique identifier.
        """
        user = User(email='email', password_hash='password_hash')
        self.assertEqual(user.get_id(), 'email')

    def test_get_auth_token(self):
        """
        Authentication tokens are created using Flask-Login's
        ``make_secure_token`` function and the email address and password of
        the user.
        """
        user = User(email='email', password_hash='password_hash')
        with app.app_context():
            self.assertEqual(user.get_auth_token(),
                             make_secure_token('email', 'password_hash'))

    def test_different_password_different_token(self):
        """
        If a user has a different password hash, it will have a different
        token.
        """
        user_1 = User(email='email', password_hash='password_hash')
        user_2 = User(email='email', password_hash='different_hash')
        with app.app_context():
            self.assertNotEqual(user_1.get_auth_token(),
                                user_2.get_auth_token())
