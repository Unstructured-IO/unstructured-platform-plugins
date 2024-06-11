#!/usr/bin/env bash

while IFS= read -r -d '' file; do
	echo "Running 'pip-compile --upgrade $file'"
	pip-compile --upgrade --verbose "$file"
done < <(find requirements/ -type f -name "*.in" -maxdepth 1 -print0)
