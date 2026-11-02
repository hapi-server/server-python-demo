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


def df2np(df, meta=None):
  """Convert pandas DataFrame to NumPy structured array.

  Args:
      df (pandas.DataFrame): Input DataFrame to convert.
      meta (dict): HAPI info metadata dict.

  Returns:
      numpy.ndarray: NumPy structured array representing the DataFrame.
  """
  import numpy as np
  import pandas as pd
  from hapiclient import datetime2hapitime

  if not isinstance(df, (pd.DataFrame, pd.Series)):
    raise ValueError(f"Input must be a pandas DataFrame, got {type(df)}")

  if df.empty:
    raise ValueError("Input DataFrame is empty")

  meta_i = df_infer_meta(df)

  if meta is None:
    meta = meta_i
  else:
    if len(meta_i['parameters']) != len(meta['parameters']):
      msg = (f"Number of parameters in meta ({len(meta['parameters'])}) does "
             f"not match inferred meta ({len(meta_i['parameters'])})")
      raise ValueError(msg)
    names = [param['name'] for param in meta['parameters']]
    names_i = [param['name'] for param in meta_i['parameters']]
    if set(names) != set(names_i):
      msg = (f"Parameter names in meta ({names}) do not match inferred meta "
             f"({names_i})")
      raise ValueError(msg)
    else:
      # Report error if parameter order is different
      if names != names_i:
        msg = (f"Parameter order in meta ({names}) does not match inferred "
               f"meta ({names_i})")
        raise ValueError(msg)

    # Check that meta_i and meta parameters are consistent
    for i, param_i in enumerate(meta_i['parameters']):
      param = meta['parameters'][i]
      for key in ['name', 'type', 'length', 'size']:
        if key == 'size' and param.get(key, [1]) == param_i.get(key, [1]):
          continue
        if key in param_i and key not in param:
          msg = f"Parameter '{key}' missing in given meta for {param_i['name']}"
          raise ValueError(msg)
        if key in param and key not in param_i:
          msg = f"Parameter '{key}' in given meta not in inferred meta for {param['name']}"
          raise ValueError(msg)
        if (
          key == 'length'
          and param['type'] == 'string'
          and param[key] >= param_i[key]
        ):
          continue
        if key in param and param[key] != param_i[key]:
          msg = (f"Parameter '{key}' mismatch for {param['name']}: "
                 f"given meta has {param[key]}, inferred meta has {param_i[key]}")
          raise ValueError(msg)

  if not isinstance(meta, dict) or 'parameters' not in meta:
    raise ValueError("Meta must be a dictionary with a 'parameters' key")

  if not isinstance(meta['parameters'], list) or len(meta['parameters']) == 0:
    raise ValueError("meta['parameters'] must be a non-empty list")

  for parameter in meta['parameters']:
    if 'name' not in parameter or 'type' not in parameter:
      msg = "Each parameter in meta['parameters'] must have 'name' and 'type' keys"
      raise ValueError(msg)

    if parameter['type'] == 'isotime' and 'length' not in parameter:
      raise ValueError("Isotime parameters must have a 'length' key")

    if parameter['type'] == 'string' and 'length' not in parameter:
      raise ValueError("String parameters must have a 'length' key")

    types_known = ['string', 'integer', 'double', 'isotime']
    if parameter['type'] not in types_known:
      msg = (
              f"Unsupported parameter type: {parameter['type']} for parameter "
              f"{parameter['name']}. Supported types are: {types_known}."
      )
      raise ValueError(msg)

    if 'size' in parameter:
      if not isinstance(parameter['size'], list) or not all(isinstance(s, int) and s > 0 for s in parameter['size']):
        msg = (
                f"Parameter {parameter['name']} has invalid 'size' field. "
                "Must be a list of positive integers."
        )
        raise ValueError(msg)


  if meta['parameters'][0]['type'] != 'isotime':
    msg = "The first parameter in meta['parameters'] must be of type 'isotime'"
    raise ValueError(msg)

  time_name = meta['parameters'][0]['name']

  # Convert datetime back to HAPI ISO 8601 format using datetime2hapitime
  # Convert pandas datetime to list of Python datetime objects
  if np.issubdtype(df[time_name].dtype, np.datetime64):
    df[time_name] = datetime2hapitime(list(df[time_name].dt.to_pydatetime()))

  # Convert parameters from list of parameter dicts to dict with keys of
  # parameter name and values of parameter dicts.
  parameters = {param['name']: param for param in meta['parameters']}

  dtypes = []
  for name, parameter in parameters.items():

    if parameter['type'] in ['string', 'isotime']:
      length = parameter.get('length', None)
      if 'length' not in parameter or isinstance(length, int) is False or length <= 0:
        msg = f"Parameter {name} of type '{parameter['type']}' must have a "
        msg += "positive integer 'length' field in meta."
        raise ValueError(msg)

      if parameter['type'] == 'string':
        dtype = (name, f'U{length}')
      elif parameter['type'] == 'isotime':
        dtype = (name, f'S{length}')

    if parameter['type'] == 'integer':
      dtype = (name, 'int32')

    if parameter['type'] == 'double':
      dtype = (name, 'float64')

    # Determine the shape of the parameter from meta
    size = parameter.get('size', [])

    if len(size) == 0 or len(size) == 1 and size[0] == 1:
      # Scalar parameter
      dtypes.append(dtype)
    else:
      # Multidimensional parameter - flatten the shape for structured array
      dtypes.append((dtype[0], dtype[1], tuple(size)))

  data = np.empty(len(df), dtype=dtypes)
  for col_name in df.columns:

    if isinstance(col_name, str):
      name = col_name
      values = df[col_name].values
    else:
      # Column name is tuple of form (name, index_tuple)
      name = col_name[0]

      # Extract all columns with tuple with first element equal to name
      components = [col for col in df.columns if isinstance(col, tuple) and col[0] == name]
      values = df[components].values

      # Reshape to original shape
      values = values.reshape(len(df), *data[name].shape[1:])

    data[name] = values

  return data


def df2np_test():
  import copy

  import numpy as np
  import pandas as pd

  def assert_meta_error(meta, message):
    try:
      df2np(df.copy(), meta)
    except ValueError as exc:
      assert message in str(exc), f"Expected {message!r}, got {str(exc)!r}"
    else:
      raise AssertionError(f"Expected ValueError containing: {message}")

  # Create a sample DataFrame with time index and numeric columns
  time_index = pd.date_range(start='2023-01-01', periods=5, freq='D')
  df = pd.DataFrame({
      'time': time_index,
      'col1': np.arange(5),
      'col2': np.random.rand(5),
      'col3': ['a', 'bb', 'ccc', 'dddd', 'eeeee'],
      ('vector', (0, )): np.random.rand(5),
      ('vector', (1, )): np.random.rand(5)
  })

  meta = df_infer_meta(df)

  meta_fewer_parameters = copy.deepcopy(meta)
  meta_fewer_parameters['parameters'].pop()
  assert_meta_error(
    meta_fewer_parameters,
    "Number of parameters in meta (4) does not match inferred meta (5)",
  )

  parameter_indices = {
    parameter['name']: index
    for index, parameter in enumerate(meta['parameters'])
  }

  meta_different_name = copy.deepcopy(meta)
  meta_different_name['parameters'][parameter_indices['col1']]['name'] = 'renamed'
  assert_meta_error(
    meta_different_name,
    "Parameter names in meta (['time', 'renamed', 'col2', 'col3', 'vector']) "
    "do not match inferred meta (['time', 'col1', 'col2', 'col3', 'vector'])",
  )

  meta_different_order = copy.deepcopy(meta)
  meta_different_order['parameters'][1:3] = reversed(meta_different_order['parameters'][1:3])
  assert_meta_error(
    meta_different_order,
    "Parameter order in meta (['time', 'col2', 'col1', 'col3', 'vector']) "
    "does not match inferred meta (['time', 'col1', 'col2', 'col3', 'vector'])",
  )

  for parameter_name, key in [
    ('col1', 'type'),
    ('col3', 'length'),
    ('vector', 'size'),
  ]:
    meta_missing_key = copy.deepcopy(meta)
    del meta_missing_key['parameters'][parameter_indices[parameter_name]][key]
    assert_meta_error(
      meta_missing_key,
      f"Parameter '{key}' missing in given meta for {parameter_name}",
    )

  for key, value in [('length', 1), ('size', [2])]:
    meta_extra_key = copy.deepcopy(meta)
    meta_extra_key['parameters'][parameter_indices['col1']][key] = value
    assert_meta_error(
      meta_extra_key,
      f"Parameter '{key}' in given meta not in inferred meta for col1",
    )

  meta_scalar_size = copy.deepcopy(meta)
  meta_scalar_size['parameters'][parameter_indices['col1']]['size'] = [1]
  df2np(df.copy(), meta_scalar_size)

  for parameter_name, key, value in [
    ('col1', 'type', 'double'),
    ('col3', 'length', meta['parameters'][parameter_indices['col3']]['length'] - 1),
    ('vector', 'size', [3]),
  ]:
    meta_mismatch = copy.deepcopy(meta)
    meta_mismatch['parameters'][parameter_indices[parameter_name]][key] = value
    assert_meta_error(meta_mismatch, f"Parameter '{key}' mismatch")

  meta_padded_string = copy.deepcopy(meta)
  meta_padded_string['parameters'][parameter_indices['col3']]['length'] += 3
  df2np(df.copy(), meta_padded_string)

  meta_with_units = copy.deepcopy(meta)
  meta_with_units['parameters'][parameter_indices['col1']]['units'] = 'count'
  df2np(df.copy(), meta_with_units)

  data_np = df2np(df, meta)
  #print(repr(data_np))


