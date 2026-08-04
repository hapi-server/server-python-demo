"""
This is a demo data source for a HAPI server. This example was written so that
modifying it for file-based datasets is straightforward. The primary changes
needed are to the _file_list() and _read() functions.

Usage and examples:
  python data.py --help
"""

import logging

logger = logging.getLogger(__name__)


def data(dataset, parameters, start, stop, format=None, config=None):
  """Generate data for the given dataset and parameters from start (inclusive) to stop (exclusive).

  Args:
    dataset (str): A dataset ID string from the catalog.
    parameters (str): A comma-separated list of parameters to return. If '', return all parameters.
    start (str): Start time in ISO 8601 format with microsecond precision in format '%Y-%m-%dT%H:%M:%S.%fZ'.
    stop (str): Stop time in ISO 8601 format with microsecond precision in format '%Y-%m-%dT%H:%M:%S.%fZ'.
    format (str, optional): Output format. Currently only 'csv' is supported.
    config (dict, optional): Configuration dictionary.

  Yields:
    If format='csv' or None, yields a CSV string of data.

  Notes:
  * Start and stop passed are always to microsecond precision with format
    '%Y-%m-%dT%H:%M:%S.%fZ' by hapiserver.
  * When called from hapiserver, the arguments to data() are validated.
  * Do not change the function signature of data().
  """

  import json

  # Options for {catalog,info,data}.py are stored in config["options"]
  options = (config or {}).get("options", {})
  logging.basicConfig(level=options.get("LOG_LEVEL", None))
  msg = f"parameters={parameters}, start={start}, stop={stop}, format={format}"
  logger.debug(f"data() called with dataset={dataset}, {msg}")


  # In production use, _check_args() call may be omitted because hapiserver
  # validates the arguments before calling data() (either the function or via
  # the command line).
  _check_args(dataset, parameters, start, stop, format=format, config=config)


  # Get info for files that contain data for the given dataset and time range.
  file_list = _file_list(dataset, parameters, start, stop, config=config)
  """
  file_list has the form
  [
    {'file_name': 'filename1', 'start_data': iso8601, 'stop_data': iso8601},
    {'file_name': 'filename2', 'start_data': iso8601, 'stop_data': iso8601},
    ...
  ]
  where start_data and stop_data are timestamps of the first and last records
  in the file in ISO 8601 format with microsecond precision ('%Y-%m-%dT%H:%M:%S.%fZ').
  stop_data is exclusive.
  """
  logger.debug(f"file_list = \n{json.dumps(file_list, indent=2)}")

  if len(file_list) == 0:
    logger.debug("No files to read")
    yield ""
    return

  # Compute the first and last records to read in each file. If max_seconds is
  # set, limit the number of seconds for each read to max_seconds.
  max_seconds = options.get("MAX_SECONDS", None)
  read_list = _read_list(file_list, start, stop, max_seconds=max_seconds)
  logger.debug(f"read_list = \n{json.dumps(read_list, indent=2)}")

  for read_info in read_list:
    args = [read_info['file_name'], dataset, parameters, read_info['start_read'], read_info['stop_read']]
    data = _read(*args, config=config)
    yield _reformat(data, format=format)


def _read(file_name, dataset, parameters, start, stop, config=None):
  """
  Simulate a data source that provides a data frame from files with 1 minute of
  data per file for a given dataset and parameters and from start to stop (with
  stop exclusive).

  Performance notes for file readers:
  * If the files are slow to read and disk space is available, cache .npy or .pkl
    files to speed up reading.
  """

  import os
  import pandas

  file_name = os.path.abspath(file_name)
  start_read = pandas.Timestamp(start)
  stop_read = pandas.Timestamp(stop)

  msg = f"Reading {file_name} from {start_read} to {stop_read}"
  logger.debug(msg)

  # Create a DataFrame with time from start_read to stop_read with 1 second cadence
  # and a scalar value that is the number of seconds since 1970-01-01T00:00:00Z
  time_index = pandas.date_range(start=start_read, end=stop_read, freq='1s', inclusive='left')
  time_str = time_index.strftime('%Y-%m-%dT%H:%M:%SZ')
  unix_0 = pandas.Timestamp('1970-01-01T00:00:00Z')
  scalar = (time_index - unix_0) // pandas.Timedelta('1s')

  # Convert to int32 because pandas writes integers as int64 and JSON does not
  # support int64.
  scalar = scalar.astype('int32')

  index = pandas.Index(time_str, name='Time')
  data = pandas.DataFrame({'scalar': scalar}, index=index)

  return data


