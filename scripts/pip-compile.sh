#!/usr/bin/env bash

# python version must match lowest supported (3.10)
major=3
minor=10
if ! python -c "import sys; assert sys.version_info.major == $major and sys.version_info.minor == $minor"; then
	echo "python version not equal to expected $major.$minor: $(python --version)"
	exit 1
fi

while IFS= read -r -d '' file; do
	filename=${file%.in}
	txtfilename="${filename}.txt"
	echo "Removing $txtfilename"
	rm -f $txtfilename
	echo "Running pip-compile on file $file"
	pip-compile --upgrade --verbose "$file"
done < <(find requirements/ -type f -name "*.in" -maxdepth 1 -print0)
