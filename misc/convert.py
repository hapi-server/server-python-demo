def reformat(data, out_format, meta):
  import numpy
  if isinstance(data, numpy.ndarray):
    if out_format == 'binary':
      return df2binary(data, meta)
    elif out_format == 'csv':
      import pandas as pd
      df = pd.DataFrame(data)
      return df.to_csv(index=False)
    elif out_format == 'dataframe':
      return np2df(data, meta)
    else:
      raise ValueError(f"Unsupported output format: {out_format}")


def df2binary(data, meta):
  """"""

  import numpy as np

  # Get time strings from index
  time_strings = data.index.values
  n_records = len(time_strings)

  if n_records == 0:
    return b''

  # HAPI binary format: fixed-length null-terminated time string (24 bytes)
  # followed by numeric values as int32 or float64
  time_length = 24

  # Get numeric data columns and determine dtypes
  data_values = data.values  # NumPy array (n_records, n_columns)

  # Build dtype list for structured array: time + numeric fields
  dtype_list = [('time', f'S{time_length}')]

  for col_idx in range(data_values.shape[1]):
    col = data_values[:, col_idx]
    if np.issubdtype(col.dtype, np.integer):
      dtype_list.append((f'col{col_idx}', '<i4'))  # Little-endian int32
    else:
      dtype_list.append((f'col{col_idx}', '<f8'))  # Little-endian float64

  # Create structured array - this packs data efficiently without Python loops
  structured = np.zeros(n_records, dtype=dtype_list)

  # Assign time strings (NumPy handles encoding and padding automatically)
  structured['time'] = time_strings.astype(f'S{time_length}')

  # Assign numeric columns with appropriate type conversion
  for col_idx in range(data_values.shape[1]):
    col = data_values[:, col_idx]
    if np.issubdtype(col.dtype, np.integer):
      structured[f'col{col_idx}'] = col.astype(np.int32)
    else:
      structured[f'col{col_idx}'] = col.astype(np.float64)

  # Convert to bytes - this is the fast, vectorized operation
  return structured.tobytes()


def df2np(df, meta):
  # Convert pandas DataFrame to NumPy ndarray with named fields. Convert
  # time back to string for consistency with HAPI data format.
  import numpy as np
  from hapiclient import datetime2hapitime

  time_name = meta['parameters'][0]['name']

  # Convert datetime back to HAPI ISO 8601 format using datetime2hapitime
  # Convert pandas datetime to list of Python datetime objects
  df[time_name] = datetime2hapitime(list(df[time_name].dt.to_pydatetime()))

  return df.to_records(index=False).view(np.ndarray)