def np2df(data, meta, time_format='datetime', nan_fill=False, parameters_include=None, parameters_exclude=None, name_map=None):
  """
  Convert output of hapi() to a Pandas DataFrame.

  nan_fill : bool
      For isotime parameters, and if time_format = 'datetime64', replace fill
      values with numpy.datetime64('NaT', 'us').

      For integer parameters, convert to double and replace fill values with numpy.nan.

      For double parameters, replace fill values with numpy.nan.

  parameters_include : list or None
      List of parameter names to include. If None, include all parameters.

  parameters_exclude : list or None
      List of parameter names to exclude. If None, exclude no parameters.

  name_map : dict or None
      Dictionary mapping original parameter names to new names.
      If None, no renaming is performed.
  """

  import pandas

  from hapiclient import hapitime2datetime

  dfs = []

  time_name = meta['parameters'][0]['name']
  names = [p['name'] for p in meta['parameters']]

  if parameters_include is not None and parameters_exclude is not None:
    # Check for overlap between parameters_include and parameters_exclude
    overlap = set(parameters_include) & set(parameters_exclude)
    if overlap:
      coda = "in both parameters_include and parameters_exclude"
      if len(overlap) == 1:
        msg = f"Parameter '{overlap.pop()}' is {coda}"
      else:
        msg = f"Parameters {list(overlap)} are {coda}"
      raise ValueError(msg)

  if parameters_include is not None:
    for name_include in parameters_include:
      # If parameter in parameters_include but not in meta['parameters'], raise error
      if name_include not in names:
        msg = f"Parameter '{name_include}' in parameters_include is not one of {names}"
        raise ValueError(msg)
    if time_name not in parameters_include:
      parameters_include = parameters_include.copy()
      # Always include time parameter
      parameters_include.append(time_name)

  if parameters_exclude is not None:
    for name_exclude in parameters_exclude:
      if name_exclude not in names:
        # If parameter name in parameters_exclude but not in meta['parameters']
        msg = f"Parameter '{name_exclude}' in parameters_exclude is not one of {names}"
        raise ValueError(msg)

  if name_map is not None:
    for name in name_map:
      msg_o = f"Name {name} in name_map does not match a"
      if parameters_include is not None and name not in parameters_include:
        msg = f"{msg_o} name in parameters_include ({parameters_include})"
        raise ValueError(msg)
      elif name not in names:
        msg = f"{msg_o} parameter name ({names})"
        raise ValueError(msg)

  for parameter in meta['parameters']:
    name = parameter['name']

    if parameters_include is not None:
      # only include parameters in parameters_include
      if name not in parameters_include:
        continue
    if parameters_exclude is not None:
      # exclude parameters in parameters_exclude
      if name in parameters_exclude:
        continue

    if name == time_name:
      # Convert primary time parameter to datetime or datetime64
      if time_format in ['datetime', 'datetime64']:
        df_time = pandas.DataFrame({name: hapitime2datetime(data[name])})
        if time_format == 'datetime64':
          df_time[name] = df_time[name].astype('datetime64[ns]')
      else:
        df_time = pandas.DataFrame({name: data[name]})
      dfs.append(df_time)
    else:
      param_data = data[name]

      fill = parameter.get('fill')
      if nan_fill and fill is not None:
        # Convert fill values to NaN or NaT as appropriate for the parameter type
        param_data = _nan_fill(param_data, parameter['type'], fill)

      # size is shape excluding the first dimension (time)
      size = param_data.shape[1:]
      col_names = _df_col_names(name, size)

      # flatten all but first dimension (time)
      data_flat = param_data.reshape(param_data.shape[0], -1)

      df_data = pandas.DataFrame(data_flat, columns=col_names)

      dfs.append(df_data)

  df = pandas.concat(dfs, axis=1)

  _df_rename_columns(df, time_name, name_map)

  return df


def df_columns(df, parameter, include_time=True):
  """Subset a DataFrame to have only the primary time column and a parameter."""

  if parameter not in df.columns and not any(
    isinstance(col, tuple) and col[0] == parameter for col in df.columns
  ):
    raise KeyError(f"Parameter '{parameter}' not found in DataFrame columns.")

  time_column = df.columns[0]
  if isinstance(time_column, tuple):
    raise ValueError("First column of DataFrame must be the primary time parameter, which must be scalar.")

  subset_columns = []
  if include_time:
    subset_columns.append(time_column)
  if parameter in df.columns:
    subset_columns.append(parameter)
  else:
    subset_columns.extend(col for col in df.columns if isinstance(col, tuple) and col[0] == parameter)

  return subset_columns