def _file_list(dataset, parameters, start, stop, config=None):
  """
  Return a list of the form
  [
    {'file_name': 'filename1', 'start_data': iso8601, 'stop_data': iso8601},
    {'file_name': 'filename2', 'start_data': iso8601, 'stop_data': iso8601},
    ...
  ]
  where start_data and stop_data are timestamps of the first and last records
  in the file in ISO 8601 format with microsecond precision ('%Y-%m-%dT%H:%M:%S.%fZ').
  stop_data is exclusive.
  """

  """
  Here we simulate a data source that provides data with files containing 1
  minute of data and file names in the format 'start_stop.txt' where start and
  stop have the form %Y-%m-%dT%H:%MZ.
  """

  import os
  import datetime

  def dt2str(dt):
    return dt.strftime('%Y-%m-%dT%H:%MZ')

  tfmt_full = '%Y-%m-%dT%H:%M:%S.%fZ'

  # Not used here, but could be.
  data_dir = (config or {}).get('options', {}).get('DATA_DIR') or 'data'
  logger.debug(f"data_dir = {data_dir}")

  file_list = []
  # Round down to the nearest minute
  file_start = datetime.datetime.strptime(start, tfmt_full).replace(second=0, microsecond=0)
  while file_start < datetime.datetime.strptime(stop, tfmt_full):
    file_stop = file_start + datetime.timedelta(minutes=1)
    file_name = os.path.join(data_dir, f"{dt2str(file_start)}_{dt2str(file_stop)}.txt")

    file_list.append({
      'file_name': file_name,
      'start_data': datetime.datetime.strftime(file_start, tfmt_full),
      'stop_data': datetime.datetime.strftime(file_stop, tfmt_full)
    })
    file_start = file_stop

  n = len(file_list)
  logger.debug(f"Files to read ({n}): {[f['file_name'] for f in file_list]}")

  return file_list


def _read_list(file_list, start, stop, max_seconds=None):
  """
  read_list has the form
  [
    {'file_name': 'filename1', 'start_read': iso8601, 'stop_read': iso8601, 'start_data': iso8601, 'stop_data': iso8601},
    {'file_name': 'filename1', 'start_read': iso8601, 'stop_read': iso8601, 'start_data': iso8601, 'stop_data': iso8601},
    ...
    {'file_name': 'filename2', 'start_read': iso8601, 'stop_read': iso8601, 'start_data': iso8601, 'stop_data': iso8601},
    {'file_name': 'filename2', 'start_read': iso8601, 'stop_read': iso8601, 'start_data': iso8601, 'stop_data': iso8601},
    ...
  ]
  where first and last are are timestamps of the first and last records to read
  in the file in ISO 8601 format with microsecond precision ('%Y-%m-%dT%H:%M:%S.%fZ').
  stop_data and stop_read are exclusive.
  """

  import datetime

  tfmt_full = '%Y-%m-%dT%H:%M:%S.%fZ'
  max_delta = None
  if max_seconds is not None:
    max_delta = datetime.timedelta(seconds=max_seconds)
    if max_delta <= datetime.timedelta(0):
      raise ValueError("max_seconds must be positive")

  read_list = []
  for file_info in file_list:
    start_read = datetime.datetime.strptime(max(file_info['start_data'], start), tfmt_full)
    stop_read = datetime.datetime.strptime(min(file_info['stop_data'], stop), tfmt_full)

    while start_read < stop_read:
      stop_i = stop_read if max_delta is None else min(start_read + max_delta, stop_read)
      read_list.append({
        'file_name': file_info['file_name'],
        'start_read': datetime.datetime.strftime(start_read, tfmt_full),
        'stop_read': datetime.datetime.strftime(stop_i, tfmt_full),
        'start_data': file_info['start_data'],
        'stop_data': file_info['stop_data']
      })
      start_read = stop_i

  return read_list


def _reformat(data, format=None):
  return data.to_csv(index=True, header=False)


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