def np2df(data, meta, nan_fill=False, parameters_include=None, parameters_exclude=None, name_map=None):
  """
  Convert output of hapi() to a pandas DataFrame.

  nan_fill : bool
      If True, data will fill value with NaN. Default is False.
      For string parameters, no fill option.
      For isotime parameters, fill with numpy.datetime64('NaT', 'us').
      For integer parameters, convert to float and fill with numpy.nan.
      For double parameters, fill with numpy.nan.

  parameters_include : list or None
      List of parameter names to include. If None, include all parameters.

  parameters_exclude : list or None
      List of parameter names to exclude. If None, exclude no parameters.

  name_map : dict or None
      Dictionary mapping original parameter names to new names.
      For MultiIndex columns (e.g., vectors), only rename the first level (parameter name), not the second level (column number).
      If None, no renaming is performed.

  Describe how multidimentional parameters are handled.
  #https://stackoverflow.com/questions/36760414/how-to-create-pandas-dataframes-with-more-than-2-dimensions
  """

  import pandas
  import numpy as np

  from hapiclient import hapitime2datetime

  #pandas.set_option('display.max_columns', None) # display all columns when printing dataframe, for testing

  dfs = []

  time_name = meta['parameters'][0]['name']
  param_names = [p['name'] for p in meta['parameters']]

  if parameters_include is not None:
    for param_name in parameters_include:
      # If parameter in parameters_include but not in meta['parameters'], raise error
      if param_name not in param_names:
        msg = f"Parameter {param_name} in parameters_include is not one of {param_names}"
        raise ValueError(msg)
    if time_name not in parameters_include:
      parameters_include = parameters_include.copy()
      # Always include time parameter
      parameters_include.append(time_name)

  if parameters_exclude is not None:
    for param_name in parameters_exclude:
      if param_name not in param_names:
        # If parameter name in parameters_exclude but not in meta['parameters']
        msg = f"Parameter {param_name} in parameters_exclude is not one of {param_names}"
        raise ValueError(msg)
    if time_name in parameters_exclude:
      raise ValueError(f"Primary time parameter {time_name} cannot be excluded.")

  if name_map is not None:
    for name in name_map:
      msg_o = f"Name {name} in name_map does not match a"
      if parameters_include is not None and name not in parameters_include:
        msg = f"{msg_o} name in parameters_include ({parameters_include})"
        raise ValueError(msg)
      elif name not in param_names:
        msg = f"{msg_o} parameter name ({param_names})"
        raise ValueError(msg)

  for param in meta['parameters']:
    param_name = param['name']

    if parameters_include is not None:
      # only include parameters in parameters_include
      if param_name not in parameters_include:
        continue
    if parameters_exclude is not None:
      # exclude parameters in parameters_exclude
      if param_name in parameters_exclude:
        continue

    if param_name == time_name:
      # Convert primary time parameter to datetime
      df_time = pandas.DataFrame({param_name: hapitime2datetime(data[param_name])})
      dfs.append(df_time)
    else:
      param_data = data[param_name]

      fill = param.get('fill')
      if nan_fill and fill is not None:
        # Convert fill values to NaN or NaT as appropriate for the parameter type
        param_data = _nan_fill(param_data, param['type'], fill, nan_fill)

      if param['type'] == 'string' and ',' in param_data.flatten()[0]:
        # Handle vector strings; split vector strings into multiple columns
        # TODO: Use csv parser in case of quoted strings with commas.
        str_splits = [s.strip('"').split(',') for s in param_data.flatten()]
        max_len = max(len(s) for s in str_splits)

        # Pad with empty strings
        str_array = np.array([s + [''] * (max_len - len(s)) for s in str_splits])
        param_data = str_array.reshape(param_data.shape + (max_len,))

      col_names = _col_names(param_name, param_data.ndim, param_data.shape)

      # flatten all but first dimension (time/records)
      data_flat = param_data.reshape(param_data.shape[0], -1)

      df_data = pandas.DataFrame(data_flat, columns=col_names)

      dfs.append(df_data)

  df = pandas.concat(dfs, axis=1)

  _rename_columns(df, time_name, name_map)

  return df


def _rename_columns(df, time_name, name_map):
  if name_map is not None:
    # rename columns using name_map
    # for MultiIndex columns, only rename the first level (parameter name),
    # not the second level (column number)
    col_names = df.columns
    col_names_new = []
    for col in col_names:
      if isinstance(col, tuple):
        # MultiIndex column
        col_new = (name_map.get(col[0], col[0]),) + col[1:]
      else:
        col_new = name_map.get(col, col)
      col_names_new.append(col_new)
    df.columns = col_names_new
    df.rename(columns=dict(zip(col_names, col_names_new)), inplace=True)
    if time_name in name_map:
      df.index.rename(name_map[time_name], inplace=True)


def _col_names(param_name, ndim, shape):
  import itertools

  if ndim == 1:
    col_names = [param_name]
  else:
    # use MultiIndex for > 1D parameters
    # Create hierarchical column index: param name at top level, then indices
    # e.g., for vector param "mag" with shape = 3:
    # ('mag', (0,)), ('mag', (1,)), ('mag', (2,))
    # and for 2D param "matrix" with shape = (3, 3):
    # ('matrix', (0, 0)), ('matrix', (0, 1)), ('matrix', (0, 2)),
    # ('matrix', (1, 0)), ('matrix', (1, 1)), ('matrix', (1, 2)),
    # ('matrix', (2, 0)), ('matrix', (2, 1)), ('matrix', (2, 2)),
    # Generate all index combinations for the shape (excluding first dimension which is time/records)
    # For example, if size = (3, 3), components = [range(3), range(3)]
    components = [range(shape[i]) for i in range(1, ndim)]

    index_tuples = list(itertools.product(*components))
    # Create column names as (param_name, index_tuple) for each index combination
    col_names = [(param_name, idx_tuple) for idx_tuple in index_tuples]

  return col_names


