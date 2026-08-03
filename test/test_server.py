"""
Run tests using config.json located in this directory.

Usage:
  pytest -s -v test/test_server.py
  python test/test_server.py
"""

import sys
import json
import pathlib

from fastapi.testclient import TestClient

project_dir = pathlib.Path(__file__).parent.parent
if str(project_dir) not in sys.path:
  sys.path.insert(0, str(project_dir))

def _config():
  config_path = pathlib.Path(__file__).parent / "config.json"

  with config_path.open() as file:
    config = json.load(file)

  test_path = pathlib.Path(__file__).parent / "tests.py"
  import importlib.util
  spec = importlib.util.spec_from_file_location("tests", test_path)
  tests_module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(tests_module)
  tests = tests_module.tests

  return config, config_path, tests

def test_server(config_file=None):
  import hapiserver

  config, config_path, tests = _config()

  app = hapiserver.app(str(config_path))
  client = TestClient(app)
  base_path = config.get("path", "/hapi").rstrip("/")

  for endpoint in ["about", "capabilities", "catalog"]:
    response = client.get(f"{base_path}/{endpoint}")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert isinstance(response.json(), dict)


  if tests:
    for endpoint in tests:
      for test in tests[endpoint]:
        params = test.get("request", {})
        response = client.get(f"{base_path}/{endpoint}", params=params)

        if 'status_code' not in test['response']:
          assert response.status_code == 200
        else:
          assert response.status_code == test['response']['status_code']

        content = response.content.decode('utf-8')
        if 'content_length' in test['response']:
          got = len(content)
          msg = f"Failed test for {endpoint} with request {params}. "
          msg += f"\nExpected content length: {test['response']['content_length']}, got: {got}"
          assert got == test['response']['content_length'], msg

        if 'content' in test['response']:
          got = content
          msg = f"Failed test for {endpoint} with request {params}. "
          msg += f"\nExpected content:\n'{test['response']['content']}'\ngot:\n"
          msg += f"'{got}'"
          assert got == test['response']['content'], msg

        if 'content_regex' in test['response']:
          import re
          got = content
          msg = f"Failed test for {endpoint} with request {params}. "
          msg += f"\nExpected content to match regex:\n'{test['response']['content_regex']}'"
          msg += f"\ngot:\n'{got}'"
          assert re.search(test['response']['content_regex'], got), msg

        if 'content_lambda' in test['response']:
          import inspect
          func = test['response']['content_lambda']
          source = inspect.getsource(func).strip()
          if response.headers.get("content-type", "").startswith("application/json"):
            content = response.json()
          msg = f"Failed test for {endpoint} with request {params}. "
          msg += f"Expected content to satisfy lambda function:\n{source}"
          assert test['response']['content_lambda'](content), msg

if __name__ == "__main__":
  test_server()