def df_infer_meta(df):
  """Infer HAPI parameter metadata from a pandas DataFrame.

  Returns a dictionary with a 'parameters' key containing a list of parameter
  metadata dictionaries. The parameter dictionaries contain 'name', 'type', and
  and, if appropriate, 'length' and 'size' keys.

  The first column must be a scalar primary time parameter represented by
  datetime values or strings or UTF-8 bytes that parse as HAPI time. The
  primary time column cannot contain missing values.

  Integer columns must fit in int32. Floating-point columns infer as double,
  and Boolean columns are not supported.

  String length is the maximum UTF-8 encoded byte length in the column. Text
  that looks like HAPI time must parse as HAPI time and then infers as isotime.
  Datetime columns infer as isotime with length 24.

  Indexed parameters use canonical, complete, zero-based tuple labels. For
  example, columns ('vector', (0,)) and ('vector', (1,)) infer size [2].
  """
  import datetime

  import numpy as np
  import pandas as pd

  from hapiclient import hapitime2datetime

  if not isinstance(df, pd.DataFrame):
    raise ValueError(f"Input must be a pandas DataFrame, got {type(df)}")

  if df.empty:
    raise ValueError("Input DataFrame is empty")

  primary_time_values = df.iloc[:, 0]
  if primary_time_values.isna().any():
    raise ValueError("Primary time column cannot contain missing values.")

  def infer_type(values, name):
    dtype = values.dtype

    if pd.api.types.is_bool_dtype(dtype):
      raise ValueError(f"Boolean column '{name}' is not supported.")

    if pd.api.types.is_datetime64_any_dtype(dtype):
      return {'name': name, 'type': 'isotime', 'length': 24}

    if pd.api.types.is_integer_dtype(dtype):
      if values.dropna().empty:
        return {'name': name, 'type': 'integer'}
      values_min = values.min()
      values_max = values.max()
      limits = np.iinfo(np.int32)
      if values_min < limits.min or values_max > limits.max:
        msg = (f"Integer column '{name}' cannot be represented as int32 (HAPI "
               "only supports int32 b/c JSON only supports 32-bit integers).")
        raise ValueError(msg)
      return {'name': name, 'type': 'integer'}

    if pd.api.types.is_float_dtype(dtype):
      return {'name': name, 'type': 'double'}

    non_null = values.dropna()
    if non_null.empty:
      raise ValueError(f"Cannot determine length because column '{name}' contains only null values.")

    first_value = non_null.iloc[0]
    if isinstance(first_value, (datetime.datetime, np.datetime64)):
      if not all(type(value) is type(first_value) for value in non_null):
        raise ValueError(f"Column '{name}' has mixed object value types.")
      return {'name': name, 'type': 'isotime', 'length': 24}

    if not isinstance(first_value, (str, bytes, np.bytes_)):
      msg = (f"Unsupported values in column '{name}': expected numeric, "
             "datetime, bytes, or string values.")
      raise ValueError(msg)

    if pd.api.types.infer_dtype(non_null, skipna=True) not in {'string', 'bytes', 'unicode'}:
      raise ValueError(f"Column '{name}' has mixed object value types.")

    if isinstance(first_value, (bytes, np.bytes_)):
      try:
        strings = non_null.str.decode('utf-8')
      except UnicodeDecodeError as e:
        raise ValueError(f"Column '{name}' contains invalid UTF-8 bytes: {e}") from e
    else:
      strings = non_null
    length = int(strings.str.encode('utf-8').str.len().max())
    if length == 0:
      raise ValueError(f"Cannot determine length because column '{name}' contains only empty strings.")
    hapi_time = strings.str.match(r'^\d{4}-(?:\d{2}|\d{3})(?:-|T|Z)').all()
    if hapi_time:
      try:
        hapitime2datetime(strings.tolist())
        return {'name': name, 'type': 'isotime', 'length': length}
      except Exception as e:
        raise ValueError(f"Column '{name}' looks like HAPI time but cannot be parsed: {e}")

    return {'name': name, 'type': 'string', 'length': length}

  def infer_component_parameters(values, name):
    component_parameters = []
    deferred_components = []
    for index in range(values.shape[1]):
      component = values.iloc[:, index]
      dtype = component.dtype
      dtype_determines_type = (
        pd.api.types.is_bool_dtype(dtype)
        or pd.api.types.is_datetime64_any_dtype(dtype)
        or pd.api.types.is_integer_dtype(dtype)
        or pd.api.types.is_float_dtype(dtype)
      )
      if component.dropna().empty and not dtype_determines_type:
        component_parameters.append(None)
        deferred_components.append(index)
      else:
        component_parameters.append(infer_type(component, name))

    if not deferred_components:
      return component_parameters

    inferred_component = next(
      (component for component in component_parameters if component is not None),
      None,
    )
    if inferred_component is None:
      return [
        infer_type(values.iloc[:, index], name)
        for index in range(values.shape[1])
      ]

    for index in deferred_components:
      component_parameters[index] = inferred_component.copy()
      if 'length' in component_parameters[index]:
        component_parameters[index]['length'] = 0

    return component_parameters

  def group_columns():
    groups = {}
    for column in df.columns:
      if isinstance(column, str):
        name = column
        indices = None
      elif (
        isinstance(column, tuple)
        and len(column) == 2
        and isinstance(column[0], str)
        and isinstance(column[1], tuple)
        and len(column[1]) > 0
        and all(isinstance(index, int) and not isinstance(index, bool) and index >= 0 for index in column[1])
      ):
        name = column[0]
        indices = column[1]
      else:
        raise ValueError(f"Unsupported DataFrame column name: {column!r}")

      if name in groups and indices is None and any(index is None for _, index in groups[name]):
        raise ValueError(f"Column name {name!r} appears more than once.")
      if name not in groups:
        groups[name] = []
      groups[name].append((column, indices))
    return groups

  groups = group_columns()
  parameters = []
  for name, columns in groups.items():

    indices = [index for _, index in columns]
    if any(index is None for index in indices) and any(index is not None for index in indices):
      raise ValueError(f"'{name}' is the name of a scalar and set of indexed columns.")
    if indices == [(0,)]:
      raise ValueError(f"Use scalar column name {name!r} instead of {columns[0][0]!r}.")

    values = df[[column for column, _ in columns]]
    if any(values.iloc[:, index].dtype != values.iloc[:, 0].dtype for index in range(1, values.shape[1])):
      raise ValueError(f"Parameter '{name}' has columns with different dtypes.")

    component_parameters = infer_component_parameters(values, name)
    parameter = component_parameters[0]
    if any(component['type'] != parameter['type'] for component in component_parameters[1:]):
      raise ValueError(f"Parameter '{name}' has columns with different inferred types.")

    if parameter['type'] == 'isotime':
      datetime_types = {
        type(non_null.iloc[0])
        for index in range(values.shape[1])
        if not (non_null := values.iloc[:, index].dropna()).empty
        and isinstance(non_null.iloc[0], (datetime.datetime, np.datetime64))
      }
      if len(datetime_types) > 1:
        raise ValueError(f"Parameter '{name}' mixes datetime representations.")
      string_kinds = {
        inferred_dtype
        for index in range(values.shape[1])
        if (
          inferred_dtype := pd.api.types.infer_dtype(
            values.iloc[:, index].dropna(),
            skipna=True,
          )
        ) in {'string', 'bytes', 'unicode'}
      }
      if datetime_types and string_kinds:
        raise ValueError(f"Parameter '{name}' mixes datetime and string representations.")

    if parameter['type'] in ['string', 'isotime']:
      component_kinds = [
        'bytes' if pd.api.types.infer_dtype(values.iloc[:, index].dropna(), skipna=True) == 'bytes' else 'text'
        for index in range(values.shape[1])
        if not values.iloc[:, index].dropna().empty
      ]
      if len(set(component_kinds)) > 1:
        raise ValueError(f"Parameter '{name}' mixes text and byte string components.")

    if 'length' in parameter:
      parameter['length'] = max(component['length'] for component in component_parameters)

    if indices[0] is not None:
      dimensions = len(indices[0])
      if any(len(index) != dimensions for index in indices):
        raise ValueError(f"Parameter '{name}' has inconsistent index dimensions.")

      size = [max(index[dimension] for index in indices) + 1 for dimension in range(dimensions)]
      if 1 in size:
        raise ValueError(f"Parameter '{name}' has invalid size {size}; dimensions must be greater than 1.")
      expected_columns = _df_col_names(name, size)
      actual_columns = [column for column, _ in columns]
      if actual_columns != expected_columns:
        msg = f"Parameter '{name}' columns must form a complete grid in canonical order."
        msg += f"\nOrder given: {actual_columns}"
        msg += f"\nOrder required: {expected_columns}"
        raise ValueError(msg)
      parameter['size'] = size

    parameters.append(parameter)

  if isinstance(df.columns[0], tuple):
    raise ValueError("First column of DataFrame must be the primary time parameter, which must be scalar.")
  if parameters[0]['type'] != 'isotime':
    raise ValueError("The first DataFrame column must be of type that resolves to an isotime parameter.")

  return {'parameters': parameters}


def np2df_name_map_test():

  data, meta = _sample()

  name_map = {param['name']: f"{param['name']}_new" for param in meta['parameters']}
  df = np2df(data, meta, name_map=name_map)
  df_names = _df_parameter_names(df)
  for name in df_names:
    assert name in name_map.values(), f"Expected {name} to be in name_map values {name_map.values()}"

  df = np2df(data, meta, name_map={'scalar': 'scalar_new'})
  data_names = data.dtype.names
  df_names = _df_parameter_names(df)
  diff = set(data_names) - set(df_names)

  assert len(diff) == 1 and 'scalar' in diff, f"Expected 'scalar' to be the only differing column name, got {diff}"
  assert len(df_names) == len(data_names), f"Expected {len(data_names)} columns, got {len(df_names)}"
  assert 'scalar_new' in df_names, "Expected 'scalar_new' to be in DataFrame column names"


def np2df_include_exclude_test():

  data, meta = _sample()

  df = np2df(data, meta, parameters_include=['Time', 'scalar'])
  assert len(df.columns) == 2, f"Expected 2 columns, got {len(df.columns)}"
  assert 'Time' in df.columns, "Expected 'Time' column in DataFrame"
  assert 'scalar' in df.columns, "Expected 'scalar' column in DataFrame"

  df = np2df(data, meta, parameters_exclude=['Time', 'scalar'])
  assert 'Time' not in df.columns, "Expected 'Time' column to be excluded from DataFrame"
  assert 'scalar' not in df.columns, "Expected 'scalar' column to be excluded from DataFrame"
  np_names = data.dtype.names
  df_names = _df_parameter_names(df)
  if len(df_names) != len(np_names) - 2:
    raise AssertionError(f"Expected {len(np_names) - 2} columns, got {len(df_names)}")

  try:
    df = np2df(data, meta, parameters_include=['scalar'], parameters_exclude=['Time', 'scalar'])
  except ValueError as e:
    assert "Parameter 'scalar' is in both parameters_include and parameters_exclude" in str(e), f"Unexpected error message: {e}"

  try:
    df = np2df(data, meta, parameters_include=['INVALID'])
  except ValueError as e:
    assert "Parameter 'INVALID' in parameters_include is not one of" in str(e), f"Unexpected error message: {e}"

  try:
    df = np2df(data, meta, parameters_exclude=['INVALID'])
  except ValueError as e:
    assert "Parameter 'INVALID' in parameters_exclude is not one of" in str(e), f"Unexpected error message: {e}"


