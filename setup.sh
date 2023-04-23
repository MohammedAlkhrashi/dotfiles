#! /bin/bash
shopt -s dotglob
chmod a+x dotfiles/utils/write_config_elements.sh

cd dotfiles
for file in *;
do
    if [ -f $file ]; then
        if [[ $file == *.cfg ]]; then
            filename=${file::-4}
            ./utils/write_config_elements.sh $file $filename
        else
            cp $file ~//
        fi
    fi
done
cd ..