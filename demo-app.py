# Start server using
#   Recommended:
#     uvicorn demo-app:app --host 0.0.0.0 --port 8001 --workers 4
#   Alternative:
#     gunicorn demo-app:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001 --workers 4

import os
import logging

import hapiserver
logging.getLogger('hapiserver').setLevel(logging.DEBUG)

# method = 1, 2, and 3 demonstrate different ways to configure the HAPI server.
method = 3

# The following is used by a test.
# Override with the METHOD environment variable, if set.
method = int(os.environ.get("METHOD", 3))

def _read_config():
  import json
  import pathlib

  path = pathlib.Path(__file__).parent / "bin" / "config.json"

  with open(path) as file:
    config = json.load(file)
  return config

if method == 1:
  # Import functions and put function references in config.

  from bin.info import info
  from bin.data import data
  from bin.catalog import catalog

  functions = {
    "catalog": catalog,
    "info": info,
    "data": data
  }

  config = _read_config()
  config.update({"functions": functions})
  app = hapiserver.app(config)


if method == 2:
  # Reference functions in config as strings. Useful when full configuration
  # is stored in a .json file.

  config = _read_config()
  config.update({
    "functions": {
      "catalog": "bin.catalog.catalog",
      "info": "bin.info.info",
      "data": "bin.data.data"
    }
  })

  app = hapiserver.app(config)


if method == 3:
  # Reference command line scripts for catalog, info, and data.
  # $BIN_DIR is replaced with the value of config["ENV"]["BIN_DIR"]
  # and if it is a relative path, it is resolved relative to current working
  # directory.
  config = _read_config()
  # Store variables referenced in config in ENV.
  config.update({
    "ENV": {
      "BIN_DIR": "bin"
    }
  })
  config.update({
    "scripts": {
      "catalog": "$BIN_DIR/catalog.py --depth={depth} --config={config}",
      "info": "$BIN_DIR/info.py --dataset={dataset} --config={config}",
      "data": "$BIN_DIR/data.py --dataset={dataset} --parameters={parameters} --start={start} --stop={stop} --format={format} --config={config}"
    }
  })

  app = hapiserver.app(config)