def np2df_testdata_test(versions=None):
  """Convert all TestData responses to DataFrame and back to NumPy array."""

  from hapiclient import hapi

  if versions is None:
    versions = ['2.0', '2.1', '3.0', '3.1', '3.2', '3.3']

  for version in versions:
    server = f'http://hapi-server.org/servers/TestData{version}/hapi'
    datasets = [entry['id'] for entry in hapi(server)['catalog']]

    for dataset in datasets:
      print(f'Testing TestData{version}, {dataset}')

      info = hapi(server, dataset)
      start  = '1970-01-01Z'
      stop   = '1970-01-01T00:00:11Z'
      if version == '3.2':
        start  = hapi(server,dataset)['startDate']
        stop   = hapi(server,dataset)['stopDate']

      # Check conversion of all parameters
      data_orig, meta = hapi(server, dataset, '', start, stop)
      df = np2df(data_orig, meta, time_format=None)
      data_conv = df2np(df, meta)
      _compare_np_arrays(data_orig, data_conv)

      # Check conversion of each parameter individually
      for parameter in info['parameters']:
        print(f"Testing TestData{version}, {dataset}, {parameter['name']}")

        data_orig, meta = hapi(server, dataset, parameter['name'], start, stop)

        df = np2df(data_orig, meta, time_format=None)

        data_conv = df2np(df, meta)

        _compare_np_arrays(data_orig, data_conv)