def _nan_fill(data, param_type, fill_value, nan_fill):
  import numpy as np

  from hapiclient import hapitime2datetime

  if param_type == 'isotime':
    param_data = hapitime2datetime(data)
    fill_0 = "0000-00-00T00:00:00Z"
    if fill_value == fill_0:
      # fill_0 is a sometimes used fill value that is not a valid date. Convert to NaT.
      fill = hapitime2datetime("0001-01-01T00:00:00Z")
      # replace fill value in data
      param_data = np.where(param_data == hapitime2datetime(fill_0), fill, param_data)
    else:
      fill = hapitime2datetime(fill_value)
    # convert to datetime and fill with NaT
    param_data = np.where(param_data == fill, np.datetime64('NaT', 'us'), param_data)
  elif param_type == 'integer':
    param_data = np.where(data == int(fill_value), np.nan, data)
  elif param_type == 'double':
    param_data = np.where(data == float(fill_value), np.nan, data)
  else:
    raise ValueError(f"Data has unsupported type: {param_type}")

  return param_data



def np2df_test(versions=None, add_nan=False, add_names=False):

  import numpy as np
  from hapiclient import hapi

  if versions is None:
    versions = ['2.0', '2.1', '3.0', '3.1', '3.2', '3.3']

  version = versions[0]
  server = f'http://hapi-server.org/servers/TestData{version}/hapi'
  datasets = [entry['id'] for entry in hapi(server)['catalog']]

  dataset = datasets[0]
  meta = hapi(server, dataset)
  start  = '1970-01-01Z'
  stop   = '1970-01-01T00:00:11Z'

  for param in meta['parameters']:
    print(f"Testing TestData{version}, {dataset}, {param['name']} ...")
    data, meta = hapi(server, dataset, param['name'], start, stop)
    df = np2df(data, meta, nan_fill=False, name_map=None)
    data_np = df2np(df, meta)
    print(data)
    print(data_np)
    assert np.array_equal(data, data_np), f"Data mismatch for parameter {param['name']}"
    if param['name'] == 'vector':
      breakpoint()
    print(df)

  exit()
  for version in versions:
    server = f'http://hapi-server.org/servers/TestData{version}/hapi'
    datasets = [entry['id'] for entry in hapi(server)['catalog']]

    for dataset in datasets:
      print(f'Testing TestData{version}, {dataset} ...')

      parameters = '' # all parameters
      if version == '3.2':
        start  = hapi(server,dataset)['startDate'] #TODO: this for all versions
        stop   = hapi(server,dataset)['stopDate']
      else:
        start  = '1970-01-01Z' # min 1970-01-01Z
        stop   = '1970-01-01T00:00:11Z' # max 2016-12-31Z

      data, meta = hapi(server, dataset, parameters, start, stop)

      if add_nan:
        data = _add_nan(data, meta) # add fill values for testing
        nan_fill = True
      else:
        nan_fill = False
      if add_names:
        # add _new to parameter names for testing
        name_map = {param['name']: f"{param['name']}_new" for param in meta['parameters']}
      else:
        name_map = None

      df = np2df(data, meta, nan_fill=nan_fill, name_map=name_map)

      print(df)


def _add_nan(data, meta, parameters=None, debug=False):
  if parameters is None or parameters == '':
    parameters = meta['parameters']
  else:
    parameters = [param for param in meta['parameters'] if param['name'] in parameters]
  for param in parameters:
    param_name = param['name']
    if param.get('fill') is not None:
      if debug:
        # print parameter name, data, dtype, and fill value for testing
        print(param_name, data[param_name], data[param_name].dtype, param.get('fill')) 
        pass
      if data[param_name].ndim == 1:
        data[param_name][0] = param.get('fill')
      else:
        for col in range(data[param_name].shape[1]):
          data[param_name][0, col] = param.get('fill')
  return data


if __name__ == "__main__":
  np2df_test(add_nan=True, add_names=True)