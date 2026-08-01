# server-python-demo

Demo for [`hapiserver`](https://github.com/hapi-server/server-python)

To adapt to different data, modify the four files

1. `config-functions.json` or `config-scripts.json`
2. `catalog.py`, which returns `/catalog` metadata
3. `info.py` which returns `/info` metadata
4. `data.py` which returns the `/data` response

# Standalone server

For a standalone server, start using

```bash
hapiserver --config src/config-functions.json --workers 2 --host 0.0.0.0 --port 8675
# or
# hapiserver --config src/config-scripts.json --workers 2 --host 0.0.0.0 --port 8675
```

and see the comments in [src/*.py](src/) for adapting the demo to your data.

# Alongside an existing ASGI or WSGI application

`hapiserver` uses the FastAPI framework to create an ASGI application.

To integrate the HAPI application (HAPI endpoints) into an existing ASGI application, see [app.py](src/app.py).

To integrate HAPI endpoints into an existing WSGI application (built using frameworks such as Flask, Bottle, and Django), see [server-general-psws](https://github.com/hapi-server/server-general-psws), which adds HAPI endpoints to a Django application by converting the HAPI ASGI app to WSGI and combining it with the Django WSGI application.