def df_infer_meta_test():
  import datetime

  import numpy as np
  import pandas as pd

  def assert_value_error(value, message):
    try:
      df_infer_meta(value)
    except ValueError as exc:
      assert message in str(exc)
    else:
      raise AssertionError(f"Expected ValueError containing: {message}")

  # Input validation
  assert_value_error(
    [],
    "Input must be a pandas DataFrame"
  )
  assert_value_error(
    pd.DataFrame(),
    "Input DataFrame is empty"
  )

  # Empty and unsupported scalar values
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      'empty': [None, None],
    }),
    "Cannot determine length because column 'empty' contains only null values."
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      'empty_string': pd.Series([pd.NA, pd.NA], dtype='string'),
    }),
    "Cannot determine length because column 'empty_string' contains only null values.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      'empty_text': ['', ''],
    }),
    "Cannot determine length because column 'empty_text' contains only empty strings.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      'empty_bytes': [b'', b''],
    }),
    "Cannot determine length because column 'empty_bytes' contains only empty strings.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      'empty_boolean': pd.Series([pd.NA, pd.NA], dtype='boolean'),
    }),
    "Boolean column 'empty_boolean' is not supported.",
  )

  # Column label and parameter grouping validation
  invalid_names = [
    1,
    ('name',),
    ('name', ()),
    (1, (0,)),
    ('name', 0),
    ('name', (-1,)),
    ('name', (0, 'a')),
    ('name', (True,)),
    ('name', (np.int64(0),)),
  ]
  for name in invalid_names:
    assert_value_error(
      pd.DataFrame([1], columns=[name]),
      f"Unsupported DataFrame column name: {name!r}"
    )

  assert_value_error(
    pd.DataFrame({
      'collision': [1.0, 2.0],
      ('collision', (0,)): [3.0, 4.0],
      ('collision', (1,)): [5.0, 6.0]
    }),
    "'collision' is the name of a scalar and set of indexed columns.",
  )
  assert_value_error(
    pd.DataFrame(
      [
        ['2023-01-01T00:00:00Z', 1.0, 2.0],
        ['2023-01-01T00:00:01Z', 3.0, 4.0],
      ],
      columns=pd.Index(['Time', 'duplicate_scalar', 'duplicate_scalar'], dtype=object),
    ),
      "Column name 'duplicate_scalar' appears more than once.",
  )
  assert_value_error(
    pd.DataFrame([1], columns=[('value', (0,))]),
    "Use scalar column name 'value' instead of ('value', (0,))."
  )

  # Scalar mixed-type and unsupported-value validation
  assert_value_error(
    pd.DataFrame({'mixed': ['text', 1]}),
    "Column 'mixed' has mixed object value types.",
  )
  assert_value_error(
    pd.DataFrame({'mixed_text_bytes': ['text', b'bytes']}),
    "Column 'mixed_text_bytes' has mixed object value types.",
  )
  assert_value_error(
    pd.DataFrame({'unsupported': [object()]}),
    "Unsupported values in column 'unsupported'",
  )
  assert_value_error(
    pd.DataFrame({'Time': ['2023-01-01T00:00:00Z'], 'flag': [True]}),
    "Boolean column 'flag' is not supported.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      'nullable_flag': pd.Series([True, pd.NA], dtype='boolean'),
    }),
    "Boolean column 'nullable_flag' is not supported.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z'],
      'complex': np.array([1 + 2j], dtype=np.complex128),
    }),
    "Unsupported values in column 'complex'",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': [
        '2023-01-01T00:00:00Z',
        '2023-01-01T00:00:01Z',
      ],
      'mixed_datetime': pd.Series([
        datetime.datetime(2023, 1, 1),
        'not a datetime',
      ], dtype=object),
    }),
    "Column 'mixed_datetime' has mixed object value types.",
  )
  # Primary time position and scalar requirements
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      'mixed_datetime_representations': pd.Series([
        datetime.datetime(2023, 1, 1),
        np.datetime64('2023-01-02T00:00:00'),
      ], dtype=object),
    }),
    "Column 'mixed_datetime_representations' has mixed object value types.",
  )

  assert_value_error(
    pd.DataFrame({
      'value': [1.0, 2.0],
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    }),
    "The first DataFrame column must be of type that resolves to an isotime parameter.",
  )
  assert_value_error(
    pd.DataFrame({'value': [1.0, 2.0]}),
    "The first DataFrame column must be of type that resolves to an isotime parameter.",
  )
  assert_value_error(
    pd.DataFrame({'label': ['not a time', 'still not a time']}),
    "The first DataFrame column must be of type that resolves to an isotime parameter.",
  )
  assert_value_error(
    pd.DataFrame(
      [
        ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
        ['2023-01-01T00:00:02Z', '2023-01-01T00:00:03Z'],
      ],
      columns=pd.Index([('Time', (0,)), ('Time', (1,))], dtype=object),
    ),
    "First column of DataFrame must be the primary time parameter, which must be scalar.",
  )

  # Indexed component type and representation consistency
  assert_value_error(
    pd.DataFrame({
      ('mixed_dtype', (0,)): np.array([1.0, 2.0], dtype=np.float64),
      ('mixed_dtype', (1,)): np.array([3, 4], dtype=np.int32),
    }),
    "Parameter 'mixed_dtype' has columns with different dtypes.",
  )
  assert_value_error(
    pd.DataFrame({
      ('mixed_object', (0,)): pd.Series(['text', 'more'], dtype=object),
      ('mixed_object', (1,)): pd.Series([
        datetime.datetime(2023, 1, 1),
        datetime.datetime(2023, 1, 2),
      ], dtype=object),
    }),
    "Parameter 'mixed_object' has columns with different inferred types.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      ('mixed_datetime_components', (0,)): pd.Series([
        datetime.datetime(2023, 1, 1),
        datetime.datetime(2023, 1, 2),
      ], dtype=object),
      ('mixed_datetime_components', (1,)): pd.Series([
        np.datetime64('2023-01-03T00:00:00'),
        np.datetime64('2023-01-04T00:00:00'),
      ], dtype=object),
    }),
    "Parameter 'mixed_datetime_components' mixes datetime representations.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      ('mixed_datetime_text_components', (0,)): pd.Series([
        datetime.datetime(2023, 1, 1),
        datetime.datetime(2023, 1, 2),
      ], dtype=object),
      ('mixed_datetime_text_components', (1,)): pd.Series([
        '2023-01-03T00:00:00Z',
        '2023-01-04T00:00:00Z',
      ], dtype=object),
    }),
    "Parameter 'mixed_datetime_text_components' mixes datetime and string representations.",
  )

  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      ('mixed_strings', (0,)): pd.Series(['text', 'more'], dtype=object),
      ('mixed_strings', (1,)): [b'bytes', b'more'],
    }),
    "Parameter 'mixed_strings' mixes text and byte string components.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      ('mixed_time_strings', (0,)): pd.Series([
        '2023-01-02T00:00:00Z',
        '2023-01-02T00:00:01Z',
      ], dtype=object),
      ('mixed_time_strings', (1,)): pd.Series([
        b'2023-01-03T00:00:00Z',
        b'2023-01-03T00:00:01Z',
      ], dtype=object),
    }),
    "Parameter 'mixed_time_strings' mixes text and byte string components.",
  )

  # Integer bounds and unsigned integer inference
  int32 = np.iinfo(np.int32)
  df = pd.DataFrame({
        'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
        'bounds': np.array([int32.min, int32.max], dtype=np.int64),
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'bounds', 'type': 'integer'},
    ]
  }
  assert_value_error(
    pd.DataFrame({'overflow': [int32.min - 1]}),
    "Integer column 'overflow' cannot be represented as int32",
  )
  assert_value_error(
    pd.DataFrame({'overflow': [int32.max + 1]}),
    "Integer column 'overflow' cannot be represented as int32",
  )

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'unsigned_bounds': np.array([0, int32.max], dtype=np.uint64),
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'unsigned_bounds', 'type': 'integer'},
    ]
  }
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z'],
      'unsigned_overflow': np.array([int32.max + 1], dtype=np.uint64),
    }),
    "Integer column 'unsigned_overflow' cannot be represented as int32",
  )

  # Primary time formats, parsing, and missing values
  df = pd.DataFrame({
    'Time': [b'2023-01-01T00:00:00Z', np.bytes_('2023-01-01T00:00:01Z')]
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
    ]
  }

  df = pd.DataFrame({'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z']})
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
    ]
  }

  assert_value_error(
    pd.DataFrame({'Time': pd.Series([pd.NaT, pd.NaT], dtype='datetime64[ns]')}),
    "Primary time column cannot contain missing values.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': pd.Series([
        np.datetime64('NaT'),
        np.datetime64('2023-01-01T00:00:00'),
      ], dtype=object),
    }),
    "Primary time column cannot contain missing values.",
  )
  assert_value_error(
    pd.DataFrame({'Time': pd.to_datetime(['2023-01-01T00:00:00Z', pd.NaT])}),
    "Primary time column cannot contain missing values.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': pd.Series([
        datetime.datetime(2023, 1, 1),
        None,
      ], dtype=object),
    }),
    "Primary time column cannot contain missing values.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': pd.Series(['2023-01-01T00:00:00Z', pd.NA], dtype='string'),
    }),
    "Primary time column cannot contain missing values.",
  )

  assert_value_error(
    pd.DataFrame({'Time': ['2023-13-01T00:00:00Z']}),
    "Column 'Time' looks like HAPI time but cannot be parsed:",
  )
  assert_value_error(
    pd.DataFrame({'Time': ['2023-01-01T00:00:00', '2023-01-01T00:00:01']}),
    "HAPI Times must have trailing Z.",
  )

  df = pd.DataFrame({'Time': ['2023-001T00:00:00Z', '2023-002T00:00:01Z']})
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 18},
    ]
  }

  df = pd.DataFrame({
    'Time': pd.Series([
      datetime.datetime(2023, 1, 1),
      datetime.datetime(2023, 1, 2),
    ], dtype=object)
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 24},
    ]
  }

  df = pd.DataFrame({
    'Time': pd.Series([
      np.datetime64('2023-01-01T00:00:00'),
      np.datetime64('2023-01-02T00:00:00'),
    ], dtype=object)
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 24},
    ]
  }

  # Scalar type inference and nullable values
  df = pd.DataFrame({
    'Time': pd.Series(
      [
        datetime.datetime(2023, 1, 1),
        datetime.datetime(2023, 1, 2),
        datetime.datetime(2023, 1, 3),
      ],
      dtype=object
    ),
    'count': pd.Series([1, pd.NA, 2], dtype='Int64'),
    'value': pd.Series([1.5, pd.NA, 2.5], dtype='Float64'),
    'label': pd.Series(['short', pd.NA, 'longer'], dtype='string'),
    'bytes': [b'a', None, np.bytes_(b'bytes')],
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 24},
      {'name': 'count', 'type': 'integer'},
      {'name': 'value', 'type': 'double'},
      {'name': 'label', 'type': 'string', 'length': 6},
      {'name': 'bytes', 'type': 'string', 'length': 5},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'secondary_datetime': pd.Series([
      datetime.datetime(2023, 1, 1), None,
    ], dtype=object),
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'secondary_datetime', 'type': 'isotime', 'length': 24},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'all_nan': np.array([np.nan, np.nan], dtype=np.float64),
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'all_nan', 'type': 'double'},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'all_null_integer': pd.Series([pd.NA, pd.NA], dtype='Int64'),
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'all_null_integer', 'type': 'integer'},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'all_null_float': pd.Series([pd.NA, pd.NA], dtype='Float64'),
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'all_null_float', 'type': 'double'},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'all_nat_datetime': pd.Series([pd.NaT, pd.NaT], dtype='datetime64[ns]'),
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'all_nat_datetime', 'type': 'isotime', 'length': 24},
    ]
  }

  # String, byte, UTF-8, and secondary isotime inference
  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'label': [b'a', np.bytes_(b'longer')],
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'label', 'type': 'string', 'length': 6},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'event_time': ['2023-01-02T00:00:00Z', '2023-01-02T00:00:01Z'],
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'event_time', 'type': 'isotime', 'length': 20},
    ]
  }

  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z'],
      'invalid_event_time': ['2023-13-01T00:00:00Z'],
    }),
    "Column 'invalid_event_time' looks like HAPI time but cannot be parsed:",
  )

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'nullable_text_time': pd.Series(['2023-01-02T00:00:00Z', pd.NA], dtype='string'),
    'nullable_byte_time': [b'2023-01-03T00:00:00Z', None],
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'nullable_text_time', 'type': 'isotime', 'length': 20},
      {'name': 'nullable_byte_time', 'type': 'isotime', 'length': 20},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'mixed_time_text': ['2023-01-01T00:00:00Z', 'ordinary text'],
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'mixed_time_text', 'type': 'string', 'length': 20},
    ]
  }

  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z'],
      'invalid_utf8': [b'\xff'],
    }),
    "Column 'invalid_utf8' contains invalid UTF-8 bytes:",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      'later_invalid_utf8': [b'valid', b'\xff'],
    }),
    "Column 'later_invalid_utf8' contains invalid UTF-8 bytes:",
  )

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'utf8_label': ['\u00e9', '\U0001F600'], # First has two bytes in UTF-8, second has four bytes in UTF-8
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'utf8_label', 'type': 'string', 'length': 4},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    'utf8_bytes': [b'\xc3\xa9', b'\xf0\x9f\x98\x80'],
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'utf8_bytes', 'type': 'string', 'length': 4},
    ]
  }

  # Successful indexed parameter inference
  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    ('labels', (0,)): ['a', 'bb'],
    ('labels', (1,)): ['longer', 'wide'],
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'labels', 'type': 'string', 'length': 6, 'size': [2]},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    ('nullable_labels', (0,)): pd.Series(['a', pd.NA], dtype='string'),
    ('nullable_labels', (1,)): pd.Series(['longer', 'bb'], dtype='string'),
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'nullable_labels', 'type': 'string', 'length': 6, 'size': [2]},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    ('labels_with_empty_component', (0,)): pd.Series([pd.NA, pd.NA], dtype='string'),
    ('labels_with_empty_component', (1,)): pd.Series(['longer', 'bb'], dtype='string'),
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'labels_with_empty_component', 'type': 'string', 'length': 6, 'size': [2]},
    ]
  }
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      ('all_null_labels', (0,)): pd.Series([pd.NA, pd.NA], dtype='string'),
      ('all_null_labels', (1,)): pd.Series([pd.NA, pd.NA], dtype='string'),
    }),
    "Cannot determine length because column 'all_null_labels' contains only null values.",
  )

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    ('byte_labels', (0,)): [b'a', b'four'],
    ('byte_labels', (1,)): [b'three', b'bb'],
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'byte_labels', 'type': 'string', 'length': 5, 'size': [2]},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    ('counts', (0,)): pd.Series([1, pd.NA], dtype='Int64'),
    ('counts', (1,)): pd.Series([2, 3], dtype='Int64'),
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'counts', 'type': 'integer', 'size': [2]},
    ]
  }

  df = pd.DataFrame({
    'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
    ('event_times', (0,)): ['2023-001T00:00:00Z', '2023-002T00:00:01Z'],
    ('event_times', (1,)): ['2023-01-03T00:00:00Z', '2023-01-04T00:00:01Z'],
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'event_times', 'type': 'isotime', 'length': 20, 'size': [2]},
    ]
  }

  # Indexed shape, completeness, and canonical ordering validation
  sparse_vector = pd.DataFrame({
    ('sparse_vector', (2,)): [1.0, 2.0],
    ('sparse_vector', (5,)): [3.0, 4.0],
  })
  assert_value_error(
    sparse_vector,
    "Parameter 'sparse_vector' columns must form a complete grid in canonical order.",
  )
  missing_component_vector = pd.DataFrame({
    ('vector', (0,)): [1.0, 2.0],
    ('vector', (2,)): [3.0, 4.0],
  })
  assert_value_error(
    missing_component_vector,
    "Parameter 'vector' columns must form a complete grid in canonical order.",
  )
  duplicate_component = pd.DataFrame(
    [
      ['2023-01-01T00:00:00Z', 1.0, 2.0, 3.0],
      ['2023-01-01T00:00:01Z', 4.0, 5.0, 6.0],
    ],
    columns=pd.Index([
      'Time', ('duplicate', (0,)), ('duplicate', (0,)), ('duplicate', (1,)),
    ], dtype=object),
  )
  assert_value_error(
    duplicate_component,
    "Parameter 'duplicate' columns must form a complete grid in canonical order.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      ('inconsistent', (0,)): [1.0, 2.0],
      ('inconsistent', (0, 0)): [3.0, 4.0],
    }),
    "Parameter 'inconsistent' has inconsistent index dimensions.",
  )
  assert_value_error(
    pd.DataFrame({
      'Time': ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'],
      ('singleton_dimension', (0, 0)): [1.0, 2.0],
      ('singleton_dimension', (0, 1)): [3.0, 4.0],
    }),
    "Parameter 'singleton_dimension' has invalid size [1, 2]; dimensions must be greater than 1.",
  )

  matrix_columns = _df_col_names('matrix', (3, 4))
  matrix = pd.DataFrame({
    column: [float(index), float(index + 1)]
    for index, column in enumerate(matrix_columns)
  })
  matrix.insert(0, 'Time', ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'])
  matrix.columns = pd.Index(['Time', *matrix_columns], dtype=object)
  assert df_infer_meta(matrix) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'matrix', 'type': 'double', 'size': [3, 4]},
    ]
  }
  assert_value_error(
    matrix.loc[:, matrix_columns[::-1]],
    "Parameter 'matrix' columns must form a complete grid in canonical order.",
  )

  cube_columns = _df_col_names('cube', (2, 2, 2))
  cube = pd.DataFrame({
    column: [float(index), float(index + 1)]
    for index, column in enumerate(cube_columns)
  })
  cube.insert(0, 'Time', ['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z'])
  cube.columns = pd.Index(['Time', *cube_columns], dtype=object)
  assert df_infer_meta(cube) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 20},
      {'name': 'cube', 'type': 'double', 'size': [2, 2, 2]},
    ]
  }

  # Integrated metadata inference
  df = pd.DataFrame({
    'Time': pd.to_datetime(['2023-01-01T00:00:00Z', '2023-01-01T00:00:01Z']),
    'count': [1, 2],
    'value': [1.5, 2.5],
    'label': ['a', 'long'],
    ('vector', (0,)): [3.0, 4.0],
    ('vector', (1,)): [5.0, 6.0],
  })
  assert df_infer_meta(df) == {
    'parameters': [
      {'name': 'Time', 'type': 'isotime', 'length': 24},
      {'name': 'count', 'type': 'integer'},
      {'name': 'value', 'type': 'double'},
      {'name': 'label', 'type': 'string', 'length': 4},
      {'name': 'vector', 'type': 'double', 'size': [2]},
    ]
  }

  meta = df_infer_meta(df)
  assert meta['parameters'][0]['type'] == 'isotime'
  assert meta['parameters'][1]['type'] == 'integer'
  assert meta['parameters'][2]['type'] == 'double'
  assert meta['parameters'][3]['type'] == 'string'
  assert meta['parameters'][4]['type'] == 'double'
  assert df[df_columns(df, 'vector')].shape == (2, 3)  # Time + vector components
  assert df[df_columns(df, 'vector')].columns.tolist() == ['Time', ('vector', (0,)), ('vector', (1,))]


