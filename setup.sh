#!/bin/bash

set -e

DOTFOLDER=dotfiles

cd $DOTFOLDER

for filename in .*; do
	if [[ "$filename" == "." || "$filename" == ".." ]]; then
 		echo "Skipping file: $filename"
 	else
		rm ~/$filename
 		ln $filename ~/$filename
 	fi
done
