#! /bin/bash
shopt -s dotglob

cd dotfiles
for f in *; 
do
	cp $f ~//
done
cd ..
