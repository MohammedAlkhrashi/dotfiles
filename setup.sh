#! /bin/bash
shopt -s dotglob

cd dotfiles
for file in *; 
do
	if [[ $file == *.sh ]]; then
		filename=${file::-3}
		cat $file >> ~/"${filename}"
	else
		cp $file ~//
	fi
done
cd ..
