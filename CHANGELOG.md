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