def df_infer_meta_testdata_test():
  import pandas as pd
  samples = _samples()
  for version, dataset in samples:
    data, meta = samples[(version, dataset)]
    df = np2df(data, meta)
    meta_i = df_infer_meta(df)
    assert len(meta_i['parameters']) == len(meta['parameters'])
    for parameter_i, parameter in zip(meta_i['parameters'], meta['parameters']):
      print(version, dataset, parameter['name'])
      assert parameter_i['name'] == parameter['name']
      assert parameter_i['type'] == parameter['type']

      if 'length' in parameter:
        assert 'length' in parameter_i
        if parameter['type'] == 'isotime':
          # df time like columns are always converted to isotime with length 24
          # (microsecond precision).
          if parameter['length'] <= 24:
            assert parameter_i['length'] >= parameter['length']
            # Check that when converted to datetime, values are the same.
            time_i = pd.to_datetime(df[df_columns(df, parameter_i['name'])].to_numpy().ravel(), utc=True, errors='coerce')
            time = pd.to_datetime(df[df_columns(df, parameter['name'])].to_numpy().ravel(), utc=True, errors='coerce')
            assert time_i.equals(time)
        elif parameter['type'] == 'string':
          assert parameter_i['length'] <= parameter['length']
        else:
          assert parameter_i['length'] == parameter['length']

      if 'size' in parameter_i:
        assert 'size' in parameter
      if 'size' in parameter and parameter['size'] != [1]:
        assert 'size' in parameter_i
        assert parameter_i['size'] == parameter['size']


def _df_rename_columns(df, time_name, name_map):
  """Rename columns of the DataFrame according to name_map.

  For columns with index subscripts, only rename the first element of the column name
  # tuple (parameter name), not the second level (column index or indices).

  Parameters
  ----------
  df : pandas.DataFrame
      The DataFrame whose columns are to be renamed.
  time_name : str
      The name of the primary time column.
  name_map : dict
      A dictionary mapping old column names to new column names.
  """

  if name_map is None:
    return

  col_names = df.columns
  col_names_new = []
  for col in col_names:
    if isinstance(col, tuple):
      col_new = (name_map.get(col[0], col[0]),) + col[1:]
    else:
      col_new = name_map.get(col, col)
    col_names_new.append(col_new)

  df.columns = col_names_new
  df.rename(columns=dict(zip(col_names, col_names_new)), inplace=True)

  if time_name in name_map:
    df.index.rename(name_map[time_name], inplace=True)


def _df_col_names(name, size):
  import itertools

  if len(size) == 0 or (len(size) == 1 and size[0] == 1):
    col_names = [name]
  else:
    # Create hierarchical column index: param name at top level, then indices
    # E.g., for parameter named "mag" with shape = 3:
    #
    # ('mag', (0,)), ('mag', (1,)), ('mag', (2,))
    #
    # and for 2D parameter "matrix" with shape = (3, 3):
    #
    # ('matrix', (0, 0)), ('matrix', (0, 1)), ('matrix', (0, 2)),
    # ('matrix', (1, 0)), ('matrix', (1, 1)), ('matrix', (1, 2)),
    # ('matrix', (2, 0)), ('matrix', (2, 1)), ('matrix', (2, 2)),

    # Generate all index combinations for given size. For example,
    # if size = (3, 3), components = [range(3), range(3)]
    components = [range(size[i]) for i in range(len(size))]

    # Expand to all combinations of indices
    index_tuples = list(itertools.product(*components))

    # Create column names as (param_name, index_tuple) for each index combination
    col_names = [(name, idx_tuple) for idx_tuple in index_tuples]

  return col_names


def _df_parameter_names(df):
  # Find all unique names in the DataFrame columns
  names = []
  for col_names in df.columns:
    if isinstance(col_names, tuple):
      # column name is tuple of form (param_name, index_tuple)
      if col_names[0] not in names:
        names.append(col_names[0])
    else:
      # column name is string
      if col_names not in names:
        names.append(col_names)

  return names




