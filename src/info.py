import logging

logger = logging.getLogger(__name__)

def info(dataset, config=None):

  # Options for {catalog,info,data}.py are stored in config["options"]
  options = (config or {}).get("options", {})
  logging.basicConfig(level=options.get("LOG_LEVEL", None))
  logger.debug(f"info() called with dataset={dataset}, config={config}")

  datasets = {
    "demo1": {
      "startDate": "1970-01-01Z",
      "stopDate": "1970-01-01T00:00:02Z",
      "sampleStartDate": "1970-01-01Z",
      "sampleStopDate": "1970-01-01T00:00:02Z",
      "cadence": "PT1S",
      "parameters": [
        {
          "name": "Time",
          "type": "isotime",
          "units": "UTC",
          "fill": None,
          "length": 24
        },
        {
          "name": "scalar",
          "type": "double",
          "units": "m",
          "fill": "nan",
          "description": "A scalar time series"
        }
      ]
    }
  }

  return datasets[dataset]


if __name__ == "__main__":
  """
  Allow info.py to be run as a command line script for testing or 
  usage in a server configuration that references command line scripts
  instead of function references.
  """
  from hapiserver.cli import cl_call
  cl_call(info)