"""
This is a demo data source for a HAPI server. This example was written so that
modifying it for file-based datasets is straightforward. The primary changes
needed are to the _file_list(), _read(), _subset(), and _reformat() functions.

Usage and examples:
  python data.py --help
"""

import logging

logger = logging.getLogger(__name__)


def data(dataset, parameters, start, stop, format=None, config=None):
  """Generate data files for the given dataset and parameters.

  Args:
      dataset (_type_): A dataset ID string from the catalog.
      parameters (_type_): A comma-separated list of parameters to return. If empty, return all parameters.
      start (str): Start time in ISO 8601 format with microsecond precision.
      stop (str): Stop time in ISO 8601 format with microsecond precision.
      format (str, optional): Output format. Currently only 'csv' is supported. Defaults to None.
      config (dict, optional): Configuration dictionary. Defaults to None.

  Yields:
      If format='csv' or None, yields a CSV string of data.

  Notes:
  * Start and stop passed are always to microsecond precision with format
    '%Y-%m-%dT%H:%M:%S.%fZ' by hapiserver.
  * When called from hapiserver, the arguments are validated before calling data().
  * Do not change the function signature of data().
  """

  # Options for {catalog,info,data}.py are stored in config["options"]
  options = (config or {}).get("options", {})
  logging.basicConfig(level=options.get("LOG_LEVEL", None))
  msg = f"parameters={parameters}, start={start}, stop={stop}, format={format}"
  logger.debug(f"data() called with dataset={dataset}, {msg}")

  # In production use, this can be omitted because hapiserver validates the
  # arguments before calling data().
  _check_args(dataset, parameters, start, stop, format=format, config=config)

  # Get list of files that contain data for the given dataset and time range.
  files = _file_list(dataset, parameters=parameters, start=start, stop=stop, config=config)

  if len(files) == 0:
    logger.debug("No files to read")
    yield ""
    return

  for file in files:
    data = _read(file, parameters=parameters, start=start, stop=stop, config=config)
    yield _reformat(data, format=format)


def _subset(data, parameters, start, stop):
  """
  Subset the data to the requested parameters, start, and stop times.
  """

  if not parameters:
    columns = ['scalar']
  else:
    columns = [p for p in parameters.split(',') if p != 'Time']

  data = data[(data.index >= start) & (data.index < stop)][columns]

  # index is a string of the form '%Y-%m-%dT%H:%M:%S.%fZ'; truncate to
  # '%Y-%m-%dT%H:%M:%SZ' without parsing it back into a datetime.
  data.index = data.index.str.slice(0, 19) + 'Z'
  data.index.name = 'Time'

  return data


def _reformat(data, format=None):
  return data.to_csv(index=True, header=False)


def _read(file_name, parameters=None, start=None, stop=None, config=None):
  """
  Simulate a data source that provides data in chunks of 1 minute.
  _read_file() always returns data in one-minute chunks that start on the
  0th minute of each hour.

  Performance notes for file readers:
  * If the files are slow to read and disk space is available, cache .npy or .pkl
    files to speed up reading.
  """

  import os
  import pandas

  use_cache = False
  write_cache = False
  cache_file = file_name.replace(".txt", ".pkl")

  cache_dir = (config or {}).get('options', {}).get('CACHE_DIR') or 'cache'
  cache_file = os.path.join(cache_dir, os.path.basename(cache_file))

  if use_cache and os.path.exists(cache_file):
    logger.debug(f"Reading {file_name} from cache")
    # Placeholder for reading from cache file, e.g.,
    # data = read_cache(cache_file)
    # return _subset_file(data, parameters, start, stop)
    pass

  logger.debug(f"Reading {file_name}")

  file_name = os.path.abspath(file_name)
  file_start, file_stop = os.path.basename(file_name).replace(".txt", "").split('_')
  file_start = pandas.Timestamp(file_start)
  file_stop = pandas.Timestamp(file_stop)

  # Create a DataFrame with time from start to stop with 1 second cadence
  # and a scalar value that is the number of seconds since 1970-01-01T00:00:00Z

  time_index = pandas.date_range(start=file_start, end=file_stop, freq='1s', inclusive='left')
  time = time_index.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
  unix_0 = pandas.Timestamp('1970-01-01T00:00:00Z')
  scalar = (time_index - unix_0) // pandas.Timedelta('1s')
  scalar = scalar.astype('int32')

  data = pandas.DataFrame({'scalar': scalar}, index=pandas.Index(time, name='Time'))

  if write_cache:
    cache_file = file_name.replace(".txt", ".pkl")
    # Write file.npy to disk
    data.to_pickle(cache_file)

  return _subset(data, parameters, start, stop)


def _file_list(dataset, parameters=None, start=None, stop=None, config=None):
  """
  Return a list of files that contain data for the given dataset and time range.
  """

  """
  Here we simulate a data source that provides data in chunks of 1 minute with
  file names in the format 'start_stop.txt' where start and stop have the form
  %Y-%m-%dT%H:%MZ.
  """
  import os
  import datetime

  def dt2str(dt):
    return dt.strftime(tfmt_red)

  tfmt_red = '%Y-%m-%dT%H:%MZ'
  tfmt_full = '%Y-%m-%dT%H:%M:%S.%fZ'

  # Not used here, but could be.
  data_dir = (config or {}).get('options', {}).get('DATA_DIR') or 'data'
  logger.debug(f"data_dir = {data_dir}")

  files = []
  # Round down to the nearest minute
  file_start = datetime.datetime.strptime(start, tfmt_full).replace(second=0, microsecond=0)
  while file_start < datetime.datetime.strptime(stop, tfmt_full):
    file_stop = file_start + datetime.timedelta(minutes=1)
    file_name = os.path.join(data_dir, f"{dt2str(file_start)}_{dt2str(file_stop)}.txt")
    files.append(file_name)
    file_start = file_stop

  n = len(files)
  logger.debug(f"Files to read ({n}): {files}")

  return files


def _check_args(dataset, parameters, start, stop, format=None, config=None):
  """
  Check arguments to data() function. Raise ValueError if any argument is invalid.

  These checks are not needed when hapiserver calls data() because hapiserver
  validates the arguments before calling data().
  """
  import datetime

  if format not in (None, 'csv'):
    raise ValueError(f"Unsupported format: {format}")

  # Verify format is '%Y-%m-%dT%H:%M:%S.%fZ'
  if len(start) != 27 or len(stop) != 27:
    raise ValueError("start and stop must be in format '%Y-%m-%dT%H:%M:%S.%fZ'")

  request = {}
  for arg in (start, stop):
    try:
      request[arg] = datetime.datetime.strptime(arg, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
      raise ValueError(f"{arg} must be in format '%Y-%m-%dT%H:%M:%S.%fZ'")

  if request[start] >= request[stop]:
    raise ValueError("start must be before stop")


if __name__ == "__main__":
  """
  Allow data.py to be run as a command line script for testing or 
  usage in a server configuration that references command line scripts
  instead of function references.
  """
  from hapiserver.cli import cl_call
  cl_call(data)
