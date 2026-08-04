from hapiserver_demo.data import _read_list


FILE_LIST = [{
  "file_name": "demo",
  "start_data": "1970-01-01T00:00:00.000000Z",
  "stop_data": "1970-01-01T00:01:00.000000Z",
}]
START = "1970-01-01T00:00:10.000000Z"
STOP = "1970-01-01T00:00:55.000000Z"


def test_data_read_list():
  expected = [{
    "file_name": "demo",
    "start_read": "1970-01-01T00:00:10.000000Z",
    "stop_read": "1970-01-01T00:00:55.000000Z",
    "start_data": "1970-01-01T00:00:00.000000Z",
    "stop_data": "1970-01-01T00:01:00.000000Z",
  }]
  assert _read_list(FILE_LIST, START, STOP) == expected

  expected = [
    {
      "file_name": "demo",
      "start_read": "1970-01-01T00:00:10.000000Z",
      "stop_read": "1970-01-01T00:00:40.000000Z",
      "start_data": "1970-01-01T00:00:00.000000Z",
      "stop_data": "1970-01-01T00:01:00.000000Z",
    },
    {
      "file_name": "demo",
      "start_read": "1970-01-01T00:00:40.000000Z",
      "stop_read": "1970-01-01T00:00:55.000000Z",
      "start_data": "1970-01-01T00:00:00.000000Z",
      "stop_data": "1970-01-01T00:01:00.000000Z",
    },
  ]
  assert _read_list(FILE_LIST, START, STOP, max_seconds=30) == expected



if __name__ == "__main__":
  test_data_read_list()
