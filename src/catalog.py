import logging

logger = logging.getLogger(__name__)

def catalog(depth=None, config=None):
  """
  Return the catalog of datasets.

  Do not change the arguments of catalog() because hapiserver expects the
  given signature.

  Note that HAPI clients expect /catalog responses to be fast (not much slower
  than the time to read and send a file the size of a catalog from disk). If
  building the catalog requires a long time, consider caching the catalog
  response in a file and updating the file when there is a change.
  """

  # Options for {catalog,info,data}.py are stored in config["options"]
  options = (config or {}).get("options", {})
  logging.basicConfig(level=options.get("LOG_LEVEL", None))
  logger.debug(f"catalog() called with depth={depth}, config={config}")

  cat = [
    {
      "id": "demo1",
      "title": "Demo dataset 1"
    }
  ]

  if depth == 'all':
    """
    Add /info response metadata for each dataset in the catalog. This allows
    users to make request /hapi/catalog?depth=all to get the catalog with
    info for each dataset in one request instead of having to make a separate
     request for each dataset. This is especially useful when there are 1000s of
    datasets in the catalog and an application needs all of them (e.g., a
    search application).
    """
    if __package__:
      from bin.info import info
    else:
      from info import info

    for dataset in cat:
      dataset["info"] = info(dataset["id"], config=config)

  return cat

if __name__ == "__main__":
  """
  Allow catalog.py to be run as a command line script for testing or 
  usage in a server configuration that references command line scripts
  instead of function references.
  """
  from hapiserver.cli import cl_call
  cl_call(catalog)
