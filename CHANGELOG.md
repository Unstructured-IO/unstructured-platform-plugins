## 0.0.13

* **Conform to PEP-625 compliance for project naming**

## 0.0.12

* **Bugfix: Fix UnrecoverableException exception handling to include full response**

## 0.0.11

* **Bugfix: Add UnrecoverableException exception handling back**

## 0.0.10

* **Bugfix: Add `None` support in mapping `FileDataMeta` response**

## 0.0.9

* **Support optionally exposing addition metadata around FileData**

## 0.0.8

* **reduce usage data log level** We do not want to have so much verbosity for something that might happen a lot
* **Support unrecoverable errors** Throw a 512 error for an unrecoverable error

## 0.0.7

* **Improve code separation to help with unit tests**

## 0.0.6

* **Support streaming response types for /invoke if callable is async generator**

## 0.0.5

* **Improve logging to hide body in case of sensitive data unless TRACE level**

## 0.0.4

### Fixes

* **Do not block event loop when running plugin code**

## 0.0.3

### Features

* **OTEL middleware added**

## 0.0.2

### Enhancements

### Features

### Fixes

* **FileData Literal not handled** FileData content was updated to use Literal rather than Enum. This case needed to be added. 

## 0.0.1

### Enhancements

### Features

### Fixes

* **Model generation when schema is empty fixed** Key error was being thrown when properties not in schema, but this doesn't exist when schema is null. Null check added. 

## 0.0.0

### Enhancements

### Features

* **Initial Release** First release of the project with all existing implementations in place. 

### Fixes
