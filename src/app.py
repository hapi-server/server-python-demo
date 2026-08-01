"""This script can be used to integrate a HAPI server into an existing ASGI
(1.) or WSGI application (2.). It is not intended to be run directly,
but can be (3.).

1. Integrating into an existing ASGI application (e.g. FastAPI or Starlette):

  `hapiserver.app(config)` (the `app` object built below) is itself a
  FastAPI/ASGI application, so it can be mounted as a sub-application under
  an existing ASGI app instead of being served standalone. This requires
  the hapiserver_demo package (see pyproject.toml) to be installed, e.g.
  by running `pip install -e .` from the server-python-demo repo root, so
  that "hapiserver_demo" resolves as an importable package regardless of
  the importing application's working directory:

    from hapiserver_demo.app import app as hapi_app
    from fastapi import FastAPI

    main_app = FastAPI()  # your existing ASGI application

    main_app.mount("/hapi", hapi_app)

  Then run your existing application as usual, e.g.:
    uvicorn main:main_app --host 0.0.0.0 --port 8001


3. Start server using (from the repo root, for local development/testing;
   does not require the package to be installed)
    Recommended:
      uvicorn src.app:app --host 0.0.0.0 --port 8001 --workers 4
    Alternative:
      gunicorn src.app:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001 --workers 4


"""

import os
import logging

import hapiserver
logging.getLogger('hapiserver').setLevel(logging.DEBUG)

# method = 1, 2, 3, and 4 demonstrate different ways to configure the HAPI server.
method = 4

# The following is used by a test.
# Override with the METHOD environment variable, if set.
method = int(os.environ.get("METHOD", method))

def _read_config(style):
  import json
  import pathlib

  path = pathlib.Path(__file__).parent / f"config-{style}.json"

  print(f"Reading config from {path}")
  with open(path) as file:
    config = json.load(file)

  return config

if method == 1:
  # Import functions and put function references in config.

  from .info import info
  from .data import data
  from .catalog import catalog

  functions = {
    "catalog": catalog,
    "info": info,
    "data": data
  }

  config = _read_config("functions")
  # Replace function strings with function references.
  config.update({"functions": functions})
  app = hapiserver.app(config)


if method == 2:
  # Reference functions in config as strings. Useful when full configuration
  # is stored in a .json file.

  config = _read_config("functions")
  app = hapiserver.app(config)


if method == 3:
  # Reference command line scripts for catalog, info, and data.
  # Pass the config file path (not a parsed dict) so that relative script
  # paths are resolved relative to the config file's directory (src/)
  # instead of the current working directory.

  import pathlib
  config_path = str(pathlib.Path(__file__).parent / "config-scripts.json")
  app = hapiserver.app(config_path)


if method == 4:
  # Alternatively, modify ENV["BIN_DIR"] to point to an absolute path.
  import pathlib
  config = _read_config("scripts")
  config["ENV"]["BIN_DIR"] = str(pathlib.Path(__file__).parent)
  app = hapiserver.app(config)
