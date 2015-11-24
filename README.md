[![Requirements Status](https://requires.io/github/jenca-cloud/jenca-authentication/requirements.svg?branch=master)](https://requires.io/github/jenca-cloud/jenca-authentication/requirements/?branch=master) [![Build Status](https://travis-ci.org/jenca-cloud/jenca-authentication.svg?branch=master)](https://travis-ci.org/jenca-cloud/jenca-authentication) [![Coverage Status](https://coveralls.io/repos/jenca-cloud/jenca-authentication/badge.svg?branch=master&service=github)](https://coveralls.io/github/jenca-cloud/jenca-authentication?branch=master) [![Documentation Status](https://readthedocs.org/projects/jenca-authentication/badge/?version=latest)](http://jenca-authentication.readthedocs.org/en/latest/?badge=latest)

# jenca-authentication

An authentication service for Jenca Cloud.

The full documentation for this service can be seen at http://jenca-authentication.readthedocs.org/.


## Running this service

This comes with a [Docker Compose](https://docs.docker.com/compose/) file. 

With Docker Compose available, perhaps in the Jenca Cloud Vagrant development environment, run:

```
docker-compose build
docker-compose up
```

to start the API service.

To run commands against the API, on OS X with Docker Machine for example:

```
$ docker-machine ip dev
$ 192.168.99.100
$ curl -X POST \
  -g '192.168.99.100:5000/signup' \
  -d email='user@example.com' \
  -d password='secret' \
  -c ~/Desktop/my_cookie
```

## Development

This service is written using Python and [Flask](http://flask.pocoo.org).

To start developing quickly, it is recommended that you create a `virtualenv` and install the requirements and run the tests inside it:

```
(my_virtualenv)$ pip install -e .[dev]
```

Tests are run on [Travis-CI](https://travis-ci.org/jenca-cloud/jenca-authentication).


### Documentation

To build the documentation locally, install the development requirements and then use the Makefile in the `docs/` directory:

```
(my_virtualenv)$ make -C docs/ html
```

To view this build documentation, run:

```
$ open docs/build/html/index.html
```

## TODO

* Better persistence of the database with Docker volumes (maybe a different service or container for persistence).
* Better auth tokens, see https://flask-login.readthedocs.org/en/latest/#remember-me.
* Perhaps login should happen after signup, this should be factored out.
* API responses should have good messages, data, not just status codes
* Validate schema of JSON, e.g. with https://github.com/mattupstate/flask-jsonschema or http://pythonhosted.org/Flask-Inputs/
* Some kind of versioning system
* Flesh out setup.py