def convert_time(data, meta, time_format='datetime'):
  """
  Convert isotime parameters in data returned by hapi() to Python datetime
  objects, NumPy datetime64 values, or fixed-width HAPI time bytes.


  If time_format is 'datetime64', fill values are replaced with numpy.datetime64('NaT', 'us').
  """
  import numpy as np
  import pandas as pd

  from hapiclient import hapitime2datetime
  from hapiclient.hapitime import hapitime_format_str

  def trim_to_length(values, length):
    if len(values[0]) > length:
      # Trim to length - 1 and append Z to all.
      values = values.astype(f'U{length}')
      values.view(np.uint32).reshape(values.shape + (length,))[..., -1] = ord('Z')

    return values

  allowed = ['datetime', 'datetime64', 'hapitime']
  if time_format not in allowed:
    raise ValueError(f"Unsupported time_format: {time_format}. Must be one of {allowed}.")

  isotime_names = []
  for parameter in meta['parameters']:
    name = parameter['name']
    if parameter['type'] == 'isotime':
      isotime_names.append(name)
      first_value = data[name].flat[0]
      if isinstance(first_value, (bytes, np.bytes_)):
        # Primary time parameter is stored as bytes in data (which was a
        # mistake that needs to be addressed factoring in backward compatibility).
        parameter['x_format'] = hapitime_format_str([first_value.decode('utf-8')])
      elif isinstance(first_value, str):
        parameter['x_format'] = hapitime_format_str([first_value])
  parameters_dict = {parameter['name']: parameter for parameter in meta['parameters']}

  if len(isotime_names) == 0:
    return data

  fields = []
  for name in data.dtype.names:
    field_dtype = data.dtype.fields[name][0]
    if name not in isotime_names:
      fields.append((name, field_dtype))
      continue

    subdtype = field_dtype.subdtype
    if time_format == 'hapitime':
      time_length = parameters_dict[name]['length']
      if subdtype is None:
        fields.append((name, f'S{time_length}'))
      else:
        _, shape = subdtype
        fields.append((name, f'S{time_length}', shape))
      continue

    if subdtype is None:
      fields.append((name, object))
    else:
      _, shape = subdtype
      fields.append((name, object, shape))

  converted = np.empty(data.shape, dtype=fields)
  for name in data.dtype.names:
    if name not in isotime_names:
      converted[name] = data[name]
      continue

    dtype = data[name].dtype.type
    if issubclass(dtype, (np.bytes_, np.str_)):
      time_format_found = 'hapitime'
    elif issubclass(dtype, np.datetime64):
      time_format_found = 'datetime64'
    elif dtype is np.object_:
      time_format_found = 'datetime'
    else:
      raise ValueError(f"Unsupported dtype for isotime parameter {name}: {dtype}")

    if time_format_found == 'hapitime':
      if time_format == 'hapitime':
        converted[name] = data[name]
        continue
      if time_format == 'datetime':
        values = hapitime2datetime(data[name])
      if time_format == 'datetime64':
        values = pd.to_datetime(data[name].astype('U').ravel(), utc=True, errors='coerce')
        values = values.to_numpy(dtype='datetime64[us]').reshape(data[name].shape)

    if time_format_found == 'datetime':
      if time_format == 'hapitime':
        time_fmt = parameters_dict[name].get('x_format', None)
        values = datetime2hapitime(data[name], time_fmt=time_fmt)
        values = trim_to_length(values, parameters_dict[name]['length'])
      if time_format == 'datetime':
        converted[name] = data[name]
        continue
      if time_format == 'datetime64':
        values = pd.to_datetime(data[name].ravel(), utc=True)
        values = values.to_numpy(dtype='datetime64[us]').reshape(data[name].shape)

    if time_format_found == 'datetime64':
      if time_format == 'hapitime':
        time_fmt = parameters_dict[name].get('x_format', None)
        values = datetime2hapitime(data[name], time_fmt=time_fmt)
        fill = parameters_dict[name].get('fill')
        if fill is not None:
          values = np.where(np.isnat(data[name]), fill, values)
        values = trim_to_length(values, parameters_dict[name]['length'])
      if time_format == 'datetime':
        values = hapitime2datetime(data[name])
      if time_format == 'datetime64':
        converted[name] = data[name]
        continue

    values = values.reshape(data[name].shape)
    converted[name] = values

  return converted


def convert_time_test():
  import datetime
  import numpy as np

  #data, meta = _sample(parameters='scalariso')
  data, meta = _sample()

  # Test hapitime => {datetime, datetime64} => hapitime
  data_dt_from_ht = convert_time(data, meta, time_format='datetime')
  data_dt64_from_ht = convert_time(data, meta, time_format='datetime64')

  data_ht_from_dt = convert_time(data_dt_from_ht, meta, time_format='hapitime')
  data_ht_from_dt64 = convert_time(data_dt64_from_ht, meta, time_format='hapitime')

  _compare_np_arrays(data, data_ht_from_dt)
  _compare_np_arrays(data, data_ht_from_dt64)

  # Test datetime => datetime64 => haptime
  data_dt64_from_dt = convert_time(data_dt_from_ht, meta, time_format='datetime64')
  data_ht_from_dt = convert_time(data_dt64_from_dt, meta, time_format='hapitime')
  _compare_np_arrays(data, data_ht_from_dt)

  # Test datetime64 => datetime => haptime
  data_dt_from_dt64 = convert_time(data_dt64_from_ht, meta, time_format='datetime')
  data_ht_from_dt64 = convert_time(data_dt_from_dt64, meta, time_format='hapitime')
  _compare_np_arrays(data, data_ht_from_dt64)

  # Test the three identity conversions.
  _compare_np_arrays(data, convert_time(data, meta, time_format='hapitime'))
  _compare_np_arrays(data_dt_from_ht, convert_time(data_dt_from_ht, meta, time_format='datetime'))
  _compare_np_arrays(data_dt64_from_ht, convert_time(data_dt64_from_ht, meta, time_format='datetime64'))

  unicode_meta = {
    'parameters': [{'name': 'Time', 'type': 'isotime', 'length': 20}]
  }
  unicode_data = np.array(
    [('1970-01-01T00:00:00Z',), ('1970-01-01T00:00:01Z',)],
    dtype=[('Time', 'U20')],
  )
  unicode_datetime = convert_time(unicode_data, unicode_meta, time_format='datetime')
  unicode_hapitime = convert_time(unicode_datetime, unicode_meta, time_format='hapitime')
  assert unicode_hapitime.dtype['Time'] == 'S20'
  assert np.array_equal(unicode_hapitime['Time'], unicode_data['Time'].astype('S20'))

  vector_meta = {
    'parameters': [{'name': 'Time', 'type': 'isotime', 'length': 20, 'size': [2]}]
  }
  vector_data = np.array(
    [(['1970-01-01T00:00:00Z', '1970-01-01T00:00:01Z'],)],
    dtype=[('Time', 'U20', (2,))],
  )
  vector_datetime64 = convert_time(vector_data, vector_meta, time_format='datetime64')
  assert vector_datetime64['Time'].shape == (1, 2)
  vector_hapitime = convert_time(vector_datetime64, vector_meta, time_format='hapitime')
  assert np.array_equal(vector_hapitime['Time'], vector_data['Time'].astype('S20'))

  trimmed_meta = {
    'parameters': [{'name': 'Time', 'type': 'isotime', 'length': 20, 'x_format': '%Y-%m-%dT%H:%M:%S.%fZ'}]
  }
  trimmed_data = np.array(
    [(datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc),)],
    dtype=[('Time', object)],
  )
  trimmed_hapitime = convert_time(trimmed_data, trimmed_meta, time_format='hapitime')
  assert trimmed_hapitime['Time'][0] == b'1970-01-01T00:00:00Z'

  fill_meta = {
    'parameters': [{'name': 'Time', 'type': 'isotime', 'length': 20, 'fill': '0001-01-01T00:00:00Z', 'x_format': '%Y-%m-%dT%H:%M:%SZ'}]
  }
  fill_data = np.array([(np.datetime64('NaT', 'us'),)], dtype=[('Time', 'datetime64[us]')])
  fill_hapitime = convert_time(fill_data, fill_meta, time_format='hapitime')
  assert fill_hapitime['Time'][0] == b'0001-01-01T00:00:00Z'

  no_isotime_data = np.array([(1,)], dtype=[('value', 'i4')])
  no_isotime_meta = {'parameters': [{'name': 'value', 'type': 'integer'}]}
  assert convert_time(no_isotime_data, no_isotime_meta, time_format='datetime') is no_isotime_data

  try:
    convert_time(data, meta, time_format='invalid')
  except ValueError:
    pass
  else:
    raise AssertionError('Expected unsupported time_format to raise ValueError.')

  unsupported_data = np.array([(1,)], dtype=[('Time', 'i4')])
  unsupported_meta = {'parameters': [{'name': 'Time', 'type': 'isotime', 'length': 20}]}
  try:
    convert_time(unsupported_data, unsupported_meta, time_format='datetime')
  except ValueError:
    pass
  else:
    raise AssertionError('Expected unsupported isotime dtype to raise ValueError.')



