# Unstructured Platform Plugins
 ![CI](https://github.com/Unstructured-IO/unstructured-platform-plugins/actions/workflows/ci.yml/badge.svg?branch=main)

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
For all following commands, make sure you have the local repo in your `PYTHONPATH`:
```shell
export PYTHONPATH=.
```

Wrapping a basic function with a typed dict response
```shell
etl-uvicorn test.assets.typed_dict_response:sample_function
```

Wrapping a basic async function with a typed dict response
```shell
etl-uvicorn test.assets.async_typed_dict_response:async_sample_function
```

Wrapping a class. For this to work, the class must be self instantiating. When passing a class in, a method needs to 
be passed in as well, otherwise `__call__` is used. The following example returns a pydantic BaseModel
```shell
etl-uvicorn test.assets.pydantic_response_class_method:SampleClass --method-name sample_method
```

Wrapping an instance of a class.
```shell
etl-uvicorn test.assets.pydantic_response_class_method:sample_class --method-name sample_method
```

The CLI does some validation on the wrapped function, which must have explicit inputs and outputs, meaning *args 
and **kwargs are not supported. These will cause the cli to fail fast.
```shell
etl-uvicorn test.assets.improper_function:sample_improper_function
```

### /id requirements
All the the above examples caused the CLI to autogenerate the `/id` endpoint with a hash of the generated schema. 
However, you can also provide it a reference to use for the id value. This can be a reference to a concrete 
value (i.e. `plugin_id="my_plugin_id"`) or a function in the same way that one was passed in to be wrapped above. 

Will populate the response of `/id` with the static value of `hash_value`:
```shell
etl-uvicorn test.assets.typed_dict_response:sample_function --plugin-id test.assets.simple_hash_value:hash_value
```

Can populate it using a lambda:
```shell
etl-uvicorn test.assets.typed_dict_response:sample_function --plugin-id test.assets.simple_hash_lambda:hash_lambda_fn
```

Similar to the function being wrapped, can also use a class:
```shell
etl-uvicorn test.assets.typed_dict_response:sample_function --plugin-id test.assets.simple_hash_class:GetHash --plugin-id-method my_hash
```

Or the instantiated class:
```shell
etl-uvicorn test.assets.typed_dict_response:sample_function --plugin-id test.assets.simple_hash_class:get_hash_class_instance --plugin-id-method my_hash
```

