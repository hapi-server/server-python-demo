# server-python-demo

Demo for [`hapiserver`](https://github.com/hapi-server/server-python)

To adapt to different data, modify the four files

1. `config.json` or `config-scripts.json`
2. `catalog.py`, which returns `/catalog` metadata
3. `info.py` which returns `/info` metadata
4. `data.py` which returns the `/data` response

Unit tests for the demo server in [test/](test/) can also be adapted.

# Install

```bash
git clone https://github.com/hapi-server/server-python-demo
cd server-python-demo
python -m pip install -e .
python test/test_server.py
```

# Run standalone server

For a standalone server, start using

```bash
hapiserver --config hapiserver_demo/config.json --workers 2 --host 0.0.0.0 --port 8675
# or
# hapiserver --config hapiserver_demo/config-scripts.json --workers 2 --host 0.0.0.0 --port 8675
```

and see the comments in [hapiserver_demo/*.py](hapiserver_demo/) for adapting the demo to your data.

# Alongside an existing ASGI or WSGI application

`hapiserver` uses the FastAPI framework to create an ASGI application.

To integrate the HAPI application (HAPI endpoints) into an existing ASGI application, see [app.py](hapiserver_demo/app.py).

To integrate HAPI endpoints into an existing WSGI application (built using frameworks such as Flask, Bottle, and Django), see [server-general-psws](https://github.com/hapi-server/server-general-psws), which adds HAPI endpoints to a Django application by converting the HAPI ASGI app to WSGI and combining it with the Django WSGI application.
