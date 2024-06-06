# Unstructured Platform Plugins
 ![CI](https://github.com/Unstructured-IO/unstructured-enterprise/actions/workflows/ci.yml/badge.svg?branch=main)

Information about how to build custom plugins to integrate with Unstructured Platform.

## Plugin Development
Any plugin must be published in a dedicated docker image with all required dependencies that when run, exposes an api 
on port 8000 with the required endpoints to interact with the Unstructured Platform product:
* `/invoke`: A `POST` endpoint which gets all data to run the underlying logic in the request body and expects a json serializable response. 
* `/schema`: A `GET` endpoint which publishes a json schema formatted response with the schema of the input and output expected by the plugin.


### Utility CLI
When installing this repo, it also installs the cli `etl-uvicorn`. This takes a pointer to any generic python 
function and wraps it in a FastApi application to conform to the patterns that are expected by the api hosting the 
plugin logic. 
