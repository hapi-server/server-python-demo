# server-python-demo

Demo template for hapiserver (server-python repository)

# Standalone server

For a standalone server, start using

```
hapiserver --config src/config-functions.json --workers 2 --host 0.0.0.0 --port 8675
# or
# hapiserver --config src/config-scripts.json --workers 2 --host 0.0.0.0 --port 8675
```

and see the comments in [src/*.py](src/) for adapting the demo to your data.

# Integration into existing ASGI or WSGI application

`hapiserver` uses the FastAPI framework to create an ASGI application.

To integrate the HAPI application (HAPI endpoints) into an existing ASGI application, see [demo-app.py](demo-app.py).

To integrate HAPI endpoints into an existing WSGI application (built using frameworks such as Flask, Bottle, and Django), see https://github.com/hapi-server/server-general-psws, which adds HAPI endpoints to a Django application by converting the HAPI ASGI app to WSGI and combining it with the Django WSGI application.