def test_datetime2hapitime():

  import datetime
  import numpy as np
  dt = datetime.datetime(2000,1,1)

  hapi_time = datetime2hapitime(dt)

  assert hapi_time == '2000-01-01T00:00:00.000000Z'

  dt64 = np.datetime64('2000-01-01T00:00:00.000000')
  hapi_time = datetime2hapitime(dt64)
  assert hapi_time == '2000-01-01T00:00:00.000000Z'

  containers = [(list, list), (tuple, tuple), (np.array, np.ndarray)]

  for constructor, expected_type in containers:
    dts = constructor([datetime.datetime(2000,1,1)])
    hapi_times = datetime2hapitime(dts)

    assert isinstance(hapi_times, expected_type)
    assert len(hapi_times) == 1
    assert hapi_times[0] == '2000-01-01T00:00:00.000000Z'

  for constructor, expected_type in containers:
    dts = constructor([datetime.datetime(2000,1,1), datetime.datetime(2000,1,2)])
    hapi_times = datetime2hapitime(dts)

    assert isinstance(hapi_times, expected_type)
    assert len(hapi_times) == 2
    assert hapi_times[0] == '2000-01-01T00:00:00.000000Z'
    assert hapi_times[1] == '2000-01-02T00:00:00.000000Z'

  dts = np.array([datetime.datetime(2000,1,1), datetime.datetime(2000,1,2)])
  dts = dts.reshape(2, 1)
  hapi_times = datetime2hapitime(dts)
  assert hapi_times.shape == (2, 1)

  dts = np.array([datetime.datetime(2000,1,1), datetime.datetime(2000,1,2)])
  dts = dts.reshape(2)
  hapi_times = datetime2hapitime(dts)
  assert hapi_times.shape == (2,)

  dts = np.array([datetime.datetime(2000,1,1), datetime.datetime(2000,1,2)])
  dts = np.array([dts, dts])
  dts = dts.reshape(2, 2)
  hapi_times = datetime2hapitime(dts)
  assert hapi_times.shape == (2, 2)

  dts = np.array([
    np.datetime64('2000-01-01T00:00:00.000000'),
    np.datetime64('2000-01-02T00:00:00.000000')
  ]).reshape(2, 1)
  hapi_times = datetime2hapitime(dts)
  assert hapi_times.shape == (2, 1)
  assert hapi_times[0, 0] == '2000-01-01T00:00:00.000000Z'
  assert hapi_times[1, 0] == '2000-01-02T00:00:00.000000Z'


def datetime2hapitime(dts, time_fmt='%Y-%m-%dT%H:%M:%S.%fZ'):
  """Convert datetime object(s) or datetime64 value(s) to ISO 8601 string(s)

  Example:
  ::

      from hapiclient import datetime2hapitime
      import datetime
      dts = [datetime.datetime(2000, 1, 1), datetime.datetime(2000, 1, 2)]
      hapi_times = datetime2hapitime(dts)
      print(hapi_times)
      # ['2000-01-01T00:00:00.000000Z', '2000-01-02T00:00:00.000000Z']

      dts = np.array([datetime.datetime(2000, 1, 1), datetime.datetime(2000, 1, 2)])
      hapi_times = datetime2hapitime(dts)
      print(repr(hapi_times))
      # array(['2000-01-01T00:00:00.000000Z', '2000-01-02T00:00:00.000000Z'], dtype='<U27')

  Parameter
  ---------
  dts:
  - A datetime object or datetime64 value
  - A tuple or list of datetime object(s) or datetime64 value(s)
  - A NumPy array of datetime object(s) or datetime64 value(s)

  Returns
  -------
  - An ISO 8601 string (if input is a Python datetime object or datetime64 value)
  - A tuple or list of ISO 8601 string(s) (if input is list or tuple of datetime object(s) or datetime64 value(s))
  - A NumPy array of ISO 8601 string(s) of the same shape as the input (if input is NumPy array of Python datetime object(s) or datetime64 value(s))
  """

  import numpy as np
  import pandas as pd
  import datetime
  in_type = type(dts)

  if in_type is np.ndarray:
    try:
      hapi_times = pd.to_datetime(dts.ravel()).strftime(time_fmt).to_numpy().reshape(dts.shape)
      return hapi_times
    except (TypeError, ValueError) as exc:
      msg = "Input NumPy array must contain Python datetime objects or datetime64 values."
      raise ValueError(msg) from exc

  scalar = False
  if not isinstance(dts, (list, tuple, np.ndarray)):
    scalar = True
    dts = [dts]

  hapi_times = []
  for dt in dts:
    if not isinstance(dt, (datetime.datetime, np.datetime64)):
      msg = "Input must be a Python datetime object or datetime64 value, "
      msg += "a list/tuple of datetime object(s) or datetime64 value(s), "
      msg += "or a NumPy array of datetime object(s) or datetime64 value(s). "
      msg += f"Got {type(dt)}."
      raise ValueError(msg)
    if isinstance(dt, np.datetime64):
      dt = dt.astype('datetime64[us]').astype(datetime.datetime)
    hapi_times.append(dt.strftime(time_fmt))

  if scalar:
    if in_type is tuple:
      return tuple(hapi_times)
    else:
      return hapi_times[0]
  else:
    if in_type is tuple:
      return tuple(hapi_times)
    else:
      return hapi_times


def convert_nan(data, meta):
  pass


def _nan_fill(data, param_type, fill_value):
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





def _samples(versions=None, dataset=None, parameters=''):

  from hapiclient import hapi

  if versions is None:
    versions = ['2.0', '2.1', '3.0', '3.1', '3.2', '3.3']

  samples = {}
  for version in versions:

    server = f'http://hapi-server.org/servers/TestData{version}/hapi'
    datasets = [entry['id'] for entry in hapi(server)['catalog']]

    for dataset in datasets:
      samples[(version, dataset)] = _sample(version=version, dataset=dataset, parameters=parameters)

  return samples


def _sample(version='2.0', dataset=None, parameters=''):
  from hapiclient import hapi

  server = f'http://hapi-server.org/servers/TestData{version}/hapi'
  catalog = hapi(server)['catalog']
  datasets = [entry['id'] for entry in catalog]

  start  = '1970-01-01Z'
  stop   = '1970-01-01T00:00:11Z'
  if version == '3.2':
    start  = hapi(server,dataset)['startDate']
    stop   = hapi(server,dataset)['stopDate']

  if dataset is None:
    data, meta = hapi(server, datasets[0], parameters, start, stop)
  else:
    data, meta = hapi(server, dataset, parameters, start, stop)

  return data, meta


def _compare_np_arrays(data, data_np):

  import numpy as np

  msg = f"Number of fields mismatch: {len(data.dtype)} != {len(data_np.dtype)}"
  assert len(data.dtype) == len(data_np.dtype), msg

  for name in data.dtype.names:
    msg = (
      f"Dtype mismatch for parameter {name}: "
      f"{data[name].dtype} != {data_np[name].dtype}"
    )
    assert data[name].dtype == data_np[name].dtype, msg

    equal_records = data[name] == data_np[name]
    if not np.all(equal_records):
      index = np.flatnonzero(~equal_records)[0]
      msg = (
        f"Data mismatch for parameter {name} at linear index {index}: "
        f"{data[name][index]!r} != {data_np[name][index]!r}"
      )
      raise AssertionError(msg)



if __name__ == "__main__":
  df2np_test()
  df_infer_meta_test()
  df_infer_meta_testdata_test()
  np2df_testdata_test()
  test_datetime2hapitime()
  convert_time_test()
  np2df_name_map_test()
  np2df_include_exclude_test()
