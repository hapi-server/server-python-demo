tests = {
  "catalog": [
    {
      "response": {
        "content_regex": "demo1",
        "content_lambda": lambda content: "catalog" in content and len(content["catalog"]) == 1
      }
    }
  ],
  "info": [
    {
      "request": {
        "id": "demo1"
      },
      "response": {
        "content_regex": "scalar",
        "content_lambda": lambda content: "parameters" in content and len(content["parameters"]) == 2
      }
    }
  ],
  "data": [
    {
      "request": {
        "dataset": "demo1",
        "start": "1970-01-01T00:00:00Z",
        "stop": "1970-01-01T00:00:02Z"
      },
      "response": {
        "status_code": 200,
        "content_length": 46,
        "content_regex": "^1970-01",
        "content": "1970-01-01T00:00:00Z,0\n1970-01-01T00:00:01Z,1\n"
      }
    }
  ]
}
