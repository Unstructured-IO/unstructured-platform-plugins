# Unstructured Platform Plugins
 ![CI](https://github.com/Unstructured-IO/unstructured-enterprise/actions/workflows/ci.yml/badge.svg?branch=main)

Information about how to build custom plugins to integrate with Unstructured Platform.

## Plugin Development
Any plugin must be published in a dedicated docker image with all required dependencies that when run, exposes an api 
on port 8000 with the required endpoints to interact with the Unstructured Platform product:
* `/invoke`: A `POST` endpoint which gets all data to run the underlying logic in the request body and expects a json serializable response. 
* `/schema`: A `GET` endpoint which publishes a json schema formatted response with the schema of the input and output expected by the plugin.
* `/id`: A `GET` endpoint which publishes a string unique identifier for this instance of the plugin. Will default to a hash of the schema 
response if one is not set explicitly.


## Utility CLI
When installing this repo, it also installs the cli `etl-uvicorn`. This takes a pointer to any generic python 
function and wraps it in a FastApi application to conform to the patterns that are expected by the api hosting the 
plugin logic. This cli extends the existing `uvicorn` cli which takes in a pointer to a fastapi instance or factory but 
instead takes in a pointer to a python function/class which gets wrapped with a FastApi application. 

## Example usage
Wrapping a basic function
```shell
etl-uvicorn unstructured_platform_plugins.etl_uvicorn.example:sample_function
```

Wrapping a basic async function
```shell
etl-uvicorn unstructured_platform_plugins.etl_uvicorn.example:async_sample_function
```

Wrapping a class. For this to work, the class must be self instantiating. When passing a class in, a method needs to 
be passed in as well, otherwise `__call__` is used.
```shell
etl-uvicorn unstructured_platform_plugins.etl_uvicorn.example:SampleClass --method sample_method
```

Wrapping an instance of a class.
```shell
etl-uvicorn unstructured_platform_plugins.etl_uvicorn.example:sample_class --method sample_method
```

The CLI does some validation on the wrapped function, which must have explicit inputs and outputs, meaning *args 
and **kwargs are not supported. These will cause the cli to fail fast.
```shell
etl-uvicorn unstructured_platform_plugins.etl_uvicorn.example:sample_function
```
